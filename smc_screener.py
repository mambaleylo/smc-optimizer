#!/usr/bin/env python3
"""
SMC Optimizer v1.0
Smart Money Concepts parameter optimizer for Gate.io futures.
Inspired by WickFill Optimizer architecture (mambaleylo/wickfill).

Что оптимизирует:
  - swing_len       : длина свинга (pivot detection window)
  - internal_len    : длина внутренней структуры
  - ob_filter_mult  : множитель ATR для фильтра OB
  - fvg_threshold   : порог FVG (0 = выкл, 1 = авто)
  - use_eqhl        : фильтр Equal High/Low
  - eqhl_len        : bars confirmation для EQH/EQL
  - eqhl_thresh     : чувствительность EQH/EQL (ATR-кратное)
  - entry_type      : 0=BOS-only, 1=CHoCH-only, 2=all
  - htf_bias        : 0=off, 1=on (торгуем только по тренду HTF swing)
  - sl_pct          : стоп-лосс %
  - tp_pct          : тейк-профит %
  - use_atr_sl      : динамический SL по ATR
  - atr_sl_mult     : множитель ATR для SL
  - confirm_bar     : ждать подтверждающий бар после BOS/CHoCH

Стратегия сигналов:
  LONG  — bullish BOS или CHoCH на swing/internal структуре
  SHORT — bearish BOS или CHoCH

Выход:
  - TP / SL по фиксированному % (или ATR-SL)
  - Следующий противоположный сигнал (sig-close)

Run:   python3 smc_screener.py
UI:    http://localhost:8765
"""

# ── changelog (newest first) ───────────────────────────────────────────────
# v1.0: первый релиз — Gate.io candles, SMC signal sim, Basin-Hopping optimizer,
#       HTML/JS UI, Telegram/ntfy alerts, GitHub config sync.
# ──────────────────────────────────────────────────────────────────────────

import os, sys, json, time, math, random, threading, base64, hashlib
import itertools, traceback, copy, bisect, urllib.request

from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from datetime import datetime, timezone

try:
    import requests
except ImportError:
    os.system("pip install requests --break-system-packages -q")
    import requests

# ── ANSI ──────────────────────────────────────────────────────────────────
_C_RST  = "\033[0m"
_C_GRN  = "\033[32m"
_C_YEL  = "\033[33m"
_C_RED  = "\033[31m"
_C_GREY = "\033[90m"
_C_CYN  = "\033[36m"

# ══════════════════════════════════════════════════════════════════════════
# PARAM SPACE
# ══════════════════════════════════════════════════════════════════════════
PARAM_SPACE = {
    "swing_len":      {"min": 20,  "max": 100, "step": 5,    "type": "int",   "label": "Swing Length"},
    "internal_len":   {"min": 3,   "max": 10,  "step": 1,    "type": "int",   "label": "Internal Length"},
    "ob_filter_mult": {"min": 1.0, "max": 3.0, "step": 0.25, "type": "float", "label": "OB ATR Filter ×"},
    "fvg_threshold":  {"values": [0, 1],                      "type": "int",   "label": "FVG Auto Thresh"},
    "use_eqhl":       {"values": [False, True],               "type": "bool",  "label": "EQH/EQL Filter"},
    "eqhl_len":       {"min": 2,   "max": 6,   "step": 1,    "type": "int",   "label": "EQH/EQL Bars"},
    "eqhl_thresh":    {"min": 0.0, "max": 0.5, "step": 0.1,  "type": "float", "label": "EQH/EQL Thresh"},
    "entry_type":     {"values": [0, 1, 2],                   "type": "int",   "label": "Entry: 0=BOS 1=CHoCH 2=All"},
    "htf_bias":       {"values": [False, True],               "type": "bool",  "label": "HTF Trend Filter"},
    "confirm_bar":    {"values": [False, True],               "type": "bool",  "label": "Confirmation Bar"},
    "sl_pct":         {"min": 0.35,"max": 2.0, "step": 0.05, "type": "float", "label": "Stop-Loss (%)"},
    "tp_pct":         {"min": 0.5, "max": 3.0, "step": 0.1,  "type": "float", "label": "Take-Profit (%)"},
    "use_atr_sl":     {"values": [False, True],               "type": "bool",  "label": "Dynamic ATR SL"},
    "atr_sl_mult":    {"min": 0.5, "max": 3.0, "step": 0.25, "type": "float", "label": "ATR SL Mult"},
}

def _param_grid(spec):
    if "values" in spec:
        return list(spec["values"])
    mn, mx, st = spec["min"], spec["max"], spec["step"]
    vals = []
    v = mn
    while v <= mx + 1e-9:
        if spec["type"] == "int":
            vals.append(int(round(v)))
        else:
            vals.append(round(v, 6))
        v += st
    return vals

_GRIDS = {k: _param_grid(v) for k, v in PARAM_SPACE.items()}

def _rand_params():
    return {k: random.choice(v) for k, v in _GRIDS.items()}

def _clamp_params(p):
    out = {}
    for k, g in _GRIDS.items():
        v = p.get(k, g[0])
        if v not in g:
            # snap to nearest
            v = min(g, key=lambda x: abs(x - v) if isinstance(v, (int, float)) else 0)
        out[k] = v
    return out

