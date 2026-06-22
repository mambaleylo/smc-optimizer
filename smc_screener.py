#!/usr/bin/env python3
"""
SMC Optimizer v1.3
- v1.0: первая версия. Оптимизатор параметров Smart Money Concepts (SMC) сигналов
  по свечам Gate.io Futures. Метод: Basin Hopping + Metropolis. TP/SL как в WickFill.
  Параметры: swing_len (размер свинга), internal_len (внутренний свинг), ob_filter
  (фильтр ордер-блоков по ATR), ob_mitigation (Close/HighLow), fvg_threshold,
  sl_pct, tp_pct. Фитнесс: winrate × profit_factor × log(trades+1) / max_drawdown.
  HTTP-сервер на :8765, браузерный UI с живым графиком, топ-20 конфигов,
  автосохранение лучшего на GitHub, Telegram/ntfy алерты.
- v1.1: фикс "мешанины" на графике. Причины было две: (1) /chart_data игнорировал
  9 из 12 параметров лучшего конфига (internal_len, ob_filter, ob_mitigation,
  fvg_enabled, fvg_threshold, choch_only, use_internal, min_ob_size,
  require_fvg_confirm) — они были жёстко зашиты дефолтами и не приходили с
  фронта даже после "Применить лучший"; (2) зоны OB/FVG на графике считались
  отдельной, упрощённой JS-копией SMC-логики (rebuildInd), а не той же
  _simulate(), что и оптимизатор, и рисовались БЕЗ инвалидации — каждая зона
  тянулась на всю видимую ширину графика, поэтому сотни зон со свингов
  накладывались друг на друга сплошными полосами. Теперь зоны OB/FVG
  считает _simulate() с реальными параметрами конфига и передаёт на фронт
  с end_i (где зона инвалидируется ценой); фронт рисует зону только на её
  фактическом интервале i→end_i.
- v1.2: живой монитор сигналов + Telegram-алерты (по аналогии с WickFill).
  _simulate() при _collect=True теперь также возвращает текущую ОТКРЫТУЮ
  (ещё не закрытую TP/SL) позицию как сигнал без exit_i — раньше она была
  не видна ни графику, ни монитору до своего закрытия. Убран ранний return
  None при <5 закрытых сделках для _collect-вызовов (графику и монитору
  нужен результат даже при малой исторической выборке). Новый фоновый поток
  _chart_monitor_loop раз в бар (с привязкой к закрытию свечи по ТФ)
  пересчитывает _simulate() на свежих свечах и, если последний сигнал
  (entry-таймстемп) сменился — шлёт компактный алерт в Telegram/ntfy.
  При первом запуске монитор "вооружается" без алерта на уже существующий
  сигнал, чтобы не спамить историей. Эндпоинты: POST /chart_monitor_start
  (sym, tf, days, params), POST /chart_monitor_stop, GET
  /chart_monitor_status. На фронте — кнопка "🔔 Алерты" в баре графика и
  автообновление графика раз в ТФ (loadChart(true) по таймеру, с сохранением
  позиции/масштаба просмотра по времени свечи, а не по индексу).
- v1.3: настройка алертов через UI (по аналогии с WickFill). Поля TG Token /
  TG Chat ID / ntfy URL в сайдбаре, сохраняются в ~/.smc_alert_cfg.json
  (приоритет над env при старте) и подхватываются при перезапуске — больше
  не нужно экспортировать env-переменные руками каждый раз. Кнопка "Тест"
  реально проверяет доставку: для Telegram разбирает поле "ok" в ответе API
  (а не просто фиксирует факт отправки HTTP-запроса), для ntfy — код ответа.
  Эндпоинты: GET /alert_cfg, POST /alert_cfg, POST /alert_test.
"""
import os, sys, json, time, math, random, threading, base64, hashlib
import http.server, urllib.request, urllib.parse
from functools import lru_cache

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

APP_VERSION  = "1.3"
GATE_API     = "https://fx-api.gateio.ws/api/v4"
PORT         = 8765
GH_REPO      = os.environ.get("GH_REPO", "mambaleylo/smc-optimizer")
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
TG_TOKEN     = os.environ.get("TG_TOKEN", "")
TG_CHAT      = os.environ.get("TG_CHAT", "")
NTFY_URL     = os.environ.get("NTFY_URL", "")
ALERT_CFG_PATH = os.path.expanduser("~/.smc_alert_cfg.json")

_C_GRN = "\033[92m"; _C_YEL = "\033[93m"; _C_RED = "\033[91m"
_C_GREY = "\033[90m"; _C_RST = "\033[0m"

TF_SECONDS = {
    "1m":60,"5m":300,"15m":900,"30m":1800,
    "1h":3600,"4h":14400,"1d":86400
}

# ─── Пространство параметров ────────────────────────────────────────────────
PARAM_SPACE = {
    "sl_pct":        {"min":0.3,  "max":2.0,  "step":0.05, "type":"float"},
    "tp_pct":        {"min":0.5,  "max":4.0,  "step":0.05, "type":"float"},
    "swing_len":     {"min":10,   "max":100,  "step":5,    "type":"int"},
    "internal_len":  {"min":3,    "max":15,   "step":1,    "type":"int"},
    "ob_filter":     {"values":["atr","range"],             "type":"cat"},
    "ob_mitigation": {"values":["close","highlow"],         "type":"cat"},
    "fvg_enabled":   {"values":[True, False],               "type":"bool"},
    "fvg_threshold": {"min":0.0,  "max":0.5,  "step":0.05, "type":"float"},
    "choch_only":    {"values":[False, True],               "type":"bool"},
    "use_internal":  {"values":[True, False],               "type":"bool"},
    "min_ob_size":   {"min":0.5,  "max":3.0,  "step":0.1,  "type":"float"},
    "require_fvg_confirm": {"values":[False,True],          "type":"bool"},
}

# ─── Глобальное состояние ───────────────────────────────────────────────────
opt_lock   = threading.Lock()
opt_state  = {
    "running": False, "logs": [], "best": None, "top20": [],
    "cycle": 0, "trials": 0, "progress": 0,
    "symbol": "BTC_USDT", "tf": "15m", "days": 30,
    "sl_pct": 0.6, "tp_pct": 1.2, "risk_pct": 2.0,
    "chart": None, "fetch_pct": 0, "logs_dropped": 0,
}
_stop_flag = threading.Event()
_opt_thread = None

# Монитор графика: раз в бар проверяет, не появился ли новый сигнал,
# и шлёт алерт в Telegram (по аналогии с WickFill)
chart_mon_lock  = threading.Lock()
chart_mon_state = {
    "active": False, "symbol": None, "tf": None, "days": 30,
    "params": None, "armed": False,
    "last_entry_ts": None, "last_dir": None, "last_check": 0,
}
_chart_mon_stop   = threading.Event()
_chart_mon_thread = None

def _ts():
    return time.strftime("[%H:%M:%S]")

def olog(msg):
    with opt_lock:
        opt_state["logs"].append({"ts": time.strftime("%H:%M:%S"), "msg": msg})
        if len(opt_state["logs"]) > 500:
            opt_state["logs"] = opt_state["logs"][-300:]
            opt_state["logs_dropped"] = opt_state.get("logs_dropped",0) + 200

# ─── Gate.io fetch ──────────────────────────────────────────────────────────
def _fetch_candles(symbol, tf, days):
    interval_sec = TF_SECONDS.get(tf, 3600)
    now   = int(time.time())
    since = now - days * 86400
    LIMIT = 999
    all_candles = []
    current_from = since
    while current_from < now:
        try:
            r = requests.get(f"{GATE_API}/futures/usdt/candlesticks",
                params={"contract":symbol,"interval":tf,"from":current_from,"limit":LIMIT},
                timeout=15)
            if r.status_code != 200:
                time.sleep(5); continue
            raw = r.json()
            if not raw: break
            batch = []
            for c in raw:
                t = int(c.get("t",0))
                batch.append({
                    "t": t, "open": float(c.get("o",0)),
                    "high": float(c.get("h",0)), "low": float(c.get("l",0)),
                    "close": float(c.get("c",0)), "vol": float(c.get("v",0))
                })
            if not batch: break
            all_candles.extend(batch)
            last_t = batch[-1]["t"]
            if last_t >= now - interval_sec: break
            current_from = last_t + interval_sec
            time.sleep(0.12)
        except Exception as e:
            olog(f"fetch error: {e}")
            time.sleep(5)
    seen = set()
    result = []
    for c in sorted(all_candles, key=lambda x: x["t"]):
        if c["t"] not in seen:
            seen.add(c["t"]); result.append(c)
    return result

# ─── Индикаторы ─────────────────────────────────────────────────────────────
def _ema(arr, period):
    result = [None]*len(arr)
    if len(arr) < period: return result
    k = 2.0/(period+1)
    s = sum(arr[:period])/period
    result[period-1] = s
    for i in range(period, len(arr)):
        s = arr[i]*k + s*(1-k)
        result[i] = s
    return result

