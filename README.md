# SMC Optimizer

Smart Money Concepts parameter optimizer for Gate.io USDT-M futures.
Inspired by [WickFill Optimizer](https://github.com/mambaleylo/wickfill).

## Что делает

- Загружает свечи с Gate.io фьючерсы
- Симулирует сигналы по **SMC-стратегии** (BOS / CHoCH на swing и internal структуре)
- Перебирает параметры методом **Basin-Hopping** с критерием Metropolis
- TP/SL: фиксированный % или динамический ATR-SL
- Уведомления в **Telegram** и **ntfy**
- Синхронизация лучшего конфига через **GitHub**
- Веб-UI на `http://localhost:8765`

## Параметры оптимизации

| Параметр | Диапазон | Описание |
|---|---|---|
| `swing_len` | 20–100 | Длина свинга (pivot detection) |
| `internal_len` | 3–10 | Длина internal структуры |
| `ob_filter_mult` | 1.0–3.0 | ATR-множитель фильтра OB |
| `entry_type` | 0/1/2 | BOS only / CHoCH only / All |
| `htf_bias` | bool | Торговать только по HTF тренду |
| `confirm_bar` | bool | Подтверждение следующей свечой |
| `sl_pct` | 0.35–2.0% | Стоп-лосс |
| `tp_pct` | 0.5–3.0% | Тейк-профит |
| `use_atr_sl` | bool | Динамический ATR SL |
| `atr_sl_mult` | 0.5–3.0 | Множитель ATR для SL |

## Запуск (Termux / Linux)

```bash
pip install requests
python3 smc_screener.py
# UI → http://localhost:8765
```

## Логика сигналов

**LONG**: close пересекает вверх последний swing/internal pivot high → BOS (тренд бычий) или CHoCH (тренд медвежий)

**SHORT**: close пересекает вниз последний swing/internal pivot low → BOS или CHoCH

Выход: TP или SL по % от цены входа (или ATR×mult). При следующем противоположном сигнале позиция закрывается.