# ══════════════════════════════════════════════════════════════════════════
# GATE.IO CANDLE FETCHING
# ══════════════════════════════════════════════════════════════════════════
GATE_BASE = "https://api.gateio.ws/api/v4"

def _tf_to_seconds(tf: str) -> int:
    table = {"1m":60,"3m":180,"5m":300,"15m":900,"30m":1800,
             "1h":3600,"2h":7200,"4h":14400,"6h":21600,"12h":43200,
             "1d":86400,"1w":604800}
    return table.get(tf, 3600)

def fetch_candles(symbol: str, tf: str, days: int = 90) -> list:
    """Загружает свечи с Gate.io фьючерсы. Возвращает список dict {t,o,h,l,c,v}."""
    interval = tf
    limit_per_req = 1000
    tf_sec = _tf_to_seconds(tf)
    now_ts = int(time.time())
    since_ts = now_ts - days * 86400

    candles = []
    end_ts = now_ts
    seen = set()

    for _ in range(50):
        url = (f"{GATE_BASE}/futures/usdt/candlesticks"
               f"?contract={symbol}&interval={interval}&limit={limit_per_req}&to={end_ts}")
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            batch = r.json()
        except Exception as e:
            print(f"{_C_RED}[candles] fetch error: {e}{_C_RST}", flush=True)
            break

        if not batch:
            break

        new = 0
        for c in batch:
            t = int(c.get("t") or c.get("time") or 0)
            if t in seen or t < since_ts:
                continue
            seen.add(t)
            candles.append({
                "t": t,
                "o": float(c.get("o") or c.get("open") or 0),
                "h": float(c.get("h") or c.get("high") or 0),
                "l": float(c.get("l") or c.get("low") or 0),
                "c": float(c.get("c") or c.get("close") or 0),
                "v": float(c.get("v") or c.get("volume") or 0),
            })
            new += 1

        if not new:
            break

        oldest = min(int(c.get("t") or c.get("time") or end_ts) for c in batch)
        if oldest <= since_ts:
            break
        end_ts = oldest - 1
        time.sleep(0.05)

    candles.sort(key=lambda x: x["t"])
    return candles

# ══════════════════════════════════════════════════════════════════════════
# SMC SIGNAL SIMULATOR
# ══════════════════════════════════════════════════════════════════════════
def _atr(candles, period=14, i=None):
    """ATR до индекса i (включительно)."""
    if i is None:
        i = len(candles) - 1
    start = max(0, i - period + 1)
    trs = []
    for j in range(start, i + 1):
        h, l, c = candles[j]["h"], candles[j]["l"], candles[j]["c"]
        pc = candles[j-1]["c"] if j > 0 else c
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0

def _detect_pivots(candles, size):
    """
    Возвращает список (index, price, direction) — 'H' или 'L'.
    Pivot high: high[size] > all highs in [0..size-1] and [size+1..2*size]
    """
    n = len(candles)
    pivots = []
    for i in range(size, n - size):
        hi = candles[i]["h"]
        lo = candles[i]["l"]
        is_ph = all(candles[i-k]["h"] < hi for k in range(1, size+1)) and \
                all(candles[i+k]["h"] < hi for k in range(1, size+1))
        is_pl = all(candles[i-k]["l"] > lo for k in range(1, size+1)) and \
                all(candles[i+k]["l"] > lo for k in range(1, size+1))
        if is_ph:
            pivots.append((i, hi, "H"))
        if is_pl:
            pivots.append((i, lo, "L"))
    pivots.sort(key=lambda x: x[0])
    return pivots

def _get_htf_direction(candles, swing_len):
    """
    Упрощённый HTF тренд: последовательность HH/HL → 1 (bull), LH/LL → -1 (bear).
    Смотрим на последние 3 свинг-точки.
    """
    pivots = _detect_pivots(candles, swing_len)
    highs = [(i, p) for i, p, d in pivots if d == "H"]
    lows  = [(i, p) for i, p, d in pivots if d == "L"]
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1][1] > highs[-2][1]
        hl = lows[-1][1]  > lows[-2][1]
        if hh and hl:
            return 1
        if not hh and not hl:
            return -1
    return 0