def _atr(candles, period=14):
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]["high"]; l = candles[i]["low"]; pc = candles[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    result = [None]*len(candles)
    if len(trs) < period: return result
    s = sum(trs[:period])/period
    result[period] = s
    for i in range(period+1, len(candles)):
        s = (s*(period-1) + trs[i-1])/period
        result[i] = s
    return result

def _pivot_high(candles, length):
    """Возвращает массив pivot high цен (None если не пивот)"""
    n = len(candles)
    result = [None]*n
    for i in range(length, n-length):
        h = candles[i]["high"]
        if all(candles[j]["high"] < h for j in range(i-length, i)) and \
           all(candles[j]["high"] < h for j in range(i+1, i+length+1)):
            result[i] = h
    return result

def _pivot_low(candles, length):
    """Возвращает массив pivot low цен (None если не пивот)"""
    n = len(candles)
    result = [None]*n
    for i in range(length, n-length):
        l = candles[i]["low"]
        if all(candles[j]["low"] > l for j in range(i-length, i)) and \
           all(candles[j]["low"] > l for j in range(i+1, i+length+1)):
            result[i] = l
    return result

# ─── SMC симуляция ──────────────────────────────────────────────────────────
def _simulate(candles, p, sl_pct=None, tp_pct=None, risk_pct=2.0,
              init_deposit=1000.0, _collect=False):
    """
    Симуляция SMC стратегии по параметрам p.
    Возвращает dict с метриками или None если мало данных.
    """
    if sl_pct is None: sl_pct = p["sl_pct"]
    if tp_pct is None: tp_pct = p["tp_pct"]

    swing_len     = int(p["swing_len"])
    internal_len  = int(p.get("internal_len", 5))
    ob_filter     = p.get("ob_filter","atr")
    ob_mit        = p.get("ob_mitigation","highlow")
    fvg_enabled   = p.get("fvg_enabled", True)
    fvg_thr       = p.get("fvg_threshold", 0.1)
    choch_only    = p.get("choch_only", False)
    use_internal  = p.get("use_internal", True)
    min_ob_size   = p.get("min_ob_size", 1.0)
    req_fvg       = p.get("require_fvg_confirm", False)

    n = len(candles)
    min_bars = swing_len*2 + 20
    if n < min_bars: return None

    # ATR
    atr_arr = _atr(candles, 200)
    cum_tr = 0.0; cum_atr_range = []
    for i in range(1, n):
        h=candles[i]["high"]; l=candles[i]["low"]; pc=candles[i-1]["close"]
        cum_tr += max(h-l, abs(h-pc), abs(l-pc))
        cum_atr_range.append(cum_tr / i)

    # Пивоты
    ph = _pivot_high(candles, swing_len)
    pl = _pivot_low(candles, swing_len)
    if use_internal:
        iph = _pivot_high(candles, internal_len)
        ipl = _pivot_low(candles, internal_len)
    else:
        iph = [None]*n; ipl = [None]*n

    # Order blocks: ищем последний бычий/медвежий OB
    # Бычий OB = последняя медвежья свеча перед пробитием вверх swing high
    # Медвежий OB = последняя бычья свеча перед пробитием вниз swing low

    # Определяем swing trend и CHoCH/BOS
    sw_highs = []  # (i, price)
    sw_lows  = []  # (i, price)
    for i in range(n):
        if ph[i] is not None: sw_highs.append((i, ph[i]))
        if pl[i] is not None: sw_lows.append((i, pl[i]))

    # FVG детекция
    fvg_bull = []  # (i, low, high) бычий FVG: low[i] > high[i-2]
    fvg_bear = []  # (i, high, low) медвежий FVG: high[i] < low[i-2]
    for i in range(2, n):
        gap_b = candles[i]["low"] - candles[i-2]["high"]
        gap_s = candles[i-2]["low"] - candles[i]["high"]
        atr_val = atr_arr[i] or 0.001
        if gap_b > fvg_thr * atr_val:
            fvg_bull.append((i, candles[i-2]["high"], candles[i]["low"]))
        if gap_s > fvg_thr * atr_val:
            fvg_bear.append((i, candles[i]["high"], candles[i-2]["low"]))

    # Основной бэктест
    equity    = init_deposit
    trades    = []
    signals   = []  # для _collect
    in_trade  = False
    trade_dir = None  # "long" / "short"
    entry_px  = 0.0
    sl_price  = 0.0
    tp_price  = 0.0
    entry_i   = 0

    # Swing trend state
    last_sh = None  # последний swing high (i, price)
    last_sl_sw = None  # последний swing low (i, price)
    sw_trend = 0   # +1 bull, -1 bear

    # OB storage: list of {"dir":+1/-1, "hi":, "lo":, "i":}
    bull_obs = []
    bear_obs = []
    # Полная (некапнутая) история OB для отрисовки на графике
    coll_bull_obs = []
    coll_bear_obs = []

    for i in range(swing_len*2, n):
        c = candles[i]
        high_i = c["high"]; low_i = c["low"]
        close_i = c["close"]; open_i = c["open"]

        # Update swing highs/lows
        if ph[i] is not None:
            # New swing high
            if last_sh is None or ph[i] > last_sh[1]:
                if last_sh is not None and sw_trend == -1:
                    # CHoCH вверх или BOS вверх
                    pass
                last_sh = (i, ph[i])
            # Медвежий OB перед этим высоким: ищем последнюю бычью свечу до i
            ob_hi_bar = i - 1
            while ob_hi_bar > max(0, i-swing_len):
                ci = candles[ob_hi_bar]
                is_bullish = ci["close"] > ci["open"]
                size_ok = (ci["high"] - ci["low"]) >= min_ob_size * (atr_arr[i] or 0.001)
                if is_bullish and size_ok:
                    bear_obs.append({"dir":-1,"hi":ci["high"],"lo":ci["low"],"i":ob_hi_bar})
                    if len(bear_obs) > 10: bear_obs.pop(0)
                    if _collect:
                        coll_bear_obs.append({"hi":ci["high"],"lo":ci["low"],"i":ob_hi_bar})
                    break
                ob_hi_bar -= 1

        if pl[i] is not None:
            if last_sl_sw is None or pl[i] < last_sl_sw[1]:
                last_sl_sw = (i, pl[i])
            # Бычий OB перед этим низким: последняя медвежья свеча до i
            ob_lo_bar = i - 1
            while ob_lo_bar > max(0, i-swing_len):
                ci = candles[ob_lo_bar]
                is_bearish = ci["close"] < ci["open"]
                size_ok = (ci["high"] - ci["low"]) >= min_ob_size * (atr_arr[i] or 0.001)
                if is_bearish and size_ok:
                    bull_obs.append({"dir":+1,"hi":ci["high"],"lo":ci["low"],"i":ob_lo_bar})
                    if len(bull_obs) > 10: bull_obs.pop(0)
                    if _collect:
                        coll_bull_obs.append({"hi":ci["high"],"lo":ci["low"],"i":ob_lo_bar})
                    break
                ob_lo_bar -= 1

        # Swing trend update: BOS/CHoCH
        if last_sh is not None and close_i > last_sh[1]:
            sw_trend = +1
        if last_sl_sw is not None and close_i < last_sl_sw[1]:
            sw_trend = -1

        # Управление открытой позицией
        if in_trade:
            if trade_dir == "long":
                sl_src = low_i if ob_mit == "highlow" else close_i
                tp_src = high_i
                if sl_src <= sl_price:
                    pnl_pct = -sl_pct
                    pnl = equity * (risk_pct/100.0) * (-1.0)
                    equity += pnl
                    trades.append({"dir":"long","entry":entry_px,"exit":sl_price,
                                   "pnl_pct":pnl_pct,"pnl":pnl,"win":False,"i":i})
                    if _collect:
                        signals.append({"dir":"long","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":False})
                    in_trade = False
                elif tp_src >= tp_price:
                    rr = tp_pct / sl_pct
                    pnl = equity * (risk_pct/100.0) * rr
                    equity += pnl
                    trades.append({"dir":"long","entry":entry_px,"exit":tp_price,
                                   "pnl_pct":tp_pct,"pnl":pnl,"win":True,"i":i})
                    if _collect:
                        signals.append({"dir":"long","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":True})
                    in_trade = False
            else:  # short
                sl_src = high_i if ob_mit == "highlow" else close_i
                tp_src = low_i
                if sl_src >= sl_price:
                    pnl = equity * (risk_pct/100.0) * (-1.0)
                    equity += pnl
                    trades.append({"dir":"short","entry":entry_px,"exit":sl_price,
                                   "pnl_pct":-sl_pct,"pnl":pnl,"win":False,"i":i})
                    if _collect:
                        signals.append({"dir":"short","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":False})
                    in_trade = False
                elif tp_src <= tp_price:
                    rr = tp_pct / sl_pct
                    pnl = equity * (risk_pct/100.0) * rr
                    equity += pnl
                    trades.append({"dir":"short","entry":entry_px,"exit":tp_price,
                                   "pnl_pct":tp_pct,"pnl":pnl,"win":True,"i":i})
                    if _collect:
                        signals.append({"dir":"short","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":True})
                    in_trade = False
            if in_trade: continue

        # Сигнал входа — ищем возврат цены в OB
        sig_dir = None
        entry_candidate = None

        # Бычий сигнал: цена возвращается в бычий OB снизу при бычьем тренде (или CHoCH)
        for ob in reversed(bull_obs):
            in_ob = low_i <= ob["hi"] and high_i >= ob["lo"]
            trend_ok = (sw_trend == +1) or (not choch_only)
            if in_ob and trend_ok:
                # FVG подтверждение
                fvg_ok = True
                if req_fvg and fvg_enabled:
                    fvg_ok = any(f[0] > ob["i"] and f[0] <= i and
                                  f[1] <= ob["hi"] and f[2] >= ob["lo"]
                                  for f in fvg_bull)
                if fvg_ok:
                    sig_dir = "long"
                    entry_candidate = ob
                    break

        if sig_dir is None:
            for ob in reversed(bear_obs):
                in_ob = high_i >= ob["lo"] and low_i <= ob["hi"]
                trend_ok = (sw_trend == -1) or (not choch_only)
                if in_ob and trend_ok:
                    fvg_ok = True
                    if req_fvg and fvg_enabled:
                        fvg_ok = any(f[0] > ob["i"] and f[0] <= i and
                                      f[1] <= ob["hi"] and f[2] >= ob["lo"]
                                      for f in fvg_bear)
                    if fvg_ok:
                        sig_dir = "short"
                        entry_candidate = ob
                        break

        if sig_dir is not None and entry_candidate is not None:
            entry_px  = close_i
            if sig_dir == "long":
                sl_price = entry_px * (1 - sl_pct/100)
                tp_price = entry_px * (1 + tp_pct/100)
            else:
                sl_price = entry_px * (1 + sl_pct/100)
                tp_price = entry_px * (1 - tp_pct/100)
            in_trade  = True
            trade_dir = sig_dir
            entry_i   = i

    # Метрики
    if len(trades) < 5 and not _collect:
        return None
    if len(trades) == 0:
        wr = 0.0; pf = 0.0; max_dd = 0.001
    else:
        wins   = [t for t in trades if t["win"]]
        losses = [t for t in trades if not t["win"]]
        wr     = len(wins)/len(trades)
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss   = abs(sum(t["pnl"] for t in losses)) or 1e-9
        pf   = gross_profit / gross_loss
        # Max drawdown
        eq = init_deposit
        peak = eq; max_dd = 0.0
        for t in trades:
            eq += t["pnl"]
            if eq > peak: peak = eq
            dd = (peak - eq)/peak if peak > 0 else 0
            if dd > max_dd: max_dd = dd
        max_dd = max(max_dd, 0.001)
    total_return = (equity - init_deposit)/init_deposit*100

    result = {
        "trades": len(trades), "winrate": round(wr*100,1),
        "profit_factor": round(pf,3), "max_dd": round(max_dd*100,2),
        "total_return": round(total_return,2), "equity": round(equity,2),
        "fitness": 0.0,
    }
    # Fitness: WR × PF × log(trades) / (1+max_dd) — штраф за просадку
    fitness = (wr * min(pf,5.0) * math.log(len(trades)+1)) / (1 + max_dd)
    result["fitness"] = round(fitness, 6)

    if _collect:
        def _box_end(items, kind):
            out = []
            for ob in items:
                oi, hi, lo = ob["i"], ob["hi"], ob["lo"]
                end_i = n - 1
                for j in range(oi+1, n):
                    cj = candles[j]["close"]
                    if kind == "bull" and cj < lo:
                        end_i = j; break
                    if kind == "bear" and cj > hi:
                        end_i = j; break
                out.append({"i": oi, "hi": hi, "lo": lo, "end_i": end_i})
            return out
        def _fvg_end(items, kind):
            out = []
            for it in items:
                fi, lo, hi = it[0], it[1], it[2]
                end_i = n - 1
                for j in range(fi+1, n):
                    cj = candles[j]["close"]
                    if kind == "bull" and cj < lo:
                        end_i = j; break
                    if kind == "bear" and cj > hi:
                        end_i = j; break
                out.append({"i": fi, "hi": hi, "lo": lo, "end_i": end_i})
            return out
        result["signals"]  = signals
        if in_trade:
            # Открытая (ещё не закрытая) позиция — без неё монитор и график
            # не видят текущий активный сигнал до его TP/SL
            result["signals"] = signals + [{
                "dir": trade_dir, "entry_i": entry_i, "entry": entry_px,
                "tp": tp_price, "sl": sl_price, "open": True
            }]
        result["candles"]  = candles
        result["bull_obs"] = _box_end(coll_bull_obs, "bull")
        result["bear_obs"] = _box_end(coll_bear_obs, "bear")
        result["fvg_bull"] = _fvg_end(fvg_bull, "bull")
        result["fvg_bear"] = _fvg_end(fvg_bear, "bear")

    return result

# ─── Параметры: random / shake ───────────────────────────────────────────────
def _random_params():
    p = {}
    for k, sp in PARAM_SPACE.items():
        if sp["type"] == "float":
            steps = round((sp["max"]-sp["min"])/sp["step"])
            p[k] = round(sp["min"] + random.randint(0,steps)*sp["step"], 4)
        elif sp["type"] == "int":
            steps = (sp["max"]-sp["min"])//sp["step"]
            p[k] = int(sp["min"] + random.randint(0,steps)*sp["step"])
        elif sp["type"] == "cat":
            p[k] = random.choice(sp["values"])
        elif sp["type"] == "bool":
            p[k] = random.choice(sp["values"])
    return p

def _shake(p, strength=0.3):
    q = dict(p)
    keys = list(PARAM_SPACE.keys())
    n_shake = max(1, int(len(keys)*strength))
    for k in random.sample(keys, n_shake):
        sp = PARAM_SPACE[k]
        if sp["type"] == "float":
            steps = round((sp["max"]-sp["min"])/sp["step"])
            q[k] = round(sp["min"] + random.randint(0,steps)*sp["step"], 4)
        elif sp["type"] == "int":
            steps = (sp["max"]-sp["min"])//sp["step"]
            q[k] = int(sp["min"] + random.randint(0,steps)*sp["step"])
        elif sp["type"] in ("cat","bool"):
            q[k] = random.choice(sp["values"])
    return q

def _neighbour(p, temp=0.1):
    """Малое отклонение одного-двух параметров"""
    q = dict(p)
    keys = [k for k,sp in PARAM_SPACE.items() if sp["type"] in ("float","int")]
    for k in random.sample(keys, min(2, len(keys))):
        sp = PARAM_SPACE[k]
        if sp["type"] == "float":
            delta = random.choice([-2,-1,1,2]) * sp["step"]
            q[k] = round(max(sp["min"], min(sp["max"], p[k]+delta)), 4)
        elif sp["type"] == "int":
            delta = random.choice([-2,-1,1,2]) * sp["step"]
            q[k] = int(max(sp["min"], min(sp["max"], p[k]+delta)))
    return q

# ─── GitHub ─────────────────────────────────────────────────────────────────
def _gh_request(method, path, body=None):
    if not GH_TOKEN: return None
    url = f"https://api.github.com/repos/{GH_REPO}/{path}"
    headers = {"Authorization":f"token {GH_TOKEN}",
               "Content-Type":"application/json","Accept":"application/vnd.github.v3+json"}
    try:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        olog(f"gh error {method} {path}: {e}")
        return None

def _gh_save_best(best):
    if not GH_TOKEN: return
    sym = opt_state["symbol"].replace("/","_"); tf = opt_state["tf"]
    fname = f"configs/best_{sym}_{tf}.json"
    existing = _gh_request("GET", f"contents/{fname}")
    sha = existing.get("sha","") if existing else ""
    content_b64 = base64.b64encode(json.dumps(best, ensure_ascii=False, indent=2).encode()).decode()
    body = {"message":f"best config {sym} {tf}","content":content_b64}
    if sha: body["sha"] = sha
    _gh_request("PUT", f"contents/{fname}", body)

# ─── Telegram / ntfy ────────────────────────────────────────────────────────
def _send_alert(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id":TG_CHAT,"text":msg,"parse_mode":"HTML"}, timeout=8)
        except: pass
    if NTFY_URL:
        try:
            requests.post(NTFY_URL, data=msg.encode(), timeout=8)
        except: pass

def _load_alert_cfg():
    """Подхватывает сохранённые TG/ntfy настройки из файла (приоритет над env)."""
    global TG_TOKEN, TG_CHAT, NTFY_URL
    try:
        with open(ALERT_CFG_PATH, "r") as f:
            cfg = json.load(f)
        TG_TOKEN = cfg.get("tg_token", TG_TOKEN) or TG_TOKEN
        TG_CHAT  = cfg.get("tg_chat",  TG_CHAT)  or TG_CHAT
        NTFY_URL = cfg.get("ntfy_url", NTFY_URL) or NTFY_URL
    except FileNotFoundError:
        pass
    except Exception as e:
        olog(f"⚠ Не удалось прочитать {ALERT_CFG_PATH}: {e}")

def _save_alert_cfg():
    try:
        with open(ALERT_CFG_PATH, "w") as f:
            json.dump({"tg_token": TG_TOKEN, "tg_chat": TG_CHAT, "ntfy_url": NTFY_URL}, f)
    except Exception as e:
        olog(f"⚠ Не удалось сохранить {ALERT_CFG_PATH}: {e}")

def _test_alert():
    """Шлёт тестовое уведомление и честно проверяет, дошло ли оно."""
    if not ((TG_TOKEN and TG_CHAT) or NTFY_URL):
        return False, "Не заданы TG_TOKEN+TG_CHAT или NTFY_URL"
    msg = "✅ SMC Optimizer: тестовое уведомление. Если ты это видишь — алерты настроены верно."
    ok_any, errs = False, []
    if TG_TOKEN and TG_CHAT:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                json={"chat_id":TG_CHAT,"text":msg,"parse_mode":"HTML"}, timeout=8)
            j = r.json()
            if j.get("ok"):
                ok_any = True
            else:
                errs.append("Telegram: " + j.get("description","неизвестная ошибка"))
        except Exception as e:
            errs.append(f"Telegram: {e}")
    if NTFY_URL:
        try:
            r = requests.post(NTFY_URL, data=msg.encode(), timeout=8)
            if r.status_code < 300:
                ok_any = True
            else:
                errs.append(f"ntfy: HTTP {r.status_code}")
        except Exception as e:
            errs.append(f"ntfy: {e}")
    return ok_any, ("; ".join(errs) if errs else None)

def _fmt_px(v):
    if v is None: return "—"
    if v >= 100:  return f"{v:.2f}"
    if v >= 1:    return f"{v:.4f}"
    return f"{v:.6f}".rstrip("0").rstrip(".")

# ─── Монитор графика (live-сигналы) ────────────────────────────────────────
def _chart_monitor_loop(sym, tf, days, p):
    tf_sec = TF_SECONDS.get(tf, 900)
    olog(f"🔔 Монитор графика запущен: {sym} {tf}")
    while not _chart_mon_stop.is_set():
        try:
            candles = _fetch_candles(sym, tf, days)
            if candles and len(candles) > 50:
                result = _simulate(candles, p, sl_pct=p.get("sl_pct"),
                                    tp_pct=p.get("tp_pct"), _collect=True)
                with chart_mon_lock:
                    chart_mon_state["last_check"] = time.time()
                if result:
                    sigs = result.get("signals") or []
                    if sigs:
                        sig = sigs[-1]
                        entry_ts = candles[sig["entry_i"]]["t"]
                        new_sig = None
                        with chart_mon_lock:
                            if not chart_mon_state["armed"]:
                                # Первый запуск — просто запоминаем текущий
                                # сигнал, чтобы не спамить алертом по уже
                                # имеющейся (старой) сделке
                                chart_mon_state["armed"]         = True
                                chart_mon_state["last_entry_ts"] = entry_ts
                                chart_mon_state["last_dir"]      = sig["dir"]
                            elif entry_ts != chart_mon_state["last_entry_ts"]:
                                chart_mon_state["last_entry_ts"] = entry_ts
                                chart_mon_state["last_dir"]      = sig["dir"]
                                new_sig = sig
                        if new_sig:
                            emoji = "🟢" if new_sig["dir"] == "long" else "🔴"
                            dirru = "LONG" if new_sig["dir"] == "long" else "SHORT"
                            _send_alert(
                                f"{emoji} <b>{sym} {tf}</b> — новый сигнал {dirru}\n"
                                f"Entry {_fmt_px(new_sig['entry'])} | "
                                f"TP {_fmt_px(new_sig['tp'])} | "
                                f"SL {_fmt_px(new_sig['sl'])}"
                            )
                            olog(f"🔔 Новый сигнал {sym} {tf} {dirru} "
                                 f"entry={_fmt_px(new_sig['entry'])}")
        except Exception as e:
            olog(f"⚠ Монитор графика: {e}")
        # Спим до следующего закрытия бара (+небольшой запас)
        now = time.time()
        sleep_for = tf_sec - (now % tf_sec) + 3
        _chart_mon_stop.wait(timeout=max(5, sleep_for))
    olog("🔕 Монитор графика остановлен")

# ─── Основной оптимизатор ───────────────────────────────────────────────────
def run_optimizer():
    global _opt_thread
    sym   = opt_state["symbol"]
    tf    = opt_state["tf"]
    days  = int(opt_state["days"])
    sl_p  = float(opt_state["sl_pct"])
    tp_p  = float(opt_state["tp_pct"])
    risk  = float(opt_state["risk_pct"])

    olog(f"▶ Старт | {sym} {tf} {days}д | SL={sl_p}% TP={tp_p}%")
    candles = _fetch_candles(sym, tf, days)
    if not candles or len(candles) < 100:
        olog("❌ Мало свечей, остановка"); return
    olog(f"✔ Загружено {len(candles)} свечей")

    best_params  = _random_params()
    best_params["sl_pct"] = sl_p; best_params["tp_pct"] = tp_p
    best_result  = _simulate(candles, best_params, sl_pct=sl_p, tp_pct=tp_p, risk_pct=risk)
    best_fit     = best_result["fitness"] if best_result else 0.0
    top20        = []
    cycle        = 0
    TEMP_START   = 1.0

    with opt_lock:
        opt_state["top20"] = top20
        opt_state["best"]  = None

    while not _stop_flag.is_set():
        cycle += 1
        temp = TEMP_START * math.exp(-0.05 * cycle)
        with opt_lock: opt_state["cycle"] = cycle

        # Несколько стартовых точек за цикл
        starts = [_shake(best_params, 0.4) if best_params else _random_params(),
                  _random_params()]
        if len(top20) > 2:
            starts.append(_shake(random.choice(top20)["params"], 0.3))

        for start_p in starts:
            if _stop_flag.is_set(): break
            current_p = start_p
            current_r = _simulate(candles, current_p, risk_pct=risk)
            current_fit = current_r["fitness"] if current_r else 0.0

            # Локальный поиск
            for step in range(60):
                if _stop_flag.is_set(): break
                with opt_lock:
                    opt_state["trials"] = opt_state.get("trials",0)+1
                    opt_state["progress"] = int(step/60*100)

                neighbour_p = _neighbour(current_p)
                neighbour_r = _simulate(candles, neighbour_p, risk_pct=risk)
                if not neighbour_r: continue
                nfit = neighbour_r["fitness"]
                delta = nfit - current_fit
                if delta > 0 or random.random() < math.exp(delta / max(temp, 0.001)):
                    current_p   = neighbour_p
                    current_fit = nfit
                    current_r   = neighbour_r

                    # Обновляем топ-20
                    with opt_lock:
                        top20 = opt_state["top20"]
                        entry = {"params": current_p, "result": current_r}
                        top20 = [e for e in top20 if abs(e["result"]["fitness"]-nfit)>0.001]
                        top20.append(entry)
                        top20.sort(key=lambda x: x["result"]["fitness"], reverse=True)
                        opt_state["top20"] = top20[:20]

                    if nfit > best_fit:
                        best_fit    = nfit
                        best_params = current_p
                        best_result = current_r
                        with opt_lock:
                            opt_state["best"] = {"params":current_p,"result":current_r}
                        olog(f"🏆 Цикл {cycle} шаг {step} | "
                             f"WR={current_r['winrate']}% PF={current_r['profit_factor']} "
                             f"DD={current_r['max_dd']}% T={current_r['trades']} "
                             f"fit={nfit:.4f} | "
                             f"SL={current_p['sl_pct']}% TP={current_p['tp_pct']}% "
                             f"swing={current_p['swing_len']}")
                        threading.Thread(target=_gh_save_best,
                            args=({"params":current_p,"result":current_r},), daemon=True).start()
                        _send_alert(
                            f"🏆 SMC {sym} {tf} — новый лучший\n"
                            f"WR={current_r['winrate']}% PF={current_r['profit_factor']} "
                            f"DD={current_r['max_dd']}% Trades={current_r['trades']}\n"
                            f"SL={current_p['sl_pct']}% TP={current_p['tp_pct']}% "
                            f"swing={current_p['swing_len']}"
                        )

        olog(f"Цикл {cycle} завершён | best fit={best_fit:.4f}")

    olog("⏹ Остановлено")
    with opt_lock: opt_state["running"] = False

# ─── HTTP сервер ─────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SMC Optimizer</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#e0e0e0;font-family:'JetBrains Mono',monospace,sans-serif;font-size:13px}
.topbar{background:#111;border-bottom:1px solid #222;padding:8px 12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.topbar h1{color:#f0b800;font-size:15px;font-weight:700}
.ver{color:#555;font-size:11px}
.btn{padding:6px 14px;border:none;border-radius:5px;cursor:pointer;font-size:12px;font-weight:600}
.btn-go{background:#1a8f4a;color:#fff}.btn-go:hover{background:#22b85e}
.btn-stop{background:#8f1a1a;color:#fff}.btn-stop:hover{background:#b82222}
.btn-sm{background:#222;color:#aaa;padding:4px 10px;font-size:11px}
.tabs{display:flex;gap:4px;padding:0 12px;background:#111;border-bottom:1px solid #222}
.tab{padding:7px 16px;font-size:12px;cursor:pointer;color:#666;border-bottom:2px solid transparent;background:none;border:none}
.tab.active{color:#f0b800;border-bottom:2px solid #f0b800}
.tab-panel{display:none}.tab-panel.active{display:block}
.body{display:grid;grid-template-columns:320px 1fr;gap:0;height:calc(100vh - 80px)}
@media(max-width:700px){.body{grid-template-columns:1fr;height:auto}}
.sidebar{background:#111;border-right:1px solid #1e1e1e;padding:10px;overflow-y:auto;height:100%}
.main{padding:10px;overflow-y:auto;height:100%}
.card{background:#161616;border:1px solid #222;border-radius:6px;padding:10px;margin-bottom:8px}
.card h3{color:#f0b800;font-size:12px;margin-bottom:6px}
label{display:block;color:#888;font-size:11px;margin-bottom:2px}
input,select{width:100%;background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:5px 7px;border-radius:4px;font-size:12px;margin-bottom:6px}
.stat-row{display:flex;justify-content:space-between;padding:2px 0;font-size:12px}
.stat-label{color:#666}.stat-val{color:#e0e0e0;font-weight:600}
.green{color:#0f9}.red{color:#f45}.yellow{color:#f0b800}
.log-box{background:#0a0a0a;border:1px solid #1e1e1e;border-radius:4px;height:200px;overflow-y:auto;padding:6px;font-size:11px;font-family:monospace}
.log-line{padding:1px 0;border-bottom:1px solid #111}
.prog-bar{background:#1e1e1e;border-radius:3px;height:6px;margin:6px 0}
.prog-fill{background:#f0b800;height:6px;border-radius:3px;transition:width .3s}
.top20-row{display:grid;grid-template-columns:24px 1fr 1fr 1fr 1fr 1fr;gap:4px;padding:3px 0;border-bottom:1px solid #1a1a1a;font-size:11px;align-items:center}
.badge{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;margin-right:3px}
.badge-bull{background:#0a2a1a;color:#0f9}.badge-bear{background:#2a0a0a;color:#f45}
#chartPanel{padding:10px}
.chart-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:flex-end;padding-bottom:10px}
.chart-bar label{display:flex;flex-direction:column;font-size:11px;color:#888;gap:2px}
.chart-bar input,.chart-bar select{background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:4px 7px;border-radius:4px;font-size:12px;width:90px;margin-bottom:0}
.chart-legend{display:flex;flex-wrap:wrap;gap:10px;padding:4px 0 8px;font-size:11px;color:#888}
.chart-legend span{display:flex;align-items:center;gap:4px}
.chart-legend i{display:inline-block;width:14px;height:6px;border-radius:2px}
#chartMetrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(90px,1fr));gap:6px;margin-top:8px}
.cm{background:#161616;border:1px solid #222;border-radius:5px;padding:8px 10px}
.cm .cl{font-size:10px;color:#555}.cm .cv{font-size:16px;font-weight:700;color:#e0e0e0}
#chartCanvas{display:block;width:100%;cursor:grab;border:1px solid #222;border-radius:5px;background:#0a0a0a}
#chartStatus{font-size:11px;color:#555;padding:4px 0}
</style></head><body>
<div class="topbar">
  <h1>&#9889; SMC Optimizer</h1>
  <span class="ver" id="verBadge">v__VER__</span>
  <button class="btn btn-go" id="btnStart" onclick="startOpt()">&#9654; Старт</button>
  <button class="btn btn-stop" id="btnStop" onclick="stopOpt()" style="display:none">&#9632; Стоп</button>
  <span id="statusBadge" style="color:#555;font-size:11px">готов</span>
</div>
<div class="tabs">
  <button class="tab active" onclick="switchTab('opt',this)">Оптимизатор</button>
  <button class="tab" onclick="switchTab('chart',this)">График</button>
</div>
<div id="optPanel" class="tab-panel active">
<div class="body">
<div class="sidebar">
  <div class="card">
    <h3>Параметры запуска</h3>
    <label>Символ</label><input id="sym" value="BTC_USDT">
    <label>Таймфрейм</label>
    <select id="tf">
      <option>1m</option><option>5m</option><option selected>15m</option>
      <option>30m</option><option>1h</option><option>4h</option><option>1d</option>
    </select>
    <label>Дней истории</label><input id="days" type="number" value="30" min="7" max="365">
    <label>SL %</label><input id="sl_pct" type="number" value="0.6" step="0.05">
    <label>TP %</label><input id="tp_pct" type="number" value="1.2" step="0.05">
    <label>Риск на сделку %</label><input id="risk_pct" type="number" value="2.0" step="0.5">
  </div>
  <div class="card">
    <h3>Лучший конфиг</h3>
    <button class="btn btn-go" style="width:100%;margin-bottom:8px;font-size:11px" onclick="applyBestToChart()">Открыть на графике</button>
    <div id="bestCard" style="color:#555;font-size:11px">—</div>
  </div>
  <div class="card">
    <h3>Алерты (Telegram / ntfy)</h3>
    <label>TG Token</label><input id="tgToken" type="password" placeholder="1234567890:AA...">
    <label>TG Chat ID</label><input id="tgChat" placeholder="123456789">
    <label>ntfy URL (необязательно)</label><input id="ntfyUrl" placeholder="https://ntfy.sh/your-topic">
    <div style="display:flex;gap:6px">
      <button class="btn btn-sm" style="flex:1" onclick="saveAlertCfg()">💾 Сохранить</button>
      <button class="btn btn-sm" style="flex:1" onclick="testAlertCfg()">📨 Тест</button>
    </div>
    <div id="alertCfgStatus" style="font-size:11px;color:#555;margin-top:6px">—</div>
  </div>
  <div class="card">
    <h3>Прогресс</h3>
    <div class="prog-bar"><div class="prog-fill" id="progFill" style="width:0%"></div></div>
    <div class="stat-row"><span class="stat-label">Цикл</span><span class="stat-val" id="cycleVal">—</span></div>
    <div class="stat-row"><span class="stat-label">Попыток</span><span class="stat-val" id="trialsVal">—</span></div>
  </div>
  <div class="card log-box" id="logBox"></div>
</div>
<div class="main">
  <div class="card">
    <h3>Топ-20 конфигураций</h3>
    <div id="top20Container">
      <div class="top20-row">
        <span>#</span><span>WR%</span><span>PF</span><span>DD%</span>
        <span>T</span><span>SL/TP/swing</span>
      </div>
    </div>
  </div>
</div>
</div>
</div>
<div id="chartPanel" class="tab-panel">
  <div class="chart-bar">
    <label>Символ<input id="cSym" value="BTC_USDT"></label>
    <label>ТФ<select id="cTf">
      <option>1m</option><option>5m</option><option value="15m" selected>15m</option>
      <option>30m</option><option>1h</option><option>4h</option><option>1d</option>
    </select></label>
    <label>Дней<input id="cDays" type="number" value="7" min="1" max="60" style="width:60px"></label>
    <label>Swing<input id="cSwing" type="number" value="10" min="3" max="50" style="width:60px"></label>
    <label>SL%<input id="cSl" type="number" value="0.8" step="0.1" style="width:60px"></label>
    <label>TP%<input id="cTp" type="number" value="1.6" step="0.1" style="width:60px"></label>
    <button class="btn btn-go" onclick="loadChart()" style="align-self:flex-end">Загрузить</button>
    <button class="btn" id="monBtn" onclick="toggleChartMonitor()" style="align-self:flex-end">🔔 Алерты</button>
  </div>
  <div id="chartStatus">Нажмите Загрузить</div>
  <div class="chart-legend">
    <span><i style="background:#089981"></i>Long</span>
    <span><i style="background:#F23645"></i>Short</span>
    <span><i style="background:rgba(49,121,245,0.3);border:1px solid #3179f5"></i>Bull OB</span>
    <span><i style="background:rgba(247,124,128,0.3);border:1px solid #f77c80"></i>Bear OB</span>
    <span><i style="background:rgba(0,255,104,0.2);border:1px solid #0f9"></i>FVG Bull</span>
    <span><i style="background:rgba(255,0,8,0.15);border:1px solid #f45"></i>FVG Bear</span>
  </div>
  <canvas id="chartCanvas"></canvas>
  <div id="chartMetrics"></div>
</div>
<script>
var _bestParams = null;
var _chartExtra = {internal_len:5, ob_filter:'atr', ob_mitigation:'highlow',
  fvg_enabled:true, fvg_threshold:0.1, choch_only:false, use_internal:true,
  min_ob_size:1.0, require_fvg_confirm:false};
var TF_SEC = {"1m":60,"5m":300,"15m":900,"30m":1800,"1h":3600,"4h":14400,"1d":86400};
var _chartAutoTimer = null;
var _monitorActive = false;

function switchTab(id, btn){
  document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
  document.querySelectorAll('.tab').forEach(function(b){b.classList.remove('active');});
  document.getElementById(id+'Panel').classList.add('active');
  btn.classList.add('active');
}

function applyBestToChart(){
  if(!_bestParams) return;
  var p = _bestParams;
  document.getElementById('cSym').value  = document.getElementById('sym').value;
  document.getElementById('cTf').value   = document.getElementById('tf').value;
  document.getElementById('cSwing').value = p.swing_len || 10;
  document.getElementById('cSl').value   = p.sl_pct || 0.8;
  document.getElementById('cTp').value   = p.tp_pct || 1.6;
  _chartExtra = {
    internal_len: p.internal_len, ob_filter: p.ob_filter, ob_mitigation: p.ob_mitigation,
    fvg_enabled: p.fvg_enabled, fvg_threshold: p.fvg_threshold, choch_only: p.choch_only,
    use_internal: p.use_internal, min_ob_size: p.min_ob_size,
    require_fvg_confirm: p.require_fvg_confirm
  };
  switchTab('chart', document.querySelectorAll('.tab')[1]);
  loadChart();
}

function toggleChartMonitor(){
  var btn = document.getElementById('monBtn');
  if(_monitorActive){
    fetch('/chart_monitor_stop',{method:'POST'}).then(function(){
      _monitorActive=false;
      btn.textContent='🔔 Алерты';
      btn.classList.remove('btn-go');
    });
    return;
  }
  var sym  = document.getElementById('cSym').value.trim()||'BTC_USDT';
  var tf   = document.getElementById('cTf').value;
  var days = parseInt(document.getElementById('cDays').value)||30;
  var params = Object.assign({}, _chartExtra, {
    swing_len: parseFloat(document.getElementById('cSwing').value),
    sl_pct:    parseFloat(document.getElementById('cSl').value),
    tp_pct:    parseFloat(document.getElementById('cTp').value)
  });
  fetch('/chart_monitor_start',{method:'POST',headers:{'Content-Type':'application/json'},
    body: JSON.stringify({sym:sym, tf:tf, days:days, params:params})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        _monitorActive=true;
        btn.textContent='🔕 Алерты вкл ('+sym+' '+tf+')';
        btn.classList.add('btn-go');
      }
    }).catch(function(e){cStatus('Ошибка монитора: '+e);});
}

function alertCfgStatus(t,ok){
  var el=document.getElementById('alertCfgStatus');
  el.textContent=t;
  el.style.color = ok===true?'#0f9':(ok===false?'#f45':'#555');
}

function loadAlertCfg(){
  fetch('/alert_cfg').then(function(r){return r.json();}).then(function(d){
    document.getElementById('tgToken').value = d.tg_token||'';
    document.getElementById('tgChat').value  = d.tg_chat||'';
    document.getElementById('ntfyUrl').value = d.ntfy_url||'';
    if(d.tg_token||d.tg_chat||d.ntfy_url) alertCfgStatus('Загружено из сохранённых настроек');
  }).catch(function(){});
}

function saveAlertCfg(){
  var body={
    tg_token: document.getElementById('tgToken').value.trim(),
    tg_chat:  document.getElementById('tgChat').value.trim(),
    ntfy_url: document.getElementById('ntfyUrl').value.trim()
  };
  alertCfgStatus('Сохраняем...');
  fetch('/alert_cfg',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(r){return r.json();})
    .then(function(d){ alertCfgStatus(d.ok?'💾 Сохранено':'Ошибка сохранения', d.ok); })
    .catch(function(e){ alertCfgStatus('Ошибка: '+e, false); });
}

function testAlertCfg(){
  alertCfgStatus('Сохраняем и отправляем тест...');
  saveAlertCfgSync().then(function(){
    return fetch('/alert_test',{method:'POST'});
  }).then(function(r){return r.json();})
    .then(function(d){
      alertCfgStatus(d.ok?'✅ Тест отправлен, проверь Telegram':('❌ '+(d.error||'не дошло')), d.ok);
    }).catch(function(e){ alertCfgStatus('Ошибка: '+e, false); });
}

function saveAlertCfgSync(){
  var body={
    tg_token: document.getElementById('tgToken').value.trim(),
    tg_chat:  document.getElementById('tgChat').value.trim(),
    ntfy_url: document.getElementById('ntfyUrl').value.trim()
  };
  return fetch('/alert_cfg',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
}

loadAlertCfg();

/* ── Optimizer polling ── */
var polling=null, lastLogTotal=0, logsDropped=0;

function startOpt(){
  var body={
    symbol:document.getElementById('sym').value,
    tf:document.getElementById('tf').value,
    days:parseInt(document.getElementById('days').value),
    sl_pct:parseFloat(document.getElementById('sl_pct').value),
    tp_pct:parseFloat(document.getElementById('tp_pct').value),
    risk_pct:parseFloat(document.getElementById('risk_pct').value),
  };
  fetch('/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(){
      document.getElementById('btnStart').style.display='none';
      document.getElementById('btnStop').style.display='';
      document.getElementById('statusBadge').textContent='работает...';
      scheduleNext();
    });
}
function stopOpt(){
  fetch('/scan_stop',{method:'POST'}).then(function(){
    document.getElementById('btnStop').style.display='none';
    document.getElementById('btnStart').style.display='';
    document.getElementById('statusBadge').textContent='останавливается...';
  });
}
function scheduleNext(){ polling=setTimeout(poll, 1500); }
function poll(){
  fetch('/opt_status').then(function(r){return r.json();}).then(function(d){
    logsDropped = d.logs_dropped||0;
    var totalNow = logsDropped + (d.logs||[]).length;
    var newFrom = Math.max(0, lastLogTotal - logsDropped);
    var newLogs = (d.logs||[]).slice(newFrom);
    var lb = document.getElementById('logBox');
    newLogs.forEach(function(l){
      var div=document.createElement('div');
      div.className='log-line';
      div.innerHTML='<span style="color:#555">['+l.ts+']</span> '+l.msg;
      lb.appendChild(div);
    });
    if(newLogs.length) lb.scrollTop=lb.scrollHeight;
    lastLogTotal=totalNow;

    document.getElementById('progFill').style.width=(d.progress||0)+'%';
    document.getElementById('cycleVal').textContent=d.cycle||'—';
    document.getElementById('trialsVal').textContent=(d.trials||0).toLocaleString();

    if(!d.running){
      document.getElementById('btnStop').style.display='none';
      document.getElementById('btnStart').style.display='';
      document.getElementById('statusBadge').textContent='завершено';
    } else scheduleNext();

    if(d.best){
      var r=d.best.result, p=d.best.params;
      _bestParams = p;
      var wrC=r.winrate>=55?'green':r.winrate>=45?'yellow':'red';
      document.getElementById('bestCard').innerHTML=
        '<div class="stat-row"><span class="stat-label">Winrate</span><span class="stat-val '+wrC+'">'+r.winrate+'%</span></div>'+
        '<div class="stat-row"><span class="stat-label">Profit Factor</span><span class="stat-val">'+r.profit_factor+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">Max DD</span><span class="stat-val red">'+r.max_dd+'%</span></div>'+
        '<div class="stat-row"><span class="stat-label">Сделок</span><span class="stat-val">'+r.trades+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">Доходность</span><span class="stat-val '+(r.total_return>=0?'green':'red')+'">'+r.total_return+'%</span></div>'+
        '<div class="stat-row"><span class="stat-label">Fitness</span><span class="stat-val yellow">'+r.fitness+'</span></div>'+
        '<hr style="border-color:#222;margin:5px 0">'+
        '<div class="stat-row"><span class="stat-label">SL / TP</span><span class="stat-val">'+p.sl_pct+'% / '+p.tp_pct+'%</span></div>'+
        '<div class="stat-row"><span class="stat-label">Swing len</span><span class="stat-val">'+p.swing_len+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">Internal len</span><span class="stat-val">'+p.internal_len+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">OB filter</span><span class="stat-val">'+p.ob_filter+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">OB mitigation</span><span class="stat-val">'+p.ob_mitigation+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">FVG</span><span class="stat-val">'+(p.fvg_enabled?'вкл':'выкл')+'</span></div>'+
        '<div class="stat-row"><span class="stat-label">CHoCH only</span><span class="stat-val">'+(p.choch_only?'да':'нет')+'</span></div>';
    }

    var top=(d.top20||[]);
    if(top.length){
      var html='<div class="top20-row"><span>#</span><span>WR%</span><span>PF</span><span>DD%</span><span>T</span><span>SL/TP/swing</span></div>';
      top.forEach(function(e,i){
        var r=e.result,p=e.params;
        var wrC=r.winrate>=55?'green':r.winrate>=45?'yellow':'red';
        html+='<div class="top20-row">'+
          '<span style="color:#555">'+(i+1)+'</span>'+
          '<span class="'+wrC+'">'+r.winrate+'%</span>'+
          '<span>'+r.profit_factor+'</span>'+
          '<span class="red">'+r.max_dd+'%</span>'+
          '<span>'+r.trades+'</span>'+
          '<span style="color:#888">'+p.sl_pct+'/'+p.tp_pct+'/'+p.swing_len+'</span>'+
        '</div>';
      });
      document.getElementById('top20Container').innerHTML=html;
    }
  }).catch(function(){scheduleNext();});
}
fetch('/opt_status').then(function(r){return r.json();}).then(function(d){
  if(d.running){
    document.getElementById('btnStart').style.display='none';
    document.getElementById('btnStop').style.display='';
    document.getElementById('statusBadge').textContent='работает...';
    scheduleNext();
  }
});

/* ── Chart ── */
var _cd=[], _sig=[], _obs_bull=[], _obs_bear=[], _fvg_bull=[], _fvg_bear=[];
var _camStart=0, _camEnd=0, _drag=false, _dragX=0, _dragCam=0;
var cv=document.getElementById('chartCanvas');
var ctx2=cv.getContext('2d');

function cStatus(t){document.getElementById('chartStatus').textContent=t;}

function loadChart(auto){
  var sym=document.getElementById('cSym').value.trim()||'BTC_USDT';
  var tf=document.getElementById('cTf').value;
  var days=document.getElementById('cDays').value;
  var sw=document.getElementById('cSwing').value;
  var sl=document.getElementById('cSl').value;
  var tp=document.getElementById('cTp').value;
  var ex=_chartExtra;
  if(!auto) cStatus('Загружаем данные...');
  // Запоминаем текущий вид по времени (не по индексу — индексы сдвигаются
  // при скользящем окне свечей), чтобы автообновление раз в бар не сбрасывало
  // масштаб/позицию, если пользователь листает историю
  var wasFollowing = !_cd.length || _camEnd >= _cd.length-3;
  var anchorTs = (_cd.length && _camStart < _cd.length) ? _cd[_camStart].t : null;
  var visWidth = _camEnd - _camStart;
  var url='/chart_data?sym='+encodeURIComponent(sym)+'&tf='+tf+'&days='+days
    +'&swing='+sw+'&sl='+sl+'&tp='+tp
    +'&internal_len='+ex.internal_len+'&ob_filter='+ex.ob_filter+'&ob_mitigation='+ex.ob_mitigation
    +'&fvg_enabled='+ex.fvg_enabled+'&fvg_threshold='+ex.fvg_threshold+'&choch_only='+ex.choch_only
    +'&use_internal='+ex.use_internal+'&min_ob_size='+ex.min_ob_size
    +'&require_fvg_confirm='+ex.require_fvg_confirm;
  fetch(url)
    .then(function(r){return r.json();}).then(function(d){
      if(d.error){cStatus('Ошибка: '+d.error);return;}
      _cd=d.candles||[];
      _sig=d.signals||[];
      // Зоны OB/FVG теперь считает бэкенд той же функцией _simulate(),
      // что и оптимизатор — это гарантирует совпадение с лучшим конфигом
      // и ограниченную (а не "до конца графика") протяжённость зон.
      _obs_bull=d.bull_obs||[]; _obs_bear=d.bear_obs||[];
      _fvg_bull=d.fvg_bull||[]; _fvg_bear=d.fvg_bear||[];
      if(!auto || anchorTs===null){
        _camStart=Math.max(0,_cd.length-120);
        _camEnd=_cd.length-1;
      } else if(wasFollowing){
        _camEnd=_cd.length-1;
        _camStart=Math.max(0,_camEnd-visWidth);
      } else {
        var idx=0;
        for(var i=0;i<_cd.length;i++){ idx=i; if(_cd[i].t>=anchorTs) break; }
        _camStart=Math.max(0,Math.min(_cd.length-1,idx));
        _camEnd=Math.min(_cd.length-1,_camStart+visWidth);
      }
      drawChart();
      renderCM(d.metrics);
      cStatus(_cd.length+' свечей, '+_sig.length+' сигналов'+(auto?' (автообновление)':''));
      scheduleAutoRefresh(tf);
    }).catch(function(e){cStatus('Ошибка: '+e);});
}

function scheduleAutoRefresh(tf){
  if(_chartAutoTimer) clearTimeout(_chartAutoTimer);
  var sec = TF_SEC[tf] || 900;
  _chartAutoTimer = setTimeout(function(){ loadChart(true); }, sec*1000);
}

function drawChart(){
  if(!_cd.length)return;
  var dpr=window.devicePixelRatio||1;
  var W=cv.parentElement.clientWidth-20;
  var H=420;
  cv.width=W*dpr;cv.height=H*dpr;
  cv.style.width=W+'px';cv.style.height=H+'px';
  ctx2.scale(dpr,dpr);
  var s=Math.max(0,Math.floor(_camStart));
  var e=Math.min(_cd.length-1,Math.floor(_camEnd));
  var vis=_cd.slice(s,e+1);
  if(!vis.length)return;
  var PAD={l:65,r:8,t:12,b:28};
  var cW=W-PAD.l-PAD.r, cH=H-PAD.t-PAD.b;
  var barW=cW/vis.length, candleW=Math.max(1,barW*0.65);
  var mn=Infinity,mx=-Infinity;
  vis.forEach(function(c){if(c.l<mn)mn=c.l;if(c.h>mx)mx=c.h;});
  _sig.forEach(function(sg){
    if(sg.entry_i>=s&&sg.entry_i<=e){
      if(sg.tp<mn)mn=sg.tp;if(sg.tp>mx)mx=sg.tp;
      if(sg.sl<mn)mn=sg.sl;if(sg.sl>mx)mx=sg.sl;
    }
  });
  var rng=mx-mn||1, pad2=rng*0.06;
  mn-=pad2;mx+=pad2;
  function toY(p){return PAD.t+cH*(1-(p-mn)/(mx-mn));}
  function toX(i){return PAD.l+(i-s+0.5)*barW;}
  ctx2.fillStyle='#0a0a0a';ctx2.fillRect(0,0,W,H);
  ctx2.strokeStyle='rgba(255,255,255,0.05)';ctx2.lineWidth=0.5;
  for(var g=0;g<=5;g++){
    var p=mn+(mx-mn)*g/5,y=toY(p);
    ctx2.beginPath();ctx2.moveTo(PAD.l,y);ctx2.lineTo(W-PAD.r,y);ctx2.stroke();
    ctx2.fillStyle='rgba(160,160,160,0.45)';ctx2.font='10px monospace';ctx2.textAlign='right';
    ctx2.fillText(p>1000?p.toFixed(1):p>10?p.toFixed(2):p.toFixed(4),PAD.l-3,y+3);
  }
  _fvg_bull.filter(function(f){return f.end_i>=s&&f.i<=e;}).forEach(function(f){
    ctx2.fillStyle='rgba(0,255,104,0.1)';ctx2.strokeStyle='rgba(0,255,104,0.3)';ctx2.lineWidth=0.5;
    var x1=toX(Math.max(f.i,s))-barW/2, x2=toX(Math.min(f.end_i,e))+barW/2;
    var y1=toY(f.hi),y2=toY(f.lo);ctx2.fillRect(x1,y1,x2-x1,y2-y1);ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
  });
  _fvg_bear.filter(function(f){return f.end_i>=s&&f.i<=e;}).forEach(function(f){
    ctx2.fillStyle='rgba(255,0,8,0.08)';ctx2.strokeStyle='rgba(255,0,8,0.25)';ctx2.lineWidth=0.5;
    var x1=toX(Math.max(f.i,s))-barW/2, x2=toX(Math.min(f.end_i,e))+barW/2;
    var y1=toY(f.hi),y2=toY(f.lo);ctx2.fillRect(x1,y1,x2-x1,y2-y1);ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
  });
  _obs_bull.filter(function(o){return o.end_i>=s&&o.i<=e;}).forEach(function(o){
    var x1=toX(Math.max(o.i,s))-barW/2, x2=toX(Math.min(o.end_i,e))+barW/2;
    ctx2.fillStyle='rgba(49,121,245,0.18)';ctx2.strokeStyle='rgba(49,121,245,0.5)';ctx2.lineWidth=0.8;
    var y1=toY(o.hi),y2=toY(o.lo);ctx2.fillRect(x1,y1,x2-x1,y2-y1);ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
    ctx2.fillStyle='rgba(49,121,245,0.6)';ctx2.font='9px monospace';ctx2.textAlign='left';ctx2.fillText('Bull OB',x1+2,y1+9);
  });
  _obs_bear.filter(function(o){return o.end_i>=s&&o.i<=e;}).forEach(function(o){
    var x1=toX(Math.max(o.i,s))-barW/2, x2=toX(Math.min(o.end_i,e))+barW/2;
    ctx2.fillStyle='rgba(247,124,128,0.18)';ctx2.strokeStyle='rgba(247,124,128,0.5)';ctx2.lineWidth=0.8;
    var y1=toY(o.hi),y2=toY(o.lo);ctx2.fillRect(x1,y1,x2-x1,y2-y1);ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
    ctx2.fillStyle='rgba(247,124,128,0.6)';ctx2.font='9px monospace';ctx2.textAlign='left';ctx2.fillText('Bear OB',x1+2,y1+9);
  });
  vis.forEach(function(c,idx){
    var xi=s+idx,x=toX(xi),bull=c.c>=c.o,clr=bull?'#089981':'#F23645';
    ctx2.strokeStyle=clr;ctx2.lineWidth=1;
    ctx2.beginPath();ctx2.moveTo(x,toY(c.h));ctx2.lineTo(x,toY(c.l));ctx2.stroke();
    ctx2.fillStyle=clr;
    var y1=toY(Math.max(c.o,c.c)),y2=toY(Math.min(c.o,c.c));
    ctx2.fillRect(x-candleW/2,y1,candleW,Math.max(1,y2-y1));
  });
  _sig.forEach(function(sg){
    if(sg.entry_i<s||sg.entry_i>e)return;
    var xe=toX(sg.entry_i);
    var xe2=(sg.exit_i!==undefined&&sg.exit_i<=e)?toX(sg.exit_i):W-PAD.r;
    var ye=toY(sg.entry),yt=toY(sg.tp),ys=toY(sg.sl);
    var isLong=sg.dir==='long';
    ctx2.fillStyle=isLong?'rgba(8,153,129,0.07)':'rgba(242,54,69,0.07)';
    ctx2.fillRect(xe,Math.min(yt,ys),Math.max(0,xe2-xe),Math.abs(yt-ys));
    ctx2.strokeStyle='rgba(8,153,129,0.55)';ctx2.lineWidth=1;ctx2.setLineDash([4,3]);
    ctx2.beginPath();ctx2.moveTo(xe,yt);ctx2.lineTo(xe2,yt);ctx2.stroke();
    ctx2.strokeStyle='rgba(242,54,69,0.55)';
    ctx2.beginPath();ctx2.moveTo(xe,ys);ctx2.lineTo(xe2,ys);ctx2.stroke();
    ctx2.setLineDash([]);
    if(sg.exit_i!==undefined&&sg.exit_i>=s&&sg.exit_i<=e){
      ctx2.fillStyle=sg.win?'rgba(8,153,129,0.8)':'rgba(242,54,69,0.8)';
      ctx2.beginPath();ctx2.arc(toX(sg.exit_i),toY(sg.win?sg.tp:sg.sl),4,0,Math.PI*2);ctx2.fill();
    }
    ctx2.fillStyle=isLong?'#089981':'#F23645';
    ctx2.beginPath();
    if(isLong){ctx2.moveTo(xe-5,ye+9);ctx2.lineTo(xe+5,ye+9);ctx2.lineTo(xe,ye+1);}
    else{ctx2.moveTo(xe-5,ye-9);ctx2.lineTo(xe+5,ye-9);ctx2.lineTo(xe,ye-1);}
    ctx2.fill();
    ctx2.fillStyle='rgba(180,180,180,0.7)';ctx2.font='9px monospace';ctx2.textAlign='left';
    function fmt(v){return v>100?v.toFixed(1):v.toFixed(4);}
    ctx2.fillText('TP '+fmt(sg.tp),xe+4,yt-2);
    ctx2.fillText('SL '+fmt(sg.sl),xe+4,ys+9);
  });
  ctx2.fillStyle='rgba(140,140,140,0.4)';ctx2.font='9px monospace';ctx2.textAlign='center';
  var every=Math.ceil(vis.length/8);
  vis.forEach(function(c,idx){
    if(idx%every===0){
      var x=toX(s+idx),d=new Date(c.t*1000);
      ctx2.fillText((d.getMonth()+1)+'/'+(d.getDate()),x,H-PAD.b+10);
      ctx2.fillText(d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0'),x,H-PAD.b+20);
    }
  });
}

function renderCM(m){
  if(!m)return;
  var items=[
    {l:'Сделок',v:m.trades},{l:'WinRate',v:m.winrate+'%'},
    {l:'PF',v:m.profit_factor},{l:'Max DD',v:m.max_dd+'%'},
    {l:'Return',v:m.total_return+'%'},{l:'Fitness',v:m.fitness},
  ];
  document.getElementById('chartMetrics').innerHTML=items.map(function(i){
    return '<div class="cm"><div class="cl">'+i.l+'</div><div class="cv">'+i.v+'</div></div>';
  }).join('');
}

cv.addEventListener('mousedown',function(e){_drag=true;_dragX=e.clientX;_dragCam=_camStart;cv.style.cursor='grabbing';});
document.addEventListener('mouseup',function(){_drag=false;cv.style.cursor='grab';});
document.addEventListener('mousemove',function(e){
  if(!_drag||!_cd.length)return;
  var W=cv.parentElement.clientWidth-20;
  var vis=_camEnd-_camStart;
  var dx=(e.clientX-_dragX)/W*vis;
  _camStart=Math.max(0,Math.min(_cd.length-vis-1,_dragCam-dx));
  _camEnd=_camStart+vis;
  drawChart();
});
cv.addEventListener('wheel',function(e){
  e.preventDefault();
  if(!_cd.length)return;
  var z=e.deltaY>0?1.15:0.87;
  var vis=_camEnd-_camStart;
  var nv=Math.min(_cd.length,Math.max(20,Math.round(vis*z)));
  var center=(_camStart+_camEnd)/2;
  _camStart=Math.max(0,Math.round(center-nv/2));
  _camEnd=Math.min(_cd.length-1,_camStart+nv);
  drawChart();
},{passive:false});
var _tc=null;
cv.addEventListener('touchstart',function(e){_tc=e.touches[0].clientX;_dragCam=_camStart;});
cv.addEventListener('touchmove',function(e){
  e.preventDefault();
  if(!_cd.length)return;
  var W=cv.parentElement.clientWidth-20;
  var vis=_camEnd-_camStart;
  var dx=(e.touches[0].clientX-_tc)/W*vis;
  _camStart=Math.max(0,Math.min(_cd.length-vis-1,_dragCam-dx));
  _camEnd=_camStart+vis;
  drawChart();
},{passive:false});
window.addEventListener('resize',drawChart);
</script></body></html>
""".replace("__VER__", APP_VERSION)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",len(body))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/opt_status":
            with opt_lock:
                self._json({k:v for k,v in opt_state.items() if k!="chart"})
        elif self.path.startswith("/chart_data"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            def qf(name, default):
                return qs.get(name, [str(default)])[0]
            def qb(name, default):
                return qf(name, default).lower() in ("true","1","yes")
            sym  = qf("sym",  "BTC_USDT")
            tf   = qf("tf",   "15m")
            days = int(float(qf("days", 7)))
            sl_p = float(qf("sl",  0.8))
            tp_p = float(qf("tp",  1.6))
            candles = _fetch_candles(sym, tf, days)
            if not candles:
                self._json({"error": "no data"}); return
            p = {"swing_len": int(float(qf("swing", 10))),
                 "internal_len": int(float(qf("internal_len", 5))),
                 "ob_filter": qf("ob_filter", "atr"),
                 "ob_mitigation": qf("ob_mitigation", "highlow"),
                 "fvg_enabled": qb("fvg_enabled", True),
                 "fvg_threshold": float(qf("fvg_threshold", 0.1)),
                 "choch_only": qb("choch_only", False),
                 "use_internal": qb("use_internal", True),
                 "min_ob_size": float(qf("min_ob_size", 1.0)),
                 "require_fvg_confirm": qb("require_fvg_confirm", False),
                 "sl_pct": sl_p, "tp_pct": tp_p}
            result = _simulate(candles, p, sl_pct=sl_p, tp_pct=tp_p, _collect=True)
            if not result:
                self._json({"error": "simulation failed"}); return
            # Slim down candles for transfer
            slim = [{"t":c["t"],"o":c["open"],"h":c["high"],"l":c["low"],"c":c["close"]} for c in candles]
            self._json({"candles": slim, "signals": result.get("signals",[]),
                        "bull_obs": result.get("bull_obs",[]), "bear_obs": result.get("bear_obs",[]),
                        "fvg_bull": result.get("fvg_bull",[]), "fvg_bear": result.get("fvg_bear",[]),
                        "metrics": {k:result[k] for k in ("trades","winrate","profit_factor","max_dd","total_return","fitness")}})
        elif self.path == "/chart_monitor_status":
            with chart_mon_lock:
                self._json({k:v for k,v in chart_mon_state.items() if k != "params"})
        elif self.path == "/alert_cfg":
            self._json({"tg_token": TG_TOKEN, "tg_chat": TG_CHAT, "ntfy_url": NTFY_URL})
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        global _opt_thread
        length = int(self.headers.get("Content-Length",0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/scan":
            if _opt_thread and _opt_thread.is_alive():
                self._json({"ok":False,"msg":"уже работает"}); return
            _stop_flag.clear()
            with opt_lock:
                opt_state.update({
                    "running":True,"logs":[],"logs_dropped":0,
                    "best":None,"top20":[],"cycle":0,"trials":0,"progress":0,
                    "symbol": body.get("symbol","BTC_USDT"),
                    "tf":     body.get("tf","15m"),
                    "days":   body.get("days",30),
                    "sl_pct": body.get("sl_pct",0.6),
                    "tp_pct": body.get("tp_pct",1.2),
                    "risk_pct": body.get("risk_pct",2.0),
                })
            _opt_thread = threading.Thread(target=run_optimizer, daemon=True)
            _opt_thread.start()
            self._json({"ok":True})

        elif self.path == "/scan_stop":
            _stop_flag.set()
            self._json({"ok":True})

        elif self.path == "/chart_monitor_start":
            global _chart_mon_thread
            sym  = body.get("sym", "BTC_USDT")
            tf   = body.get("tf", "15m")
            days = int(body.get("days", 30))
            p    = dict(body.get("params") or {})
            if "sl_pct" not in p: p["sl_pct"] = body.get("sl", 0.8)
            if "tp_pct" not in p: p["tp_pct"] = body.get("tp", 1.6)
            if "swing_len" not in p: p["swing_len"] = body.get("swing", 10)
            # Останавливаем предыдущий монитор, если был
            _chart_mon_stop.set()
            if _chart_mon_thread and _chart_mon_thread.is_alive():
                _chart_mon_thread.join(timeout=3)
            _chart_mon_stop.clear()
            with chart_mon_lock:
                chart_mon_state.update({
                    "active": True, "symbol": sym, "tf": tf, "days": days,
                    "params": p, "armed": False,
                    "last_entry_ts": None, "last_dir": None, "last_check": 0,
                })
            _chart_mon_thread = threading.Thread(
                target=_chart_monitor_loop, args=(sym, tf, days, p), daemon=True)
            _chart_mon_thread.start()
            self._json({"ok": True})

        elif self.path == "/chart_monitor_stop":
            _chart_mon_stop.set()
            with chart_mon_lock:
                chart_mon_state["active"] = False
            self._json({"ok": True})

        elif self.path == "/alert_cfg":
            global TG_TOKEN, TG_CHAT, NTFY_URL
            TG_TOKEN = (body.get("tg_token") or "").strip()
            TG_CHAT  = (body.get("tg_chat")  or "").strip()
            NTFY_URL = (body.get("ntfy_url") or "").strip()
            _save_alert_cfg()
            self._json({"ok": True})

        elif self.path == "/alert_test":
            ok, err = _test_alert()
            self._json({"ok": ok, "error": err})

        else:
            self.send_response(404); self.end_headers()

def main():
    global GH_TOKEN, TG_TOKEN, TG_CHAT, NTFY_URL
    # Подхватываем env
    GH_TOKEN  = os.environ.get("GH_TOKEN", GH_TOKEN)
    TG_TOKEN  = os.environ.get("TG_TOKEN", TG_TOKEN)
    TG_CHAT   = os.environ.get("TG_CHAT",  TG_CHAT)
    NTFY_URL  = os.environ.get("NTFY_URL", NTFY_URL)
    # Сохранённые через UI настройки имеют приоритет над env (если есть файл)
    _load_alert_cfg()

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"{_C_GRN}SMC Optimizer v{APP_VERSION} — http://0.0.0.0:{PORT}{_C_RST}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nЗавершено"); server.shutdown()

if __name__ == "__main__":
    main()