def simulate(candles, p, days_limit=0, init_deposit=100.0, risk_pct=20.0):
    """
    Симулирует торговлю SMC-сигналами по параметрам p.
    Возвращает dict с метриками или None.
    """
    sw  = p["swing_len"]
    iln = p["internal_len"]
    ob_mult = p["ob_filter_mult"]
    entry_t = p["entry_type"]     # 0=BOS, 1=CHoCH, 2=all
    htf_on  = p["htf_bias"]
    conf_b  = p["confirm_bar"]
    sl_p    = p["sl_pct"] / 100
    tp_p    = p["tp_pct"] / 100
    use_atr_sl = p["use_atr_sl"]
    atr_sl_m   = p["atr_sl_mult"]

    if days_limit > 0:
        cutoff = time.time() - days_limit * 86400
        candles = [c for c in candles if c["t"] >= cutoff]

    n = len(candles)
    min_bars = max(sw * 2, iln * 2, 30)
    if n < min_bars:
        return None

    # HTF direction (whole dataset as proxy)
    htf_dir = _get_htf_direction(candles, max(sw, 5)) if htf_on else 0

    # ── detect swing structure ────────────────────────────────────────────
    # We scan bar-by-bar, maintaining last pivot high/low and trend bias.
    # When close crosses last pivot → BOS or CHoCH.

    # Pre-detect all pivots (swing and internal)
    swing_pivots   = _detect_pivots(candles, sw)
    internal_pivots= _detect_pivots(candles, iln)

    # Build per-bar last-known pivot (for real-time simulation)
    # sw_high_at[i] = (pivot_bar, pivot_price) last swing high known at bar i
    def _build_pivot_maps(pivots, n):
        last_h = [None] * n
        last_l = [None] * n
        ph, pl = None, None
        pi = 0
        plist = pivots
        for i in range(n):
            # pivots confirmed at i - size (already in the list up to i-size)
            while pi < len(plist) and plist[pi][0] <= i - 1:
                idx, price, d = plist[pi]
                if d == "H":
                    ph = (idx, price)
                else:
                    pl = (idx, price)
                pi += 1
            last_h[i] = ph
            last_l[i] = pl
        return last_h, last_l

    sw_lh, sw_ll   = _build_pivot_maps(swing_pivots,   n)
    in_lh, in_ll   = _build_pivot_maps(internal_pivots, n)

    # ── simulation loop ───────────────────────────────────────────────────
    deposit  = init_deposit
    trades   = []
    in_trade = False
    direction= 0
    ep = tp_price = sl_price = 0.0
    entry_bar = 0

    sw_trend   = 0   # last known swing trend
    in_trend   = 0   # last known internal trend
    sw_ph_crossed = True
    sw_pl_crossed = True
    in_ph_crossed = True
    in_pl_crossed = True
    last_sw_h = last_sw_l = None
    last_in_h = last_in_l = None

    # for BOS/CHoCH detection track if pivot crossed
    sw_h_cross = {}   # pivot_bar → crossed bool
    sw_l_cross = {}
    in_h_cross = {}
    in_l_cross = {}

    signals = []  # list of {bar, dir, ep, tp, sl, exit_bar, exit_price, win}

    pending_entry = None  # (bar, direction, ep, tp, sl) for confirm_bar mode

    for i in range(min_bars, n):
        c  = candles[i]
        hi = c["h"]; lo = c["l"]; cl = c["c"]; op = c["o"]

        # ── close open trade ─────────────────────────────────────────────
        if in_trade:
            hit_tp = (direction == 1 and hi >= tp_price) or (direction == -1 and lo <= tp_price)
            hit_sl = (direction == 1 and lo <= sl_price) or (direction == -1 and hi >= sl_price)
            if hit_tp or hit_sl:
                win = hit_tp and not hit_sl
                if hit_tp and hit_sl:
                    # simultaneous — conservative: SL wins
                    win = False
                exit_p = tp_price if win else sl_price
                pnl_pct = (exit_p - ep) / ep * direction
                pos_size = deposit * risk_pct / 100 / sl_p
                pnl_usdt = pos_size * pnl_pct
                deposit += pnl_usdt
                signals[-1]["exit_bar"]  = i
                signals[-1]["exit_price"]= exit_p
                signals[-1]["win"]       = win
                signals[-1]["pnl_pct"]   = pnl_pct * 100
                in_trade = False

        # ── pivot updates ─────────────────────────────────────────────────
        # Swing
        cur_sw_h = sw_lh[i]
        cur_sw_l = sw_ll[i]
        if cur_sw_h and cur_sw_h != last_sw_h:
            last_sw_h = cur_sw_h
            sw_h_cross[cur_sw_h[0]] = False
        if cur_sw_l and cur_sw_l != last_sw_l:
            last_sw_l = cur_sw_l
            sw_l_cross[cur_sw_l[0]] = False

        # Internal
        cur_in_h = in_lh[i]
        cur_in_l = in_ll[i]
        if cur_in_h and cur_in_h != last_in_h:
            last_in_h = cur_in_h
            in_h_cross[cur_in_h[0]] = False
        if cur_in_l and cur_in_l != last_in_l:
            last_in_l = cur_in_l
            in_l_cross[cur_in_l[0]] = False

        # ── structure breaks ──────────────────────────────────────────────
        sig_dir = 0
        sig_type = ""  # "BOS" or "CHoCH"

        def _check_cross_up(pivot_map, cross_map, trend_ref):
            """Returns (broke, sig_type) if close crosses above last pivot high."""
            nonlocal sw_trend, in_trend
            if not pivot_map:
                return 0, ""
            pb, pp = pivot_map
            if pb in cross_map and not cross_map[pb] and cl > pp:
                cross_map[pb] = True
                t = "CHoCH" if trend_ref < 0 else "BOS"
                return 1, t
            return 0, ""

        def _check_cross_dn(pivot_map, cross_map, trend_ref):
            if not pivot_map:
                return 0, ""
            pb, pp = pivot_map
            if pb in cross_map and not cross_map[pb] and cl < pp:
                cross_map[pb] = True
                t = "CHoCH" if trend_ref > 0 else "BOS"
                return -1, t
            return 0, ""

        # Swing crosses
        bull_sw, bst_sw = _check_cross_up(last_sw_h, sw_h_cross, sw_trend)
        bear_sw, bst_sw2= _check_cross_dn(last_sw_l, sw_l_cross, sw_trend)
        if bull_sw:
            sw_trend = 1
        if bear_sw:
            sw_trend = -1

        # Internal crosses
        bull_in, bst_in = _check_cross_up(last_in_h, in_h_cross, in_trend)
        bear_in, bst_in2= _check_cross_dn(last_in_l, in_l_cross, in_trend)
        if bull_in:
            in_trend = 1
        if bear_in:
            in_trend = -1

        # Choose signal
        for d, st in [(1, bst_sw if bull_sw else ""), (-1, bst_sw2 if bear_sw else ""),
                      (1, bst_in if bull_in else ""), (-1, bst_in2 if bear_in else "")]:
            if d == 0 or not st:
                continue
            # entry_type filter
            if entry_t == 0 and st != "BOS":
                continue
            if entry_t == 1 and st != "CHoCH":
                continue
            # HTF filter
            if htf_on and htf_dir != 0 and d != htf_dir:
                continue
            sig_dir = d
            sig_type = st
            break

        # ── confirm bar ───────────────────────────────────────────────────
        if pending_entry:
            pb, pd, pep, ptp, psl = pending_entry
            pending_entry = None
            if not in_trade:
                # entry at open of this bar
                actual_ep = op
                lev = max(1, round(risk_pct / (p["sl_pct"])))
                signals.append({"bar": i, "dir": pd, "ep": actual_ep,
                                 "tp": ptp, "sl": psl, "type": sig_type,
                                 "exit_bar": None, "exit_price": None,
                                 "win": None, "pnl_pct": None})
                in_trade  = True
                direction = pd
                ep        = actual_ep
                sl_price  = actual_ep * (1 - psl * pd) if pd == 1 else actual_ep * (1 + psl)
                tp_price  = actual_ep * (1 + ptp * pd) if pd == 1 else actual_ep * (1 - ptp)

        if sig_dir != 0 and not in_trade:
            actual_sl = sl_p
            if use_atr_sl:
                bar_atr = _atr(candles, 14, i)
                if ep_tmp := cl:
                    dyn = bar_atr * atr_sl_m / cl
                    actual_sl = max(sl_p, min(sl_p * 3, dyn))

            ep_now  = cl
            if sig_dir == 1:
                sl_now = ep_now * (1 - actual_sl)
                tp_now = ep_now * (1 + tp_p)
            else:
                sl_now = ep_now * (1 + actual_sl)
                tp_now = ep_now * (1 - tp_p)

            if conf_b:
                pending_entry = (i, sig_dir, ep_now, tp_p, actual_sl)
            else:
                signals.append({"bar": i, "dir": sig_dir, "ep": ep_now,
                                 "tp": tp_now, "sl": sl_now, "type": sig_type,
                                 "exit_bar": None, "exit_price": None,
                                 "win": None, "pnl_pct": None})
                in_trade  = True
                direction = sig_dir
                ep        = ep_now
                sl_price  = sl_now
                tp_price  = tp_now
                entry_bar = i

    # ── compute metrics ───────────────────────────────────────────────────
    closed = [s for s in signals if s["exit_bar"] is not None]
    if len(closed) < 3:
        return None

    wins    = sum(1 for s in closed if s["win"])
    losses  = len(closed) - wins
    wr      = wins / len(closed)
    avg_win = sum(s["pnl_pct"] for s in closed if s["win"]) / max(wins, 1)
    avg_los = abs(sum(s["pnl_pct"] for s in closed if not s["win"])) / max(losses, 1)
    pf      = (wins * avg_win) / max(losses * avg_los, 1e-9)

    # max drawdown
    eq_curve = [init_deposit]
    dep = init_deposit
    for s in closed:
        pos = dep * risk_pct / 100 / sl_p
        dep += pos * (s["pnl_pct"] / 100)
        eq_curve.append(dep)
    peak = eq_curve[0]
    max_dd = 0.0
    for eq in eq_curve:
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    final_dep = eq_curve[-1]
    fitness = (wr * 0.4 + min(pf, 5) / 5 * 0.3 + min(len(closed), 30) / 30 * 0.2
               - max_dd / 100 * 0.1) * (final_dep / init_deposit)

    return {
        "fitness":   round(fitness, 6),
        "wr":        round(wr * 100, 2),
        "trades":    len(closed),
        "pf":        round(pf, 3),
        "max_dd":    round(max_dd, 2),
        "equity":    round(final_dep, 2),
        "signals":   signals,
        "closed":    closed,
    }

# ══════════════════════════════════════════════════════════════════════════
# OPTIMIZER STATE
# ══════════════════════════════════════════════════════════════════════════
opt_state = {
    "running":    False,
    "symbol":     "BTC_USDT",
    "tf":         "1h",
    "days":       60,
    "risk_pct":   20.0,
    "deposit":    100.0,
    "best":       None,
    "best_params":None,
    "cycle":      0,
    "iters":      0,
    "logs":       [],
    "candles":    [],
    "candles_ts": 0,
    "alert_cfg":  {},
    "top20":      [],
}

_opt_thread  = None
_candles_lock= threading.Lock()
_state_lock  = threading.Lock()

ALERT_CFG_FILE = os.path.expanduser("~/.smc_alert_cfg.json")
BEST_FILE      = os.path.expanduser("~/.smc_best.json")

def _load_persistent():
    global opt_state
    if os.path.exists(ALERT_CFG_FILE):
        try:
            opt_state["alert_cfg"] = json.load(open(ALERT_CFG_FILE))
        except Exception:
            pass
    if os.path.exists(BEST_FILE):
        try:
            d = json.load(open(BEST_FILE))
            if d.get("params"):
                opt_state["best_params"] = d["params"]
                opt_state["best"] = d.get("metrics")
                _log(f"[start] загружен локальный best: fit={d.get('metrics',{}).get('fitness','?')}")
        except Exception:
            pass

def _save_best_local(params, metrics):
    try:
        json.dump({"params": params, "metrics": metrics}, open(BEST_FILE, "w"), ensure_ascii=False)
    except Exception:
        pass

def _log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with _state_lock:
        opt_state["logs"].append(line)
        if len(opt_state["logs"]) > 300:
            opt_state["logs"] = opt_state["logs"][-200:]

# ── Telegram/ntfy ─────────────────────────────────────────────────────────
def _send_alert(text: str):
    cfg = opt_state.get("alert_cfg", {})
    tg_token = cfg.get("tg_token", "")
    tg_chat  = cfg.get("tg_chat", "")
    ntfy_url = cfg.get("ntfy_url", "")

    if tg_token and tg_chat:
        try:
            requests.post(
                f"https://api.telegram.org/bot{tg_token}/sendMessage",
                json={"chat_id": tg_chat, "text": text, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception as e:
            _log(f"[tg] ошибка: {e}")

    if ntfy_url:
        try:
            requests.post(ntfy_url, data=text.encode(), timeout=10)
        except Exception as e:
            _log(f"[ntfy] ошибка: {e}")

# ── GitHub config sync ────────────────────────────────────────────────────
def _gh_push_best(params, metrics, symbol, tf):
    cfg = opt_state.get("alert_cfg", {})
    token = cfg.get("gh_token", "")
    repo  = cfg.get("gh_repo", "")
    if not token or not repo:
        return

    path  = f"configs/{symbol}_{tf}_best.json"
    data  = json.dumps({"params": params, "metrics": metrics,
                        "symbol": symbol, "tf": tf,
                        "ts": int(time.time())}, ensure_ascii=False, indent=2)
    b64   = base64.b64encode(data.encode()).decode()

    # get current SHA
    sha = None
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                         headers={"Authorization": f"token {token}"}, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass

    payload = {"message": f"smc best {symbol} {tf}", "content": b64}
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(f"https://api.github.com/repos/{repo}/contents/{path}",
                         headers={"Authorization": f"token {token}",
                                  "Content-Type": "application/json"},
                         data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                         timeout=15)
        if r.status_code in (200, 201):
            _log(f"[gh] pushed best → {path}")
        else:
            _log(f"[gh] push failed {r.status_code}: {r.text[:120]}")
    except Exception as e:
        _log(f"[gh] push error: {e}")

def _gh_pull_best(symbol, tf):
    cfg = opt_state.get("alert_cfg", {})
    token = cfg.get("gh_token", "")
    repo  = cfg.get("gh_repo", "")
    if not token or not repo:
        return None
    path = f"configs/{symbol}_{tf}_best.json"
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/contents/{path}",
                         headers={"Authorization": f"token {token}"}, timeout=10)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content)
    except Exception:
        pass
    return None

# ══════════════════════════════════════════════════════════════════════════
# BASIN-HOPPING OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════
def _shake(params, keys=None, n=2):
    """Встряска: рескрамблить n случайных параметров."""
    p = dict(params)
    ks = keys or list(_GRIDS.keys())
    for k in random.sample(ks, min(n, len(ks))):
        p[k] = random.choice(_GRIDS[k])
    return p

def _neighbor(params, temp=1.0):
    """Сосед: сдвигаем 1-2 параметра на один шаг."""
    p = dict(params)
    n_keys = random.randint(1, 3)
    for k in random.sample(list(_GRIDS.keys()), n_keys):
        g = _GRIDS[k]
        idx = g.index(p[k]) if p[k] in g else 0
        delta = random.choice([-1, 0, 1])
        idx = max(0, min(len(g)-1, idx + delta))
        p[k] = g[idx]
    return p

def _run_optimizer():
    global opt_state, _opt_thread

    symbol   = opt_state["symbol"]
    tf       = opt_state["tf"]
    days     = opt_state["days"]
    risk_pct = opt_state["risk_pct"]
    deposit  = opt_state["deposit"]

    _log(f"[opt] старт {symbol} {tf} {days}д риск={risk_pct}%")

    # ── fetch candles ──────────────────────────────────────────────────────
    _log(f"[opt] загружаю свечи {symbol} {tf}...")
    candles = fetch_candles(symbol, tf, days)
    if len(candles) < 50:
        _log(f"[opt] недостаточно свечей ({len(candles)}), стоп")
        opt_state["running"] = False
        return
    with _state_lock:
        opt_state["candles"] = candles
        opt_state["candles_ts"] = int(time.time())
    _log(f"[opt] загружено {len(candles)} свечей")

    # ── init ───────────────────────────────────────────────────────────────
    best_params = opt_state.get("best_params") or _rand_params()
    best_result = opt_state.get("best")
    if best_result is None:
        best_result = simulate(candles, best_params, 0, deposit, risk_pct)
        if best_result is None:
            best_params = _rand_params()
            best_result = {"fitness": -999}

    gh_data = _gh_pull_best(symbol, tf)
    if gh_data and gh_data.get("params"):
        gh_res = simulate(candles, gh_data["params"], 0, deposit, risk_pct)
        if gh_res and (best_result is None or gh_res["fitness"] > best_result.get("fitness", -999)):
            best_params = gh_data["params"]
            best_result = gh_res
            _log(f"[gh] взял GH-лучший: fit={gh_res['fitness']:.4f}")

    current_params = dict(best_params)
    current_fit    = best_result.get("fitness", -999) if best_result else -999

    T = 1.0
    T_min = 0.01
    alpha = 0.98
    stagnation = 0
    stagnation_max = 50
    cycle = 0
    top20 = []

    def _update_top20(params, metrics):
        nonlocal top20
        entry = {"params": params, "metrics": metrics}
        fit = metrics["fitness"]
        top20.append(entry)
        top20.sort(key=lambda x: -x["metrics"]["fitness"])
        # dedup by fitness
        seen_f = set()
        deduped = []
        for e in top20:
            f = round(e["metrics"]["fitness"], 4)
            if f not in seen_f:
                seen_f.add(f)
                deduped.append(e)
        top20 = deduped[:20]
        with _state_lock:
            opt_state["top20"] = top20

    if best_result and best_result.get("fitness", -999) > -999:
        _update_top20(best_params, best_result)

    _log(f"[opt] base fitness={current_fit:.4f}")

    # ── main loop ──────────────────────────────────────────────────────────
    while opt_state["running"]:
        cycle += 1
        with _state_lock:
            opt_state["cycle"] = cycle

        # re-fetch candles every 30 min
        if int(time.time()) - opt_state["candles_ts"] > 1800:
            new_c = fetch_candles(symbol, tf, days)
            if len(new_c) >= 50:
                candles = new_c
                with _state_lock:
                    opt_state["candles"] = candles
                    opt_state["candles_ts"] = int(time.time())
                _log(f"[opt] свечи обновлены ({len(candles)})")

        # Basin-Hopping: explore neighbourhood
        stagnation += 1
        if stagnation >= stagnation_max:
            stagnation = 0
            current_params = _shake(best_params, n=3)
            _log(f"[opt] встряска (stagnation={stagnation_max})")
        else:
            current_params = _neighbor(current_params, T)

        res = simulate(candles, current_params, 0, deposit, risk_pct)
        with _state_lock:
            opt_state["iters"] += 1

        if res is None:
            continue

        fit = res["fitness"]
        delta = fit - current_fit

        # Metropolis acceptance
        if delta > 0 or (T > T_min and random.random() < math.exp(delta / T)):
            current_fit    = fit
            current_params = dict(current_params)

        if fit > best_result.get("fitness", -999):
            best_result = res
            best_params = dict(current_params)
            stagnation  = 0
            with _state_lock:
                opt_state["best"]        = {k: v for k, v in res.items() if k != "signals" and k != "closed"}
                opt_state["best_params"] = best_params

            _log(f"{_C_GRN}[opt] НОВЫЙ РЕКОРД: fit={fit:.4f} WR={res['wr']}% "
                 f"сделок={res['trades']} PF={res['pf']} DD={res['max_dd']}%{_C_RST}")
            _update_top20(best_params, opt_state["best"])
            _save_best_local(best_params, opt_state["best"])
            _gh_push_best(best_params, opt_state["best"], symbol, tf)

            msg = (f"🏆 SMC NEW BEST [{symbol} {tf}]\n"
                   f"fit={fit:.4f} | WR={res['wr']}% | сделок={res['trades']}\n"
                   f"PF={res['pf']} | DD={res['max_dd']}% | eq={res['equity']:.2f}\n"
                   f"SL={current_params['sl_pct']}% TP={current_params['tp_pct']}%")
            threading.Thread(target=_send_alert, args=(msg,), daemon=True).start()

        T = max(T_min, T * alpha)

        if cycle % 100 == 0:
            _log(f"[opt] цикл {cycle} | iter={opt_state['iters']} | "
                 f"best_fit={best_result.get('fitness',-999):.4f} T={T:.4f}")

    opt_state["running"] = False
    _log("[opt] остановлен")

# ══════════════════════════════════════════════════════════════════════════
# HTTP SERVER + UI
# ══════════════════════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SMC Optimizer</title>
<style>
  :root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--sub:#8b949e;
        --grn:#3fb950;--red:#f85149;--yel:#d29922;--blue:#58a6ff;--acc:#1f6feb}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font:14px/1.5 'Segoe UI',system-ui,sans-serif;padding:12px}
  h1{font-size:18px;color:var(--blue);margin-bottom:12px}
  .row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
  label{font-size:12px;color:var(--sub)}
  input,select{background:#010409;border:1px solid var(--border);color:var(--text);
    border-radius:6px;padding:5px 8px;font-size:13px;width:100%}
  .card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;flex:1;min-width:180px}
  .card h3{font-size:13px;color:var(--sub);margin-bottom:8px}
  .metric{display:flex;justify-content:space-between;margin-bottom:4px;font-size:13px}
  .metric span:last-child{font-weight:600}
  .grn{color:var(--grn)} .red{color:var(--red)} .yel{color:var(--yel)} .blue{color:var(--blue)}
  button{background:var(--acc);border:none;color:#fff;border-radius:6px;padding:7px 16px;
    cursor:pointer;font-size:13px;transition:opacity .2s}
  button:hover{opacity:.8} button.stop{background:#b62324}
  #logs{background:#010409;border:1px solid var(--border);border-radius:6px;padding:8px;
    height:200px;overflow-y:auto;font:12px/1.6 monospace;color:var(--sub);margin-top:10px}
  table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
  th,td{padding:5px 8px;text-align:left;border-bottom:1px solid var(--border)}
  th{color:var(--sub);font-weight:500} tr:hover{background:#1c2128}
  .badge{display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px}
  .badge-grn{background:#1a3828;color:var(--grn)} .badge-red{background:#3c1212;color:var(--red)}
  #status{font-size:12px;color:var(--sub);margin-top:6px}
</style>
</head>
<body>
<h1>📊 SMC Optimizer</h1>

<div class="row">
  <div class="card" style="flex:2;min-width:300px">
    <h3>Настройки</h3>
    <div class="row">
      <div style="flex:1"><label>Символ</label><input id="symbol" value="BTC_USDT"></div>
      <div style="flex:1"><label>Таймфрейм</label>
        <select id="tf">
          <option>1m</option><option>5m</option><option>15m</option><option>30m</option>
          <option value="1h" selected>1h</option><option>4h</option><option>1d</option>
        </select>
      </div>
      <div style="flex:1"><label>Дней истории</label><input id="days" type="number" value="60" min="7" max="365"></div>
    </div>
    <div class="row">
      <div style="flex:1"><label>Депозит (USDT)</label><input id="deposit" type="number" value="100"></div>
      <div style="flex:1"><label>Риск на сделку (%)</label><input id="risk_pct" type="number" value="20" step="1"></div>
    </div>
    <div class="row" style="margin-top:4px">
      <button id="btnStart" onclick="startOpt()">▶ Старт</button>
      <button class="stop" onclick="stopOpt()">⏹ Стоп</button>
    </div>
    <div id="status">Статус: остановлен</div>
  </div>

  <div class="card" id="bestCard">
    <h3>🏆 Лучший результат</h3>
    <div id="bestBody"><span style="color:var(--sub);font-size:12px">нет данных</span></div>
  </div>
</div>

<div class="row">
  <div class="card" style="flex:1;min-width:260px">
    <h3>⚙️ Telegram / ntfy</h3>
    <div style="margin-bottom:6px"><label>TG Bot Token</label><input id="tgToken" type="password"></div>
    <div style="margin-bottom:6px"><label>TG Chat ID</label><input id="tgChat"></div>
    <div style="margin-bottom:6px"><label>ntfy URL</label><input id="ntfyUrl"></div>
    <button onclick="saveAlerts()">💾 Сохранить</button>
  </div>
  <div class="card" style="flex:1;min-width:260px">
    <h3>🐙 GitHub sync</h3>
    <div style="margin-bottom:6px"><label>GitHub Token</label><input id="ghToken" type="password"></div>
    <div style="margin-bottom:6px"><label>Репо (owner/repo)</label><input id="ghRepo" placeholder="user/smc-optimizer"></div>
    <button onclick="saveAlerts()">💾 Сохранить</button>
  </div>
</div>

<div class="card" style="margin-bottom:10px">
  <h3>🏅 Топ-20 конфигов</h3>
  <table>
    <thead><tr><th>#</th><th>Fitness</th><th>WR%</th><th>Сделок</th><th>PF</th><th>DD%</th>
      <th>SL%</th><th>TP%</th><th>Swing</th><th>Entry</th><th>HTF</th></tr></thead>
    <tbody id="top20Body"><tr><td colspan="11" style="color:var(--sub)">нет данных</td></tr></tbody>
  </table>
</div>

<div id="logs"></div>

<script>
let pollTimer=null;
let running=false;

function fmt(v,d=2){return typeof v==='number'?v.toFixed(d):v??'—'}

function startOpt(){
  const body={
    symbol:document.getElementById('symbol').value.trim().toUpperCase(),
    tf:document.getElementById('tf').value,
    days:+document.getElementById('days').value,
    deposit:+document.getElementById('deposit').value,
    risk_pct:+document.getElementById('risk_pct').value,
  };
  fetch('/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
      if(d.ok){running=true;schedulePoll();}
      else alert('Ошибка: '+d.error);
    });
}

function stopOpt(){
  fetch('/stop',{method:'POST'}).then(()=>{running=false;clearTimeout(pollTimer);
    document.getElementById('status').textContent='Статус: остановлен';});
}

function saveAlerts(){
  const cfg={
    tg_token:document.getElementById('tgToken').value,
    tg_chat:document.getElementById('tgChat').value,
    ntfy_url:document.getElementById('ntfyUrl').value,
    gh_token:document.getElementById('ghToken').value,
    gh_repo:document.getElementById('ghRepo').value,
  };
  fetch('/update_alert_cfg',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)})
    .then(r=>r.json()).then(d=>alert(d.ok?'Сохранено':'Ошибка'));
}

function schedulePoll(){pollTimer=setTimeout(poll,2000);}

function poll(){
  fetch('/status').then(r=>r.json()).then(d=>{
    document.getElementById('status').textContent=
      `Статус: ${d.running?'🟢 работает':'⚪ остановлен'} | цикл ${d.cycle} | iter ${d.iters}`;

    if(d.best){
      const b=d.best;
      document.getElementById('bestBody').innerHTML=`
        <div class="metric"><span>Fitness</span><span class="blue">${fmt(b.fitness,4)}</span></div>
        <div class="metric"><span>WR</span><span class="grn">${fmt(b.wr)}%</span></div>
        <div class="metric"><span>Сделок</span><span>${b.trades}</span></div>
        <div class="metric"><span>PF</span><span class="yel">${fmt(b.pf)}</span></div>
        <div class="metric"><span>Max DD</span><span class="red">${fmt(b.max_dd)}%</span></div>
        <div class="metric"><span>Equity</span><span>${fmt(b.equity)}</span></div>
      `;
    }

    if(d.top20&&d.top20.length){
      const rows=d.top20.map((e,i)=>{
        const m=e.metrics,p=e.params;
        const et=['BOS','CHoCH','All'][p.entry_type??2];
        return `<tr>
          <td>${i+1}</td>
          <td class="blue">${fmt(m.fitness,4)}</td>
          <td class="grn">${fmt(m.wr)}%</td>
          <td>${m.trades}</td>
          <td class="yel">${fmt(m.pf)}</td>
          <td class="red">${fmt(m.max_dd)}%</td>
          <td>${fmt(p.sl_pct)}</td><td>${fmt(p.tp_pct)}</td>
          <td>${p.swing_len}</td><td>${et}</td>
          <td>${p.htf_bias?'✓':''}</td>
        </tr>`;
      }).join('');
      document.getElementById('top20Body').innerHTML=rows;
    }

    if(d.logs&&d.logs.length){
      const el=document.getElementById('logs');
      el.innerHTML=d.logs.slice(-80).map(l=>`<div>${l}</div>`).join('');
      el.scrollTop=el.scrollHeight;
    }

    running=d.running;
    if(running) schedulePoll();
  }).catch(()=>{if(running) schedulePoll();});
}

// init poll
poll();
</script>
</body>
</html>
"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # тишина

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/status":
            with _state_lock:
                self._send_json({
                    "running": opt_state["running"],
                    "cycle":   opt_state["cycle"],
                    "iters":   opt_state["iters"],
                    "best":    opt_state["best"],
                    "top20":   opt_state["top20"],
                    "logs":    opt_state["logs"][-80:],
                })
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}

        if path == "/start":
            global _opt_thread
            if opt_state["running"]:
                self._send_json({"ok": False, "error": "уже запущен"})
                return
            with _state_lock:
                opt_state["running"]    = True
                opt_state["symbol"]     = data.get("symbol", opt_state["symbol"])
                opt_state["tf"]         = data.get("tf",     opt_state["tf"])
                opt_state["days"]       = int(data.get("days", opt_state["days"]))
                opt_state["risk_pct"]   = float(data.get("risk_pct", opt_state["risk_pct"]))
                opt_state["deposit"]    = float(data.get("deposit",  opt_state["deposit"]))
                opt_state["cycle"]      = 0
                opt_state["iters"]      = 0
                opt_state["logs"]       = []
            _opt_thread = threading.Thread(target=_run_optimizer, daemon=True)
            _opt_thread.start()
            self._send_json({"ok": True})
            return

        if path == "/stop":
            opt_state["running"] = False
            self._send_json({"ok": True})
            return

        if path == "/update_alert_cfg":
            with _state_lock:
                opt_state["alert_cfg"].update(data)
            try:
                json.dump(opt_state["alert_cfg"], open(ALERT_CFG_FILE, "w"), ensure_ascii=False)
            except Exception:
                pass
            self._send_json({"ok": True})
            return

        self._send_json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

# ══════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════
PORT = 8765

if __name__ == "__main__":
    _load_persistent()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    print(f"{_C_GRN}[SMC Optimizer] http://localhost:{PORT}{_C_RST}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[exit]", flush=True)
