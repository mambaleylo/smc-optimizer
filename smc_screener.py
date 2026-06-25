#!/usr/bin/env python3
"""
SMC Optimizer v3.48.3
- v3.48.3: фикс двух оставшихся багов.
  (1) _wt_bh_on_slice (автотюнинг весов): sl_pct/tp_pct теперь явно
  передаются в _simulate на каждом шаге (_neighbour/_shake/_random_params
  не генерируют их — они вне PARAM_SPACE). Раньше в цикле sl_pct/tp_pct
  брались из p["sl_pct"] которого там не было → simulate получал None →
  бэктест считался по дефолтам или падал. Убрана мёртвая проверка
  "if best_p else _random_params()" — best_p после инициализации всегда dict.
  (2) /auto_trade_start: добавлена валидация sl_pct/tp_pct перед стартом
  потока. Если значения отсутствуют или вне диапазона [0.1–5%/10%] —
  возвращаем {"ok":false} с описанием ошибки вместо молчаливого старта
  бота с некорректными параметрами и открытия реальной позиции.
SMC Optimizer v3.48.2
- v3.48.2: два критических фикса авто-торговли.
  (1) _gate_cancel_orders теперь отменяет ОБА типа ордеров: /futures/usdt/orders
  (лимитные/рыночные) И /futures/usdt/price_orders (триггерные TP/SL). Раньше
  при смене направления старые TP/SL зависали на бирже и могли сработать уже
  на новую позицию в противоположную сторону — двойной убыток.
  (2) _gate_close_position нормализует символ через .replace("/","_").upper()
  перед запросами к Gate API (как _gate_open_position). Убрана мёртвая
  переменная side. Теперь оба вызова гарантированно получают корректный
  contract-формат независимо от того, в каком виде пришёл символ.
SMC Optimizer v3.48.1
- v3.48.1: хотфикс сломанного JS — закрывающая скобка wtPoll() слипалась
  с текстом комментария (} ──), что роняло весь <script> и делало все кнопки
  интерфейса неактивными.
SMC Optimizer v3.48
- v3.48: эко-режим теперь включается по стагнации, а не по номеру цикла.
  Раньше: eco_mode = cycle > 300 — нагрузка всегда снижалась после 300 цикла,
  даже если оптимизатор активно находил новые best-конфиги.
  Теперь: eco_mode = no_improve >= 10 — эко включается только когда 10 циклов
  подряд нет улучшения (реальная стагнация, жечь CPU бесполезно); при появлении
  нового best автоматически выключается и поиск возвращается к полной скорости.
  Лог: «🌡 стагнация N циклов — включён эко» и «⚡ новый best — эко выключен».
SMC Optimizer v3.47
- v3.47: автотюнинг весов эквалайзера fitness (coordinate descent + walk-forward).
  Кнопка «🎯 Автотюнинг» под слайдерами запускает _run_weight_tune() в фоне:
  (1) история делится на N train/test окон (по умолчанию 4 окна, train≈60%,
  test≈40%); (2) для каждого из 5 весов последовательно перебирается сетка
  [0.5, 1.0, 1.5, 2.0, 3.0]; (3) для каждого значения запускается мини-BH
  (20 циклов) на train-кусках и считается средний total_return на соответствующих
  test-кусках (OOS — честная оценка без оверфита); (4) выбирается значение с
  лучшим средним OOS; (5) passes=2 прохода по всем весам для сходимости.
  Итоговые веса применяются глобально к FITNESS_WEIGHTS, сохраняются в
  ~/.smc_fitness_weights.json и отображаются на слайдерах без перезапуска.
  Алерт в Telegram/ntfy по завершении. Прогресс и лог видны под кнопкой.
  Эндпоинты: GET /weight_tune_status, POST /weight_tune_start, POST /weight_tune_stop.
- v3.46: опциональный авто-синк параметров авто-трейда с оптимизатором.
  Чекбокс "🔁 Автоматически подхватывать новый лучший конфиг" в панели
  авто-торговли (выключен по умолчанию). Если включён: при каждом новом
  best от оптимизатора того же символа/ТФ (sym+tf совпадают с
  auto_trade_state) — auto_trade_state["params"] обновляется на лету, без
  перезапуска бота. _auto_trade_loop теперь перечитывает params из
  auto_trade_state на каждой итерации (раньше снимал один раз при старте
  потока и не видел бы обновлений) — при реальном изменении параметров
  пишет в лог. Важно: TP/SL уже открытой на бирже сделки это НЕ меняет
  (триггерные ордера выставлены при входе и остаются как есть) — новые
  параметры влияют только на то, как ищется следующий сигнал; закрытие
  старой позиции и переоткрытие новой всё ещё происходит только при смене
  направления (см. v3.45), на том же направлении бот её не трогает.
  Включить/выключить можно на ходу через POST /auto_trade_sync, без
  остановки бота. В панели авто-торговли строка с текущими параметрами
  теперь показывает "(🔁 авто-синк вкл)" вместо предупреждения о
  расхождении, когда синк активен.
SMC Optimizer v3.45
- v3.45: два фикса авто-торговли. (1) Гонка с автоприменением лучшего конфига
  на график — оптимизатор после 30-го цикла сам вызывает applyBestToChart()
  при новом best и тихо меняет swing/SL%/TP% в полях графика, при этом
  авто-трейд работает с замороженным снимком этих же полей, снятым один раз
  при нажатии "Запустить" (auto_trade_state["params"]). Поэтому entry/SL/TP
  в Telegram-алерте могли не совпадать с тем, что нарисовано на графике —
  это два независимых набора параметров, не баг рендера графика. Логика не
  тронута (раздельность сохранена намеренно — см. v3.43), но в панель
  авто-торговли добавлена строка "Параметры бота (зафиксированы при
  запуске): swing=X SL=Y% TP=Z%" + жёлтое предупреждение, если текущие
  значения в полях графика отличаются от того, чем реально торгует бот.
  (2) _auto_trade_loop закрывал и переоткрывал текущую позицию на КАЖДУЮ
  смену entry_ts последнего сигнала, даже если направление не менялось —
  а entry_ts может сдвинуться просто из-за переразметки OB/swing на новой
  свече без реального срабатывания TP/SL на бирже. Итог: бот закрывал
  нормально идущую сделку и переоткрывал в том же направлении по новой
  цене — чистый убыток на спреде/комиссии без выгоды. Теперь закрытие +
  переоткрытие происходит только при смене направления (LONG↔SHORT); если
  направление совпадает с уже открытой позицией — бот её не трогает,
  исходные TP/SL ордера продолжают действовать сами.
SMC Optimizer v3.44
- v3.44: режим слабой производительности в оптимизаторе — после 300 циклов
  телефон ощутимо греется на долгих прогонах. Теперь при cycle > 300:
  (1) параллелизм батча урезается вдвое (n_workers//2 вместо n_workers) —
  меньше одновременно загруженных ядер/процессов; (2) пауза 0.4с между
  пачками внутри цикла; (3) пауза 8с между циклами целиком (раньше паузы
  между циклами не было совсем — следующий цикл стартовал мгновенно).
  В сумме цикл становится заметно длиннее и менее нагревающим, поиск не
  останавливается, просто медленнее. opt_state["eco_mode"] отражает текущее
  состояние, индикатор "Перебор" в шапке (taблетка из v3.43) подсвечивается
  жёлтым с "🌡 эко" пока активен режим — чисто индикация, поведение
  пользователю не нужно никак настраивать.
SMC Optimizer v3.43
- v3.43: единый индикатор статуса в шапке (3 цветные таблетки): "Перебор",
  "Монитор", "Авто-трейд". Перебор/Монитор/Авто-торговля — три независимых
  фоновых процесса со своими кнопками Старт/Стоп (_stop_flag, _chart_mon_stop,
  _auto_trade_stop никак не связаны друг с другом по дизайну) — кнопка "Стоп"
  у перебора параметров останавливает ТОЛЬКО перебор, монитор графика и
  авто-трейд при этом продолжают работать, если были запущены отдельно.
  Новая строка-индикатор под шапкой опрашивает /opt_status,
  /chart_monitor_status, /auto_trade_status раз в 2с независимо от открытой
  вкладки — точка горит зелёным когда процесс активен, жёлтым у авто-трейда
  если есть открытая позиция, серым когда выключен. Чисто индикация, логика
  стопа не менялась.
- v3.37: метка PnL% на графике у точки выхода каждой сделки — показывает
  процент от депо с учётом плеча (+X% зелёным при TP, -X% красным при SL).
  dep_pct передаётся в signals при _collect=True.
- v3.36: колонка "$100→$X" в топ-20 — показывает итоговый баланс при старте $100
  (Return% / 10, т.к. риск=10% от депо на сделку). Заменяет "Return%" на
  наглядный "$100→$X" в обеих таблицах (оптимизатор и скринер).
- v3.35: эквалайзер весов fitness — 5 вертикальных слайдеров (как на
  аудио-эквалайзере) в сайдбаре: WR, PF, Кол-во сделок, RR, Просадка.
  Формула fitness переписана как взвешенная лог-сумма множителей
  (log_fit = Σ wᵢ·log(factorᵢ), fitness = exp(log_fit)) — при всех весах=1.0
  даёт точно тот же результат, что прежняя формула-произведение, но позволяет
  тюнить вклад каждого множителя в ранжирование конфигов отдельно. Например,
  если в найденном конфиге мало сделок — выкручиваешь "Кол-во" выше 1.0, и
  поиск начинает сильнее предпочитать конфиги с бо́льшим числом сделок.
  Эндпоинты GET/POST /fitness_weights, сохранение в ~/.smc_fitness_weights.json.
  Применяется на ходу без остановки: одиночный оптимизатор и скрининг
  (main-процесс) читают актуальные веса при каждом вызове _simulate(); для
  ProcessPoolExecutor (соседи в локальном поиске считаются в отдельных
  процессах — своя память) свежий снэпшот весов передаётся явно при каждой
  пачке pool.submit(), а не один раз при старте пула.
- v3.33: скрининг "все монеты" возвращён в последовательный режим, по аналогии
  с одиночным режимом — прогнали монету (50 циклов), переключились на
  следующую. Раньше ThreadPoolExecutor(max_workers=4) гонял 4 монеты
  одновременно: на Android (GIL) это не давало параллелизма для CPU-bound
  _simulate(), а только взаимную конкуренцию за процессор — отсюда "медленно
  делает 50 циклов" при scan all, хотя одиночный прогон быстрый. Теперь
  run_screener — простой for по списку монет, без ThreadPool/as_completed.
  active_workers всегда содержит ровно одну текущую монету (UI не менялся).
- v3.23: fix вечного зависания на "инициализация..." при старте оптимизатора.
  Две причины: (1) _fetch_candles() при не-200 от Gate.io (например, контракт
  не существует — невалидный символ) просто спал 5с и повторял запрос с тем
  же current_from БЕЗ лимита попыток и без единой строчки в лог — вечный
  молчаливый retry; добавлен счётчик MAX_FAILS=5, после которого загрузка
  прерывается с понятной причиной в логе. (2) даже после остановки run_optimizer()
  по "Мало свечей" — opt_state["running"] не сбрасывался в False (return был
  ДО try/finally, где он сбрасывается) — поток умирал, а UI вечно показывал
  "⏳ инициализация..." и кнопку "Стоп", потому что running оставался True.
- v3.22: fix "мега-стоп / микро-тейк" на графике и нереалистичный бэктест
  (WR 88%+, Return 10000%+). Причина: sl_price считался от низа/верха
  Order Block (ob_lo/ob_hi), а tp_price — от entry_px на tp_pct; OB может
  быть на десятки свечей назад и в разы дальше от текущей цены, чем tp_pct —
  визуально SL улетал далеко, TP стоял рядом, а в бэктесте PnL всё равно
  считался по configured sl_pct (как будто SL рядом), хотя реально цене
  почти невозможно было его достать → завышенный WR и фейковая доходность.
  Теперь sl_price = entry_px*(1∓sl_pct/100), симметрично с tp_price — OB
  остаётся только триггером входа (возврат цены в зону), не якорем стопа.
- v3.21: AMOLED-скринсейвер (по аналогии с WickFill) — кнопка ⬤ AMOLED в
  шапке; при 15с простоя экран гасится чёрным оверлеем (время/дата +
  WR/PF/Return/T лучшего конфига + статус оптимизатора/авто-трейда/алертов),
  каждые 30с контент и кнопка-отпечаток выхода случайно мигрируют по экрану —
  защита AMOLED-дисплея от выгорания пикселей. Подключены Fullscreen API
  (прячет адресную строку) и Screen Wake Lock (не даёт ОС гасить экран);
  состояние и восстановление после reload/auto-update — как в WickFill.
- v3.20: прогресс цикла внутри монеты при скрининге. on_cycle колбэк передаётся
  в _run_one_sym_screener — current_cycle/max_cycles обновляются в screener_state
  на каждом цикле. UI уже показывал cycleStr (cycle N/50) — теперь заполняется.

- v3.19: скрининг возвращён в последовательный режим (как до параллелизма) — 50
  циклов, 1 монета за раз, без ThreadPool. Параллелизм ProcessPool только в
  оптимизаторе (по аналогии с WickFill). Добавлена WickFill-логика определения
  типа пула: на python3.14t (no GIL) → ThreadPoolExecutor, иначе ProcessPoolExecutor
  (_PoolExecutor/_POOL_TYPE). Это ключевое отличие WickFill — именно оно позволяет
  работать параллелизму на Android.

- v3.18: фикс зависания [0/795]. Проблема: ThreadPool запускал все 795 монет
  одновременно, каждая = fetch_candles + 50×2×60 симуляций — на Android с GIL
  первая монета заканчивалась через минуты, UI висел на [0/795]. Решение:
  max_cycles=10 для скринера (достаточно для ранжирования), print в stdout
  для видимости прогресса в Termux.

- v3.17: фикс зависания скринера. ProcessPoolExecutor заменён на ThreadPoolExecutor
  для скринера (IO-bound: fetch свечей + simulate) — на Android spawn 795 процессов
  вешает систему. Потоков max(4, NUM_WORKERS*2). Фикс кривого __import__ as_completed
  → нормальный импорт в шапке. ProcessPool оставлен только для оптимизатора.

- v3.16: параллелизм как в WickFill. ProcessPoolExecutor создаётся один раз при старте
  оптимизатора (initializer=_worker_init передаёт свечи в глобали воркера). Локальный
  поиск Basin Hopping теперь отправляет пачки соседей в пул (n_workers*2 за итерацию),
  результаты собираются через concurrent.futures.wait. Скринер тоже параллелен:
  ProcessPoolExecutor обрабатывает все монеты одновременно через as_completed.
  multiprocessing.set_start_method("spawn") в if __name__=="__main__" — fix падения
  fork на Android.

- v3.29: фикс зависания интерфейса. (1) /scan_all_status делал dict() —
  мелкая копия, active_workers мутировался потоком во время json.dumps →
  исключение в HTTP-обработчике. Теперь deep copy под локом. (2) do_GET
  обёрнут в try/except — раньше любое исключение в обработчике убивало
  поток сервера и всё переставало работать.
- v3.28: статус каждого потока скринера в реальном времени. screener_state
  добавлен active_workers {sym: {cycle, max_cycles, phase}} — каждый из 4
  потоков пишет свою фазу (fetch/opt) и номер цикла. pollScreener обновляется
  раз в секунду и показывает все активные воркеры построчно:
  "SYMBOL — загрузка свечей..." или "SYMBOL — цикл 12/50".
  screenerStatus многострочный (white-space:pre).
- v3.27: фикс зависания скринера на fetch. _fetch_candles принимает _stop_event:
  все sleep(5)/sleep(0.12) заменены на _stop_event.wait(timeout=...) — поток
  мгновенно просыпается при нажатии Стоп. При ошибке Gate.io в режиме скринера
  ждёт 1с вместо 5с. _run_one_sym_screener передаёт _screener_stop в fetch.
- v3.26: фикс зависания скринера на старте. (1) olog использовал opt_lock —
  4 потока скринера конкурировали с оптимизатором за один лок, вызывая deadlock;
  введён отдельный _log_lock. (2) _run_sym теперь принимает idx и сразу пишет
  sym_index при старте (а не только по завершении через as_completed) — счётчик
  [N/808] обновляется корректно с первой монеты.
- v3.25: параллельный скринер. run_screener заменён с последовательного for на
  ThreadPoolExecutor(max_workers=4) — 4 монеты прогоняются одновременно (~4x
  быстрее). ThreadPool безопасен на Android (нет spawn). Стоп работает корректно:
  отменяет ещё не стартовавшие задачи через fut.cancel(). Топ-20 обновляется
  по мере завершения каждой монеты через as_completed.
- v3.24: масштаб графика на Android. (1) Pinch-zoom двумя пальцами: сводим/
  разводим пальцы — свечи уменьшаются/увеличиваются (ratio расстояния между
  касаниями масштабирует текущий visibleRange); центр зума фиксируется в
  середине текущего вида. (2) По умолчанию при загрузке показываем последние
  80 свечей вместо 120 — чуть крупнее без зума.
- v3.4: скрининг всех фьючерсных пар Gate.io. Чекбокс "Все монеты"
  рядом с полем символа — запускает прогон каждой пары по 50 циклов.
  Прогресс [N/Total] + текущая монета в реальном времени. Топ-20 монет
  с WR/PF/DD/T/Return%/SL/TP/swing обновляется по ходу. Telegram-алерт
  с топ-3 по завершении. Кнопка Стоп останавливает скрининг.
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
- v1.9: надёжность автообновления графика. (1) при ошибке fetch таймер
  теперь перезапускается в .catch — раньше цепочка обрывалась и свеча
  могла не появиться никогда без ручного Загрузить; (2) добавлен
  обратный отсчёт в статусной строке "авто через Xs" — видно что
  обновление ожидается и когда именно.
- v1.8: (1) удалено поле "Риск на сделку" из UI (осталось в HTML с прошлой
  версии); (2) фикс приоритета малого числа сделок — добавлен trade_factor =
  log(trades+1) * min(trades/20, 1.0): при <20 сделок fitness режется
  пропорционально, конфиг с 18 сделками больше не обгоняет конфиг с 97.
- v1.7: смягчён RR-фильтр. Жёсткий запрет tp<sl убран — он перекашивал
  оптимизатор в сторону огромных TP с малым числом сделок. Оставлен только
  мягкий rr_bonus = sqrt(clamp(tp/sl, 0.7, 2.5)) — штрафует плохой RR
  но не запрещает его жёстко, оптимизатор сам находит баланс между
  WR, PF и RR.
- v1.6: (1) риск на сделку зафиксирован на 10% — убрано поле из UI,
  дефолт везде 10.0; (2) Telegram-алерт о новом лучшем конфиге шлётся
  только начиная с цикла 50 — первые 49 циклов оптимизатор "разогревается"
  и часто обновляет лучший, алерты были бы спамом.
- v1.5: фикс инвертированного RR — оптимизатор находил SL>TP конфиги (RR<1)
  потому что высокий WR с маленьким TP давал хороший PF без штрафа. Фиксы:
  (1) _simulate() отклоняет tp_pct < sl_pct в режиме оптимизации;
  (2) fitness *= sqrt(tp/sl) — бонус за RR>1, штраф за RR<1;
  (3) RR добавлен в метрики графика.
- v1.4: три фикса графика. (1) автообновление теперь срабатывает точно в момент
  закрытия бара (Date.now() % tf_sec), а не через целый ТФ после загрузки —
  раньше полчаса ждал новую свечу именно из-за этого; (2) шкала Y теперь
  учитывает TP/SL всех сигналов, у которых хоть часть зоны попадает в
  видимый диапазон (entry_i <= e && exit_i >= s), а не только тех, чей
  entry_i в зоне — поэтому TP/SL больше не вылазят за границу canvas;
  (3) при переключении вкладок браузера drawChart() пропускает ренеринг
  если ширина canvas равна 0, а по событию visibilitychange перерисовывает
  при возврате — убирает «мешанину» из накладывающихся рендеров.
- v1.3: настройка алертов через UI (по аналогии с WickFill). Поля TG Token /
  TG Chat ID / ntfy URL в сайдбаре, сохраняются в ~/.smc_alert_cfg.json
  (приоритет над env при старте) и подхватываются при перезапуске — больше
  не нужно экспортировать env-переменные руками каждый раз. Кнопка "Тест"
  реально проверяет доставку: для Telegram разбирает поле "ok" в ответе API
  (а не просто фиксирует факт отправки HTTP-запроса), для ntfy — код ответа.
  Эндпоинты: GET /alert_cfg, POST /alert_cfg, POST /alert_test.
"""
import os, sys, json, time, math, random, threading, base64, hashlib
import multiprocessing
import http.server, urllib.request, urllib.parse
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait as _fw, as_completed as _as_completed
import sys as _sys
# python3.14t (free-threaded, no GIL) не поддерживает ProcessPoolExecutor
if hasattr(_sys, '_is_gil_enabled') and not _sys._is_gil_enabled():
    _PoolExecutor = ThreadPoolExecutor
    _POOL_TYPE = "thread"
else:
    _PoolExecutor = ProcessPoolExecutor
    _POOL_TYPE = "process"

try:
    import requests
except ImportError:
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

APP_VERSION  = "3.48.3"
GATE_API     = "https://api.gateio.ws/api/v4"
NUM_WORKERS  = max(1, (multiprocessing.cpu_count() or 2) - 1)

# ─── Глобали воркера ProcessPool ────────────────────────────────────────────
_worker_candles = None
_worker_risk    = None
PORT         = 8765
GH_REPO      = os.environ.get("GH_REPO", "mambaleylo/smc-optimizer")
GH_TOKEN     = os.environ.get("GH_TOKEN", "")
TG_TOKEN     = os.environ.get("TG_TOKEN", "")
TG_CHAT      = os.environ.get("TG_CHAT", "")
NTFY_URL     = os.environ.get("NTFY_URL", "")
ALERT_CFG_PATH   = os.path.expanduser("~/.smc_alert_cfg.json")
FITNESS_W_PATH   = os.path.expanduser("~/.smc_fitness_weights.json")
GATE_CFG_PATH    = os.path.expanduser("~/.smc_gate_cfg.json")
GATE_KEY         = os.environ.get("GATE_KEY", "")
GATE_SECRET      = os.environ.get("GATE_SECRET", "")

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
_log_lock  = threading.Lock()  # отдельный лок для olog — не блокирует opt_lock из потоков скринера

# Эквалайзер весов fitness — тюнится "на ходу" со страницы (см. /fitness_weights).
# При всех весах=1.0 формула математически совпадает с исходной (см. _simulate).
fitness_w_lock  = threading.Lock()
FITNESS_WEIGHTS = {"wr": 1.0, "pf": 1.0, "trades": 1.0, "rr": 1.0, "dd": 1.0}

# ─── Автотюнинг весов (coordinate descent + walk-forward) ──────────────────
weight_tune_lock  = threading.Lock()
weight_tune_state = {
    "running": False, "logs": [],
    "stage": "",      # текущий этап: "WR weight: 0.5...", "done" и т.п.
    "best_weights": None,  # итоговые веса после тюнинга
    "n_windows": 4,   # кол-во train/test пар
    "bh_cycles": 20,  # BH-циклов на каждый train-кусок
    "passes": 2,      # проходов по всем 5 весам
}
_weight_tune_stop   = threading.Event()
_weight_tune_thread = None
opt_state  = {
    "running": False, "logs": [], "best": None, "top20": [],
    "cycle": 0, "trials": 0, "progress": 0,
    "symbol": "BTC_USDT", "tf": "15m", "days": 30,
    "sl_pct": 0.6, "tp_pct": 1.2, "risk_pct": 10.0,
    "chart": None, "fetch_pct": 0, "logs_dropped": 0,
    "eco_mode": False,
}
_stop_flag = threading.Event()
_opt_thread = None

screener_lock  = threading.Lock()
screener_state = {
    "running": False, "done": False,
    "current_sym": "", "sym_index": 0, "sym_total": 0,
    "current_cycle": 0, "max_cycles": 50,
    "results": [], "tf":"15m", "days":30,
    "sl_pct":0.6, "tp_pct":1.2, "risk_pct":10.0,
    "active_workers": {},  # sym -> {"cycle": N, "max_cycles": 50, "phase": "fetch"|"opt"}
}
_screener_stop   = threading.Event()
_screener_thread = None

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

# ─── Авто-торговля Gate.io ──────────────────────────────────────────────────
import hmac, hashlib, urllib.parse as _uparse

auto_trade_lock  = threading.Lock()
auto_trade_state = {
    "enabled": False, "symbol": None, "tf": None, "days": 30, "params": None,
    "risk_pct": 10.0,         # риск на сделку %
    "position_pct": 95.0,     # % депозита в маржу
    "position": None,         # текущая открытая позиция: {dir, entry, sl, tp, size, order_ids}
    "last_entry_ts": None,    # таймстемп свечи последнего сигнала
    "last_check": 0, "last_error": "",
    "auto_sync": False,       # подхватывать новый best от оптимизатора того же sym/tf на ходу
}
_auto_trade_stop   = threading.Event()
_auto_trade_thread = None

def _gate_sign(key, secret, method, url, query_str="", body_str=""):
    """HMAC-SHA512 подпись Gate.io API v4."""
    import hashlib as _hl
    body_hash = _hl.sha512(body_str.encode()).hexdigest()
    ts = str(int(time.time()))
    msg = "\n".join([method, url, query_str, body_hash, ts])
    sig = hmac.new(secret.encode(), msg.encode(), _hl.sha512).hexdigest()
    return {"KEY": key, "Timestamp": ts, "SIGN": sig}

def _gate_req(method, path, params=None, body=None):
    """Подписанный запрос к Gate.io Futures USDT API."""
    if not GATE_KEY or not GATE_SECRET:
        raise RuntimeError("Gate.io ключи не настроены")
    import hashlib as _hl
    query_str = _uparse.urlencode(params) if params else ""
    body_str  = json.dumps(body) if body else ""
    url_path  = f"/api/v4{path}"
    body_hash = _hl.sha512(body_str.encode()).hexdigest()
    ts = str(int(time.time()))
    msg = "\n".join([method, url_path, query_str, body_hash, ts])
    sig = hmac.new(GATE_SECRET.encode(), msg.encode(), _hl.sha512).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "KEY":       GATE_KEY,
        "Timestamp": ts,
        "SIGN":      sig,
    }
    url = f"https://fx-api.gateio.ws{url_path}"
    if query_str: url += "?" + query_str
    r = requests.request(method, url, headers=headers,
                         data=body_str if body_str else None, timeout=10)
    if not r.ok:
        raise RuntimeError(f"Gate {method} {path} → {r.status_code}: {r.text[:200]}")
    return r.json()

def _gate_get_position(symbol):
    """Текущая позиция по символу (None если нет)."""
    try:
        data = _gate_req("GET", f"/futures/usdt/positions/{symbol}")
        size = float(data.get("size", 0))
        if size == 0: return None
        return {
            "dir":    "long" if size > 0 else "short",
            "size":   abs(size),
            "entry":  float(data.get("entry_price", 0)),
        }
    except Exception as e:
        olog(f"⚠ gate_get_position: {e}")
        return None

def _gate_get_price(symbol):
    """Текущая цена фьючерса (mark price)."""
    try:
        data = requests.get(f"{GATE_API}/futures/usdt/contracts/{symbol}", timeout=5).json()
        return float(data.get("mark_price") or data.get("last_price", 0))
    except:
        return 0.0

def _gate_get_quanto(symbol):
    """Размер одного контракта в USDT (quanto_multiplier)."""
    try:
        data = requests.get(f"{GATE_API}/futures/usdt/contracts/{symbol}", timeout=5).json()
        return float(data.get("quanto_multiplier", 0.0001))
    except:
        return 0.0001

def _gate_get_balance():
    """Свободный баланс USDT."""
    try:
        data = _gate_req("GET", "/futures/usdt/accounts")
        return float(data.get("available", 0))
    except Exception as e:
        olog(f"⚠ gate_get_balance: {e}")
        return 0.0

def _gate_cancel_orders(symbol):
    """Отменить все открытые ордера по символу — и лимитные/рыночные,
    и триггерные price_orders (TP/SL). Оба эндпоинта нужно чистить,
    иначе старые TP/SL зависают и могут сработать на новую позицию."""
    contract = symbol.replace("/", "_").upper()
    try:
        _gate_req("DELETE", "/futures/usdt/orders",
                  params={"contract": contract, "status": "open"})
    except Exception as e:
        olog(f"⚠ gate_cancel_orders (orders) {contract}: {e}")
    try:
        _gate_req("DELETE", "/futures/usdt/price_orders",
                  params={"contract": contract, "status": "open"})
    except Exception as e:
        olog(f"⚠ gate_cancel_orders (price_orders) {contract}: {e}")

def _gate_close_position(symbol):
    """Закрыть позицию рыночным ордером."""
    try:
        contract = symbol.replace("/", "_").upper()
        pos = _gate_get_position(contract)
        if not pos: return
        _gate_cancel_orders(contract)  # снимает и orders, и price_orders (TP/SL)
        close_size = -int(pos["size"]) if pos["dir"] == "long" else int(pos["size"])
        _gate_req("POST", "/futures/usdt/orders", body={
            "contract":    contract,
            "size":        close_size,
            "price":       "0",
            "tif":         "ioc",
            "reduce_only": True,
            "text":        "t-smc-close",
        })
        olog(f"📤 Позиция закрыта: {contract} {pos['dir']}")
    except Exception as e:
        olog(f"⚠ gate_close_position {symbol}: {e}")

def _gate_round_price(price, contract):
    """Округляет цену до нужной точности (как в WickFill)."""
    if price > 1000:  return f"{price:.1f}"
    if price > 10:    return f"{price:.2f}"
    if price > 1:     return f"{price:.4f}"
    return f"{price:.6f}"

def _gate_open_position(symbol, direction, entry_px, sl_px, tp_px, risk_pct, **kwargs):
    """
    Полный цикл открытия позиции — точно как в WickFill:
      leverage = round(risk_pct / sl_pct)
      margin   = balance * risk_pct%
      size     = (margin * leverage) / (entry_px * qm)
      TP/SL    — price_orders с price="0" (маркет при триггере)
    """
    try:
        sl_pct_val   = abs(entry_px - sl_px) / entry_px * 100.0
        position_pct = kwargs.get("position_pct", risk_pct)  # % депо в маржу

        # 1. Баланс
        balance = _gate_get_balance()
        if not balance or balance <= 0:
            raise RuntimeError(f"Нет баланса: {balance}")

        # 2. Плечо = risk_pct / sl_pct  (как в WickFill)
        leverage = max(1, round(risk_pct / sl_pct_val))

        # 3. Устанавливаем плечо на Gate (2 попытки)
        applied_leverage = leverage
        contract = symbol.replace("/", "_").upper()
        try:
            r = _gate_req("POST", f"/futures/usdt/positions/{contract}/leverage",
                          params={"leverage": str(leverage)})
            applied_leverage = int(r.get("leverage", leverage)) if isinstance(r, dict) else leverage
            olog(f"✓ Плечо: {applied_leverage}×")
        except Exception as e:
            olog(f"⚠ Плечо попытка 1: {e} — повтор через 1с")
            time.sleep(1.0)
            try:
                r = _gate_req("POST", f"/futures/usdt/positions/{contract}/leverage",
                              params={"leverage": str(leverage)})
                applied_leverage = int(r.get("leverage", leverage)) if isinstance(r, dict) else leverage
                olog(f"✓ Плечо (попытка 2): {applied_leverage}×")
            except Exception as e2:
                olog(f"⚠ Плечо не применено: {e2} — используем leverage=1")
                applied_leverage = 1

        # 4. Размер позиции
        qm = _gate_get_quanto(symbol)
        margin   = balance * (position_pct / 100.0)
        size_raw = (margin * applied_leverage) / (entry_px * qm)
        size     = round(size_raw)
        if size < 1:
            raise RuntimeError(
                f"Недостаточно средств: balance={balance:.2f} margin={margin:.2f} "
                f"lev={applied_leverage}× ep={entry_px} qm={qm} → size={size_raw:.3f} < 1"
            )
        notional = size * entry_px * qm
        olog(f"🔓 Открываем {direction.upper()} {symbol}: "
             f"balance={balance:.2f} × {position_pct}%(маржа) × {applied_leverage}×(плечо) → позиция~{notional:.2f}U | "
             f"риск={risk_pct}% | size={size} контр | entry≈{_fmt_px(entry_px)} SL={_fmt_px(sl_px)} TP={_fmt_px(tp_px)}")

        # 5. Отменяем старые ордера
        _gate_cancel_orders(symbol)

        # 6. Маркет-ордер на вход
        is_long = (direction == "long")
        _gate_req("POST", "/futures/usdt/orders", body={
            "contract": contract,
            "size":     size if is_long else -size,
            "price":    "0",
            "tif":      "ioc",
            "text":     "t-smc-open",
        })
        time.sleep(1.0)

        close_size = -size if is_long else size

        # 7. TP триггерный маркет (как в WickFill: price="0", ioc)
        _gate_req("POST", "/futures/usdt/price_orders", body={
            "initial": {
                "contract":    contract,
                "size":        close_size,
                "price":       "0",
                "tif":         "ioc",
                "reduce_only": True,
                "text":        "t-smc-tp",
            },
            "trigger": {
                "strategy_type": 0,
                "price_type":    0,
                "price":         _gate_round_price(tp_px, contract),
                "rule":          1 if is_long else 2,
                "expiration":    86400,
            },
        })

        # 8. SL триггерный маркет
        _gate_req("POST", "/futures/usdt/price_orders", body={
            "initial": {
                "contract":    contract,
                "size":        close_size,
                "price":       "0",
                "tif":         "ioc",
                "reduce_only": True,
                "text":        "t-smc-sl",
            },
            "trigger": {
                "strategy_type": 0,
                "price_type":    0,
                "price":         _gate_round_price(sl_px, contract),
                "rule":          2 if is_long else 1,
                "expiration":    86400,
            },
        })

        olog(f"✅ {symbol} открыт + TP/SL выставлены")
        _send_alert(
            f"{'🟢' if is_long else '🔴'} <b>{symbol} SMC AUTO</b> — {direction.upper()}\n"
            f"Entry ≈ {_fmt_px(entry_px)} | TP {_fmt_px(tp_px)} | SL {_fmt_px(sl_px)}\n"
            f"Size {size} контр | ~{notional:.1f}U | {applied_leverage}×плечо"
        )
        return {"dir": direction, "entry": entry_px, "sl": sl_px, "tp": tp_px,
                "size": size, "leverage": applied_leverage, "notional": round(notional, 2)}
    except Exception as e:
        olog(f"⚠ gate_open_position {symbol}: {e}")
        return None

def _load_gate_cfg():
    global GATE_KEY, GATE_SECRET
    try:
        with open(GATE_CFG_PATH) as f:
            cfg = json.load(f)
        GATE_KEY    = cfg.get("gate_key",    GATE_KEY)    or GATE_KEY
        GATE_SECRET = cfg.get("gate_secret", GATE_SECRET) or GATE_SECRET
    except: pass

def _save_gate_cfg():
    try:
        with open(GATE_CFG_PATH, "w") as f:
            json.dump({"gate_key": GATE_KEY, "gate_secret": GATE_SECRET}, f)
    except Exception as e:
        olog(f"⚠ Не удалось сохранить gate cfg: {e}")

# ─── Поток авто-торговли ────────────────────────────────────────────────────
def _auto_trade_loop():
    """
    Раз в бар запускает _simulate() на свежих свечах.
    Если появился новый сигнал — закрывает старую позицию (если есть)
    и открывает новую через Gate.io API.
    """
    with auto_trade_lock:
        sym      = auto_trade_state["symbol"]
        tf       = auto_trade_state["tf"]
        days     = auto_trade_state["days"]
        p        = auto_trade_state["params"]
        risk_pct = auto_trade_state["risk_pct"]

    tf_sec = TF_SECONDS.get(tf, 900)
    olog(f"🤖 Авто-трейд запущен: {sym} {tf} risk={risk_pct}%")

    # Вооружаемся — запоминаем текущий сигнал без открытия
    armed = False
    last_entry_ts = None

    while not _auto_trade_stop.is_set():
        try:
            with auto_trade_lock:
                new_p        = auto_trade_state["params"]
                risk_pct     = auto_trade_state["risk_pct"]
            if new_p != p:
                olog(f"🔁 Авто-трейд: параметры обновлены (синк с оптимизатором) — "
                     f"swing={new_p.get('swing_len')} SL={new_p.get('sl_pct')}% TP={new_p.get('tp_pct')}%")
                p = new_p
            candles = _fetch_candles(sym, tf, days)
            if candles and len(candles) > 50:
                result = _simulate(candles, p, sl_pct=p.get("sl_pct"),
                                   tp_pct=p.get("tp_pct"), _collect=True)
                with auto_trade_lock:
                    auto_trade_state["last_check"] = time.time()

                if result:
                    sigs = result.get("signals") or []
                    if sigs:
                        sig = sigs[-1]
                        entry_ts = candles[sig["entry_i"]]["t"]

                        if not armed:
                            armed         = True
                            last_entry_ts = entry_ts
                            olog(f"🤖 Авто-трейд вооружён, текущий сигнал: "
                                 f"{sig['dir'].upper()} entry={_fmt_px(sig['entry'])}")
                        elif entry_ts != last_entry_ts:
                            # Новый сигнал!
                            last_entry_ts = entry_ts
                            direction     = sig["dir"]
                            entry_px      = sig["entry"]
                            sl_px         = sig["sl"]
                            tp_px         = sig["tp"]

                            existing = _gate_get_position(sym)
                            if existing and existing["dir"] == direction:
                                # entry_ts сменился (структура OB/swing
                                # переразметилась на новой свече), но
                                # направление совпадает с уже открытой на
                                # бирже позицией — TP/SL ордера от исходного
                                # входа продолжают действовать сами, реальная
                                # позиция TP/SL ещё не задевала. Закрывать и
                                # переоткрывать здесь только в убыток на
                                # спреде/комиссии без всякой выгоды — не трогаем.
                                olog(f"↔ Сигнал обновился ({direction.upper()} "
                                     f"entry={_fmt_px(entry_px)}), но направление совпадает с "
                                     f"открытой позицией {existing['dir'].upper()} — не трогаем, "
                                     f"TP/SL уже выставлены")
                                with auto_trade_lock:
                                    auto_trade_state["last_entry_ts"] = entry_ts
                            else:
                                olog(f"🤖 Новый сигнал: {direction.upper()} "
                                     f"entry={_fmt_px(entry_px)} sl={_fmt_px(sl_px)} tp={_fmt_px(tp_px)}")

                                # Закрываем старую позицию (если есть, и направление другое)
                                if existing:
                                    olog(f"🔄 Закрываем старую позицию {existing['dir'].upper()} "
                                         f"перед открытием новой ({direction.upper()})")
                                    _gate_close_position(sym)
                                    time.sleep(1.0)

                                # Открываем новую
                                with auto_trade_lock:
                                    pos_pct = auto_trade_state.get("position_pct", risk_pct)
                                pos_info = _gate_open_position(
                                    sym, direction, entry_px, sl_px, tp_px, risk_pct,
                                    position_pct=pos_pct)
                                with auto_trade_lock:
                                    auto_trade_state["position"] = pos_info
                                    auto_trade_state["last_entry_ts"] = entry_ts
                        else:
                            # Тот же сигнал — просто логируем статус позиции
                            cur_price = _gate_get_price(sym)
                            with auto_trade_lock:
                                auto_trade_state["last_check"] = time.time()
                                auto_trade_state["last_error"] = ""

        except Exception as e:
            olog(f"⚠ Авто-трейд ошибка: {e}")
            with auto_trade_lock:
                auto_trade_state["last_error"] = str(e)

        now = time.time()
        sleep_for = tf_sec - (now % tf_sec) + 3
        _auto_trade_stop.wait(timeout=max(5, sleep_for))

    olog("🛑 Авто-трейд остановлен")
    with auto_trade_lock:
        auto_trade_state["enabled"] = False


def _ts():
    return time.strftime("[%H:%M:%S]")

def olog(msg):
    with _log_lock:
        opt_state["logs"].append({"ts": time.strftime("%H:%M:%S"), "msg": msg})
        if len(opt_state["logs"]) > 500:
            opt_state["logs"] = opt_state["logs"][-300:]
            opt_state["logs_dropped"] = opt_state.get("logs_dropped",0) + 200

# ─── Gate.io fetch ──────────────────────────────────────────────────────────
def _fetch_all_symbols():
    try:
        # Тикеры содержат volume_24h_usd — объём за 24ч в USDT, лучший показатель ликвидности
        r = requests.get(f"{GATE_API}/futures/usdt/tickers", timeout=15)
        if r.status_code != 200: return []
        data = r.json()
        if not isinstance(data, list): return []
        valid = [t for t in data
                 if isinstance(t, dict) and "_USDT" in t.get("contract","")]
        valid.sort(key=lambda t: float(t.get("volume_24h_usd") or t.get("volume_24h_quote") or t.get("volume_24h") or 0), reverse=True)
        top50 = [t["contract"] for t in valid[:100]]
        olog(f"Топ-100 по объёму 24h: {', '.join(top50)}")
        return top50
    except Exception as e:
        olog(f"fetch_all_symbols error: {e}")
        return []

def _fetch_candles(symbol, tf, days, _stop_event=None):
    interval_sec = TF_SECONDS.get(tf, 3600)
    now   = int(time.time())
    since = now - days * 86400
    LIMIT = 999
    all_candles = []
    current_from = since
    fail_count = 0
    MAX_FAILS = 5
    while current_from < now:
        if _stop_event and _stop_event.is_set(): return []
        try:
            r = requests.get(f"{GATE_API}/futures/usdt/candlesticks",
                params={"contract":symbol,"interval":tf,"from":current_from,"limit":LIMIT},
                timeout=15)
            if r.status_code != 200:
                fail_count += 1
                olog(f"⚠ Gate.io {r.status_code} для {symbol}: {r.text[:200]}")
                if fail_count >= MAX_FAILS:
                    olog(f"❌ {symbol}: {fail_count} ошибок подряд — контракт не существует "
                         f"или недоступен на Gate.io Futures, прерываю загрузку")
                    break
                sleep_t = 1 if _stop_event else 5
                if _stop_event:
                    _stop_event.wait(timeout=sleep_t)
                else:
                    time.sleep(sleep_t)
                continue
            fail_count = 0
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
            if _stop_event:
                if _stop_event.is_set(): return []
                _stop_event.wait(timeout=0.12)
            else:
                time.sleep(0.12)
        except Exception as e:
            fail_count += 1
            olog(f"fetch error: {e}")
            if fail_count >= MAX_FAILS:
                olog(f"❌ {symbol}: {fail_count} ошибок подряд, прерываю загрузку")
                break
            sleep_t = 1 if _stop_event else 5
            if _stop_event:
                _stop_event.wait(timeout=sleep_t)
            else:
                time.sleep(sleep_t)
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
def _simulate(candles, p, sl_pct=None, tp_pct=None, risk_pct=10.0,
              init_deposit=1000.0, _collect=False, fitness_weights=None):
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
            open_i = candles[i]["open"]
            if trade_dir == "long":
                sl_hit = (low_i  <= sl_price)
                tp_hit = (high_i >= tp_price)
                if sl_hit and tp_hit:
                    # Оба задеты на одной свече — побеждает тот, что ближе к open
                    sl_hit = abs(open_i - sl_price) <= abs(open_i - tp_price)
                    tp_hit = not sl_hit
                if sl_hit:
                    pnl = equity * (risk_pct/100.0) * (-1.0)
                    equity += pnl
                    trades.append({"dir":"long","entry":entry_px,"exit":sl_price,
                                   "pnl_pct":-sl_pct,"pnl":pnl,"win":False,"i":i})
                    if _collect:
                        _lev = max(1, round(risk_pct / sl_pct))
                        signals.append({"dir":"long","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":False,
                                        "dep_pct": round(-risk_pct, 1), "lev": _lev})
                    in_trade = False
                elif tp_hit:
                    rr = tp_pct / sl_pct
                    pnl = equity * (risk_pct/100.0) * rr
                    equity += pnl
                    trades.append({"dir":"long","entry":entry_px,"exit":tp_price,
                                   "pnl_pct":tp_pct,"pnl":pnl,"win":True,"i":i})
                    if _collect:
                        _lev = max(1, round(risk_pct / sl_pct))
                        signals.append({"dir":"long","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":True,
                                        "dep_pct": round(risk_pct * (tp_pct/sl_pct), 1), "lev": _lev})
                    in_trade = False
            else:  # short
                sl_hit = (high_i >= sl_price)
                tp_hit = (low_i  <= tp_price)
                if sl_hit and tp_hit:
                    sl_hit = abs(open_i - sl_price) <= abs(open_i - tp_price)
                    tp_hit = not sl_hit
                if sl_hit:
                    pnl = equity * (risk_pct/100.0) * (-1.0)
                    equity += pnl
                    trades.append({"dir":"short","entry":entry_px,"exit":sl_price,
                                   "pnl_pct":-sl_pct,"pnl":pnl,"win":False,"i":i})
                    if _collect:
                        _lev = max(1, round(risk_pct / sl_pct))
                        signals.append({"dir":"short","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":False,
                                        "dep_pct": round(-risk_pct, 1), "lev": _lev})
                    in_trade = False
                elif tp_hit:
                    rr = tp_pct / sl_pct
                    pnl = equity * (risk_pct/100.0) * rr
                    equity += pnl
                    trades.append({"dir":"short","entry":entry_px,"exit":tp_price,
                                   "pnl_pct":tp_pct,"pnl":pnl,"win":True,"i":i})
                    if _collect:
                        _lev = max(1, round(risk_pct / sl_pct))
                        signals.append({"dir":"short","entry_i":entry_i,"exit_i":i,
                                        "entry":entry_px,"tp":tp_price,"sl":sl_price,"win":True,
                                        "dep_pct": round(risk_pct * (tp_pct/sl_pct), 1), "lev": _lev})
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
                # v3.22: SL и TP — чистый % от entry (как в WickFill), симметрично.
                # OB используется только как триггер входа, не как якорь стопа —
                # раньше sl_price считался от ob_lo (низа order block), который мог
                # оказаться в десятках свечей назад и в разы дальше entry, чем tp_pct.
                # На графике это выглядело как микро-тейк/мега-стоп, а в бэктесте
                # SL почти не задевался → WR 88%+ и Return 10000%+ (нереалистично).
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
    # Fitness: WR × PF × log(trades) / (1+max_dd) — штраф за просадку.
    # v3.34: каждый множитель взвешен через FITNESS_WEIGHTS (эквалайзер,
    # тюнится на ходу со страницы). log_fit = Σ w_i·log(factor_i) →
    # fitness = exp(log_fit); при всех весах=1.0 это математически та же
    # формула, что раньше (произведение = exp суммы логарифмов). Увеличение
    # веса усиливает влияние множителя на ранжирование конфигов в поиске —
    # например, выкрутив "Кол-во" выше 1.0, оптимизатор сильнее предпочитает
    # конфиги с бо́льшим числом сделок.
    rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 1.0
    rr_bonus = math.sqrt(min(max(rr_ratio, 0.7), 2.5))  # мягкий бонус за RR
    # Штраф за малое число сделок: при <20 сделках fitness режется сильнее
    trade_factor = math.log(len(trades) + 1) * min(len(trades) / 20.0, 1.0)
    if fitness_weights is None:
        with fitness_w_lock:
            fitness_weights = dict(FITNESS_WEIGHTS)
    fw = fitness_weights
    _eps = 1e-6
    log_fit = (
        fw.get("wr",     1.0) * math.log(max(wr, _eps)) +
        fw.get("pf",     1.0) * math.log(max(min(pf, 5.0), _eps)) +
        fw.get("trades", 1.0) * math.log(max(trade_factor, _eps)) +
        fw.get("rr",     1.0) * math.log(max(rr_bonus, _eps)) -
        fw.get("dd",     1.0) * math.log(max(1 + max_dd, _eps))
    )
    fitness = math.exp(log_fit)
    result["fitness"] = round(fitness, 6)
    result["rr"] = round(tp_pct / sl_pct if sl_pct > 0 else 1.0, 2)

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

def _load_fitness_weights():
    """Подхватывает сохранённые веса эквалайзера fitness из файла."""
    try:
        with open(FITNESS_W_PATH, "r") as f:
            cfg = json.load(f)
        with fitness_w_lock:
            for k in FITNESS_WEIGHTS:
                if k in cfg:
                    try:
                        FITNESS_WEIGHTS[k] = float(cfg[k])
                    except (TypeError, ValueError):
                        pass
    except FileNotFoundError:
        pass
    except Exception as e:
        olog(f"⚠ Не удалось прочитать {FITNESS_W_PATH}: {e}")

def _save_fitness_weights():
    try:
        with fitness_w_lock:
            snap = dict(FITNESS_WEIGHTS)
        with open(FITNESS_W_PATH, "w") as f:
            json.dump(snap, f)
    except Exception as e:
        olog(f"⚠ Не удалось сохранить {FITNESS_W_PATH}: {e}")

def _wtlog(msg):
    """Лог в weight_tune_state."""
    with weight_tune_lock:
        weight_tune_state["logs"].append({"ts": time.strftime("%H:%M:%S"), "msg": msg})
        if len(weight_tune_state["logs"]) > 200:
            weight_tune_state["logs"] = weight_tune_state["logs"][-150:]

def _wt_bh_on_slice(candles_slice, sl_p, tp_p, risk, fw, cycles=20):
    """Мини-BH на одном куске свечей с заданными весами fw.
    Возвращает лучший params + result.
    sl_p/tp_p всегда передаются явно в _simulate — они не входят в PARAM_SPACE
    и не генерируются _random_params/_neighbour/_shake."""
    best_p = _random_params()
    best_p["sl_pct"] = sl_p; best_p["tp_pct"] = tp_p
    best_r = _simulate(candles_slice, best_p, sl_pct=sl_p, tp_pct=tp_p,
                       risk_pct=risk, fitness_weights=fw)
    best_f = best_r["fitness"] if best_r else 0.0
    for cyc in range(1, cycles + 1):
        if _weight_tune_stop.is_set():
            break
        temp = 1.0 * math.exp(-0.05 * cyc)
        for start_p in [_shake(best_p, 0.4), _random_params()]:
            start_p["sl_pct"] = sl_p; start_p["tp_pct"] = tp_p
            cur_r = _simulate(candles_slice, start_p, sl_pct=sl_p, tp_pct=tp_p,
                              risk_pct=risk, fitness_weights=fw)
            cur_p = start_p
            cur_f = cur_r["fitness"] if cur_r else 0.0
            for _ in range(30):
                if _weight_tune_stop.is_set(): break
                nb_p = _neighbour(cur_p)
                nb_p["sl_pct"] = sl_p; nb_p["tp_pct"] = tp_p
                nb_r = _simulate(candles_slice, nb_p, sl_pct=sl_p, tp_pct=tp_p,
                                 risk_pct=risk, fitness_weights=fw)
                if not nb_r: continue
                nfit = nb_r["fitness"]
                delta = nfit - cur_f
                if delta > 0 or random.random() < math.exp(delta / max(temp, 0.001)):
                    cur_p, cur_f, cur_r = nb_p, nfit, nb_r
                if nfit > best_f:
                    best_f, best_p, best_r = nfit, nb_p, nb_r
    return best_p, best_r

def _wt_eval_weight(key, val, current_fw, windows, sl_p, tp_p, risk, bh_cycles):
    """Для одного значения одного веса: считает средний OOS-результат по всем окнам.
    Возвращает средний total_return на test-кусках (честная оценка OOS)."""
    fw = dict(current_fw)
    fw[key] = val
    oos_returns = []
    for (train_c, test_c) in windows:
        if _weight_tune_stop.is_set(): return None
        best_p, _ = _wt_bh_on_slice(train_c, sl_p, tp_p, risk, fw, bh_cycles)
        if best_p is None: continue
        test_r = _simulate(test_c, best_p, sl_pct=sl_p, tp_pct=tp_p, risk_pct=risk)
        if test_r and test_r.get("trades", 0) >= 3:
            oos_returns.append(test_r.get("total_return", 0.0))
    if not oos_returns:
        return None
    return sum(oos_returns) / len(oos_returns)

def _run_weight_tune():
    """Coordinate descent + walk-forward автотюнинг 5 весов эквалайзера.
    Алгоритм:
      1. Делим историю на N окон (train 60% + test 40% со сдвигом).
      2. Для каждого веса перебираем сетку [0.5,1.0,1.5,2.0,3.0].
      3. Для каждого значения: BH на train → оцениваем на test (OOS).
      4. Выбираем значение с лучшим средним OOS total_return.
      5. Зафиксированные веса применяем глобально и сохраняем.
      6. Повторяем passes раз (сходимость).
    """
    global _weight_tune_thread
    with weight_tune_lock:
        weight_tune_state["running"] = True
        weight_tune_state["logs"] = []
        weight_tune_state["best_weights"] = None

    try:
        # Читаем текущие параметры оптимизатора для SL/TP/risk
        with opt_lock:
            sym  = opt_state["symbol"]
            tf   = opt_state["tf"]
            days = int(opt_state["days"])
            sl_p = float(opt_state["sl_pct"])
            tp_p = float(opt_state["tp_pct"])
            risk = float(opt_state["risk_pct"])
        with weight_tune_lock:
            n_windows  = weight_tune_state["n_windows"]
            bh_cycles  = weight_tune_state["bh_cycles"]
            passes     = weight_tune_state["passes"]

        _wtlog(f"▶ Автотюнинг весов | {sym} {tf} {days}д | {n_windows} окон, {bh_cycles} BH-цикл/окно, {passes} прохода")

        # Загружаем свечи
        candles = _fetch_candles(sym, tf, days)
        if not candles or len(candles) < 200:
            _wtlog("❌ Мало свечей (нужно ≥200), остановка")
            with weight_tune_lock: weight_tune_state["running"] = False
            return

        _wtlog(f"✔ Загружено {len(candles)} свечей")

        # Строим train/test окна
        # Каждое окно: train = 60% общей длины, test = следующие 40%/(n_windows-1) свечей
        # Окна сдвигаем вправо так, чтобы покрыть всю историю
        total = len(candles)
        train_ratio = 0.6
        train_size  = int(total * train_ratio)
        remain_size = total - train_size   # для test-кусков
        window_step = max(1, remain_size // n_windows)
        test_size   = window_step          # размер одного test-куска

        windows = []
        for i in range(n_windows):
            t_start = i * window_step
            t_end   = t_start + train_size
            v_start = t_end
            v_end   = min(v_start + test_size, total)
            if v_end <= v_start or t_end > total:
                break
            windows.append((candles[t_start:t_end], candles[v_start:v_end]))

        if not windows:
            _wtlog("❌ Не удалось построить окна, остановка")
            with weight_tune_lock: weight_tune_state["running"] = False
            return

        _wtlog(f"✔ Построено {len(windows)} train/test окон "
               f"(train≈{len(windows[0][0])} свечей, test≈{len(windows[0][1])} свечей)")

        # Стартовые веса — текущие из глобального эквалайзера
        with fitness_w_lock:
            current_fw = dict(FITNESS_WEIGHTS)

        GRID = [0.5, 1.0, 1.5, 2.0, 3.0]
        WR_KEYS = ["wr", "pf", "trades", "rr", "dd"]
        WR_NAMES = {"wr": "WinRate", "pf": "ProfitFactor", "trades": "Кол-во сделок",
                    "rr": "RR", "dd": "Просадка"}

        for pass_i in range(1, passes + 1):
            if _weight_tune_stop.is_set(): break
            _wtlog(f"━━ Проход {pass_i}/{passes} ━━")
            for key in WR_KEYS:
                if _weight_tune_stop.is_set(): break
                _wtlog(f"  🔍 {WR_NAMES[key]} (текущий={current_fw[key]:.2f}): "
                       f"перебираем {GRID}...")
                with weight_tune_lock:
                    weight_tune_state["stage"] = f"Проход {pass_i}: {WR_NAMES[key]}"

                best_val  = current_fw[key]
                best_oos  = None

                for val in GRID:
                    if _weight_tune_stop.is_set(): break
                    _wtlog(f"    {WR_NAMES[key]}={val}: оцениваем OOS...")
                    oos = _wt_eval_weight(key, val, current_fw, windows,
                                          sl_p, tp_p, risk, bh_cycles)
                    if oos is None:
                        _wtlog(f"    {WR_NAMES[key]}={val}: ❌ мало сделок на тесте, пропуск")
                        continue
                    _wtlog(f"    {WR_NAMES[key]}={val}: OOS avg return={oos:.2f}%")
                    if best_oos is None or oos > best_oos:
                        best_oos = oos
                        best_val = val

                if best_oos is not None:
                    old_val = current_fw[key]
                    current_fw[key] = best_val
                    _wtlog(f"  ✅ {WR_NAMES[key]}: {old_val:.2f} → {best_val:.2f} "
                           f"(OOS={best_oos:.2f}%)")
                else:
                    _wtlog(f"  ⚠ {WR_NAMES[key]}: не удалось выбрать (нет данных), оставляем {current_fw[key]:.2f}")

        if _weight_tune_stop.is_set():
            _wtlog("⏹ Прервано пользователем")
            with weight_tune_lock:
                weight_tune_state["running"] = False
                weight_tune_state["stage"]   = "остановлено"
            return

        # Применяем найденные веса глобально
        with fitness_w_lock:
            for k in FITNESS_WEIGHTS:
                FITNESS_WEIGHTS[k] = current_fw.get(k, 1.0)
        _save_fitness_weights()

        summary = " | ".join(f"{WR_NAMES[k]}={current_fw[k]:.2f}" for k in WR_KEYS)
        _wtlog(f"🏆 Автотюнинг завершён: {summary}")
        _wtlog("✔ Веса применены к эквалайзеру и сохранены")
        _send_alert(f"🎛 SMC Автотюнинг весов завершён\n{summary}")

        with weight_tune_lock:
            weight_tune_state["best_weights"] = dict(current_fw)
            weight_tune_state["stage"] = "done"

    except Exception as e:
        _wtlog(f"❌ Ошибка автотюнинга: {e}")
    finally:
        with weight_tune_lock:
            weight_tune_state["running"] = False


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
        olog("❌ Мало свечей, остановка")
        with opt_lock: opt_state["running"] = False
        return
    olog(f"✔ Загружено {len(candles)} свечей")

    n_workers = NUM_WORKERS
    olog(f"⚙ Запуск {'ThreadPool' if _POOL_TYPE=='thread' else 'ProcessPool'} ({n_workers} {'потоков' if _POOL_TYPE=='thread' else 'процессов'})...")
    pool = _PoolExecutor(
        max_workers=n_workers,
        initializer=_worker_init,
        initargs=(candles, risk)
    )

    best_params  = _random_params()
    best_params["sl_pct"] = sl_p; best_params["tp_pct"] = tp_p
    best_result  = _simulate(candles, best_params, sl_pct=sl_p, tp_pct=tp_p, risk_pct=risk)
    best_fit     = best_result["fitness"] if best_result else 0.0
    top20        = []
    cycle        = 0
    TEMP_START   = 1.0
    STEPS        = 60   # шагов локального поиска за старт
    no_improve   = 0    # циклов без улучшения глобального best
    SHAKE_AFTER  = 5    # мягкая встряска через N циклов без улучшения
    RESTART_AFTER= 15   # полный рестарт через N циклов без улучшения

    # ── Режим слабой производительности (телефон греется на долгих прогонах) ──
    # После ECO_AFTER_CYCLE циклов снижаем параллелизм (меньше воркеров в
    # батче за раз — CPU/NPU меньше греется) и добавляем паузы между батчами
    # и между циклами — цикл становится длиннее и менее "жадным" к ресурсам.
    ECO_AFTER_STAGNATION = 10   # циклов без улучшения → включить эко
    ECO_WORKERS_DIV = 2         # урезаем параллелизм в эко-режиме в N раз
    ECO_BATCH_PAUSE = 0.4       # сек, пауза между пачками внутри цикла
    ECO_CYCLE_PAUSE = 8.0       # сек, пауза между циклами
    _eco_announced  = False

    with opt_lock:
        opt_state["top20"] = top20
        opt_state["best"]  = None

    try:
        while not _stop_flag.is_set():
            cycle += 1
            temp = TEMP_START * math.exp(-0.05 * cycle)
            eco_mode = no_improve >= ECO_AFTER_STAGNATION
            with opt_lock:
                opt_state["cycle"] = cycle
                opt_state["eco_mode"] = eco_mode
            if eco_mode and not _eco_announced:
                _eco_announced = True
                olog(f"🌡 Цикл {cycle}: стагнация {no_improve} циклов — включён эко-режим "
                     f"(меньше параллелизма, паузы между циклами)")
            elif not eco_mode and _eco_announced:
                _eco_announced = False
                olog(f"⚡ Цикл {cycle}: новый best — эко-режим выключен, возврат к полной скорости")

            # ── Защита от тупиков ──────────────────────────────────────────
            if no_improve >= RESTART_AFTER:
                olog(f"🔄 Цикл {cycle}: {no_improve} циклов без улучшения — полный рестарт")
                best_params = _random_params()
                best_params["sl_pct"] = sl_p; best_params["tp_pct"] = tp_p
                no_improve  = 0
            elif no_improve >= SHAKE_AFTER:
                strength = 0.5 + 0.05 * (no_improve - SHAKE_AFTER)  # 0.5→0.75
                olog(f"⚡ Цикл {cycle}: встряска strength={strength:.2f} (стагнация {no_improve})")

            # Несколько стартовых точек за цикл
            starts = [_shake(best_params, 0.4) if best_params else _random_params(),
                      _random_params()]
            if len(top20) > 2:
                starts.append(_shake(random.choice(top20)["params"], 0.3))
            if no_improve >= SHAKE_AFTER:
                strength = 0.5 + 0.05 * (no_improve - SHAKE_AFTER)
                starts.append(_shake(best_params, min(strength, 0.9)))
                if len(top20) > 0:
                    starts.append(_shake(top20[0]["params"], min(strength, 0.9)))

            for start_p in starts:
                if _stop_flag.is_set(): break
                current_p   = start_p
                current_r   = _simulate(candles, current_p, risk_pct=risk)
                current_fit = current_r["fitness"] if current_r else 0.0

                # Параллельный локальный поиск: генерируем n_workers*STEPS соседей
                # пачками по n_workers за итерацию
                steps_done = 0
                while steps_done < STEPS and not _stop_flag.is_set():
                    workers_now = max(1, n_workers // ECO_WORKERS_DIV) if eco_mode else n_workers
                    batch_size = min(workers_now * 2, STEPS - steps_done)
                    neighbours = [_neighbour(current_p) for _ in range(batch_size)]
                    # Свежий снэпшот эквалайзера на каждую пачку — позволяет
                    # тюнить веса "на ходу" во время работы оптимизатора
                    with fitness_w_lock:
                        _fw_snap = dict(FITNESS_WEIGHTS)
                    futs = [pool.submit(_worker_simulate, nb, _fw_snap) for nb in neighbours]
                    _fw(futs, timeout=30)

                    with opt_lock:
                        opt_state["trials"]   = opt_state.get("trials", 0) + batch_size
                        opt_state["progress"] = int((steps_done + batch_size) / STEPS * 100)

                    for nb_p, fut in zip(neighbours, futs):
                        try:
                            nb_r = fut.result()
                        except Exception:
                            nb_r = None
                        if not nb_r:
                            continue
                        nfit  = nb_r["fitness"]
                        delta = nfit - current_fit
                        if delta > 0 or random.random() < math.exp(delta / max(temp, 0.001)):
                            current_p   = nb_p
                            current_fit = nfit
                            current_r   = nb_r

                        if nfit > best_fit or (delta > 0):
                            # Обновляем топ-20
                            with opt_lock:
                                top20 = opt_state["top20"]
                                entry = {"params": nb_p, "result": nb_r}
                                top20 = [e for e in top20 if abs(e["result"]["fitness"] - nfit) > 0.001]
                                top20.append(entry)
                                top20.sort(key=lambda x: x["result"]["fitness"], reverse=True)
                                opt_state["top20"] = top20[:20]

                        if nfit > best_fit:
                            best_fit    = nfit
                            best_params = nb_p
                            best_result = nb_r
                            no_improve  = 0
                            with opt_lock:
                                opt_state["best"] = {"params": nb_p, "result": nb_r}
                            olog(f"🏆 Цикл {cycle} шаг {steps_done} | "
                                 f"WR={nb_r['winrate']}% PF={nb_r['profit_factor']} "
                                 f"DD={nb_r['max_dd']}% T={nb_r['trades']} "
                                 f"fit={nfit:.4f} | "
                                 f"SL={nb_p['sl_pct']}% TP={nb_p['tp_pct']}% "
                                 f"swing={nb_p['swing_len']}")
                            threading.Thread(target=_gh_save_best,
                                args=({"params": nb_p, "result": nb_r},), daemon=True).start()
                            if cycle >= 50:
                                _send_alert(
                                    f"🏆 SMC {sym} {tf} — новый лучший\n"
                                    f"WR={nb_r['winrate']}% PF={nb_r['profit_factor']} "
                                    f"DD={nb_r['max_dd']}% Trades={nb_r['trades']}\n"
                                    f"SL={nb_p['sl_pct']}% TP={nb_p['tp_pct']}% "
                                    f"swing={nb_p['swing_len']}"
                                )

                            # Опционально подкидываем новые параметры живой авто-торговле
                            # того же символа/ТФ, если включён чекбокс синхронизации.
                            # TP/SL уже открытой на бирже позиции это не меняет —
                            # только то, как _auto_trade_loop будет искать СЛЕДУЮЩИЙ сигнал.
                            with auto_trade_lock:
                                _at_on  = auto_trade_state["enabled"]
                                _at_sym = auto_trade_state["symbol"]
                                _at_tf  = auto_trade_state["tf"]
                                _at_syn = auto_trade_state.get("auto_sync")
                            if _at_on and _at_syn and _at_sym == sym and _at_tf == tf:
                                with auto_trade_lock:
                                    auto_trade_state["params"] = dict(nb_p)
                                olog(f"🔁 Новый best отправлен в авто-трейд {sym} {tf} "
                                     f"(swing={nb_p['swing_len']} SL={nb_p['sl_pct']}% TP={nb_p['tp_pct']}%)")

                    steps_done += batch_size
                    if eco_mode:
                        _stop_flag.wait(timeout=ECO_BATCH_PAUSE)

            # Счётчик стагнации
            no_improve += 1
            olog(f"Цикл {cycle} завершён | best fit={best_fit:.4f} | стагнация={no_improve}")
            if eco_mode:
                _stop_flag.wait(timeout=ECO_CYCLE_PAUSE)

    finally:
        try:
            pool.shutdown(wait=False)
        except Exception:
            pass

    olog("⏹ Остановлено")
    with opt_lock: opt_state["running"] = False

def _run_one_sym_screener(sym, tf, days, sl_p, tp_p, risk, max_cycles=50, on_cycle=None):
    candles = _fetch_candles(sym, tf, days, _stop_event=_screener_stop)
    if not candles or len(candles) < 100: return None
    best_params = _random_params()
    best_params["sl_pct"] = sl_p; best_params["tp_pct"] = tp_p
    best_result = _simulate(candles, best_params, sl_pct=sl_p, tp_pct=tp_p, risk_pct=risk)
    best_fit    = best_result["fitness"] if best_result else 0.0
    for cycle in range(1, max_cycles + 1):
        if _screener_stop.is_set(): return None
        if on_cycle: on_cycle(cycle, max_cycles)
        temp = 1.0 * math.exp(-0.05 * cycle)
        for start_p in [_shake(best_params, 0.4), _random_params()]:
            if _screener_stop.is_set(): return None
            cur_p = start_p
            cur_r = _simulate(candles, cur_p, risk_pct=risk)
            cur_f = cur_r["fitness"] if cur_r else 0.0
            for _ in range(60):
                if _screener_stop.is_set(): return None
                nb_p = _neighbour(cur_p)
                nb_r = _simulate(candles, nb_p, risk_pct=risk)
                if not nb_r: continue
                nfit = nb_r["fitness"]
                delta = nfit - cur_f
                if delta > 0 or random.random() < math.exp(delta / max(temp, 0.001)):
                    cur_p, cur_f, cur_r = nb_p, nfit, nb_r
                if nfit > best_fit:
                    best_fit, best_params, best_result = nfit, nb_p, nb_r
    return {"sym": sym, "params": best_params, "result": best_result} if best_result else None

def _worker_init(candles, risk):
    """Инициализатор ProcessPool — загружает свечи в глобали воркера один раз."""
    global _worker_candles, _worker_risk
    _worker_candles = candles
    _worker_risk    = risk

def _worker_simulate(p, fw=None):
    """Вызов _simulate из воркера ProcessPool (использует глобали).
    fw — снэпшот весов эквалайзера: у отдельного процесса своя память,
    обновления FITNESS_WEIGHTS в основном процессе сами туда не долетят —
    поэтому передаём явно при каждом submit (см. run_optimizer)."""
    try:
        return _simulate(_worker_candles, p, risk_pct=_worker_risk, fitness_weights=fw)
    except Exception:
        return None

def _screener_worker(args):
    """Воркер для ProcessPoolExecutor — обрабатывает одну монету."""
    sym, tf, days, sl_p, tp_p, risk = args
    try:
        return _run_one_sym_screener(sym, tf, days, sl_p, tp_p, risk)
    except Exception:
        return None

def run_screener():
    global _screener_thread
    tf   = screener_state["tf"]
    days = screener_state["days"]
    sl_p = screener_state["sl_pct"]
    tp_p = screener_state["tp_pct"]
    risk = screener_state["risk_pct"]
    with screener_lock:
        screener_state.update({"results":[],"done":False,"sym_index":0,"sym_total":0,"current_sym":"","active_workers":{},"sym_list":[]})
    olog("🔍 Получаем список монет...")
    syms = _fetch_all_symbols()
    if not syms:
        with screener_lock: screener_state["running"] = False
        olog("❌ Не удалось получить список монет"); return
    with screener_lock:
        screener_state["sym_total"] = len(syms)
        screener_state["sym_list"] = syms
    olog(f"✔ {len(syms)} монет, 50 циклов каждая, последовательно (как одиночный режим)")
    all_results = []

    for idx, sym in enumerate(syms, 1):
        if _screener_stop.is_set():
            break

        with screener_lock:
            screener_state["current_sym"] = sym
            screener_state["sym_index"]   = idx
            screener_state["active_workers"] = {sym: {"cycle": 0, "max_cycles": 50, "phase": "fetch"}}

        def _on_cycle(c, mx):
            with screener_lock:
                screener_state["active_workers"] = {sym: {"cycle": c, "max_cycles": mx, "phase": "opt"}}

        try:
            res = _run_one_sym_screener(sym, tf, days, sl_p, tp_p, risk, on_cycle=_on_cycle)
        except Exception:
            res = None

        olog(f"[{idx}/{len(syms)}] {sym} готово")
        if res:
            all_results.append(res)
            all_results.sort(key=lambda x: x["result"]["fitness"], reverse=True)
            with screener_lock:
                screener_state["results"] = all_results[:20]

    with screener_lock:
        screener_state["results"]       = all_results[:20]
        screener_state["active_workers"] = {}
        screener_state["running"]       = False
        screener_state["done"]          = True
    olog(f"✅ Скрининг завершён")
    if all_results:
        top3 = ", ".join(f"{r['sym']} WR={r['result']['winrate']}%" for r in all_results[:3])
        _send_alert(f"🔍 Скрининг завершён\nТоп-3: {top3}")

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
.global-status{display:flex;gap:8px;flex-wrap:wrap;padding:5px 12px;background:#0a0a0a;border-bottom:1px solid #1c1c1c}
.gs-pill{display:flex;align-items:center;gap:5px;padding:3px 9px;border-radius:11px;background:#161616;border:1px solid #262626;font-size:11px;color:#888;transition:color .2s,border-color .2s}
.gs-pill.on{color:#bdf5d8;border-color:#1a8f4a}
.gs-pill.warn{color:#ffe2a8;border-color:#8f5a1a}
.gs-dot{width:7px;height:7px;border-radius:50%;background:#3a3a3a;flex:none;transition:background .2s,box-shadow .2s}
.gs-dot.on{background:#0f9;box-shadow:0 0 5px #0f9}
.gs-dot.warn{background:#f0b800;box-shadow:0 0 5px #f0b800}
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
.top20-row{display:grid;grid-template-columns:24px 1fr 1fr 1fr 1fr 1fr 1fr;gap:4px;padding:3px 0;border-bottom:1px solid #1a1a1a;font-size:11px;align-items:center}
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
/* ── Эквалайзер fitness ── */
.eq-bar{display:flex;justify-content:space-between;gap:2px;padding:4px 0 2px}
.eq-ch{display:flex;flex-direction:column;align-items:center;gap:4px;flex:1;min-width:0}
.eq-val{font-size:10px;color:#f0b800;font-weight:700;min-height:12px}
.eq-slot{position:relative;height:88px;width:100%;cursor:pointer;touch-action:none}
.eq-slider{position:absolute;top:50%;left:50%;width:80px;height:18px;
  transform:translate(-50%,-50%) rotate(-90deg);
  -webkit-appearance:none;appearance:none;background:transparent;margin:0;
  pointer-events:none}
.eq-slider::-webkit-slider-runnable-track{height:5px;background:#222;border-radius:3px}
.eq-slider::-webkit-slider-thumb{-webkit-appearance:none;width:16px;height:16px;border-radius:50%;
  background:#f0b800;border:2px solid #0d0d0d;margin-top:-5.5px;box-shadow:0 0 4px rgba(240,184,0,.5)}
.eq-slider::-moz-range-track{height:5px;background:#222;border-radius:3px}
.eq-slider::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:#f0b800;border:2px solid #0d0d0d}
.eq-lbl{font-size:9.5px;color:#888;text-align:center;line-height:1.2}
/* ── AMOLED screensaver ── */
#amoledContent{
  position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  text-align:center;font-family:'JetBrains Mono',monospace,sans-serif;
  color:rgba(255,255,255,.92);
  transition:opacity 1.1s ease,color 1.1s ease,top 1.1s ease,left 1.1s ease;
  user-select:none;pointer-events:none;white-space:nowrap;
  min-width:260px;
}
#amoledContent .as-time{font-size:4.2rem;font-weight:500;letter-spacing:.04em;line-height:1;color:#f0b800}
#amoledContent .as-date{font-size:1rem;margin-top:8px;opacity:.7;text-transform:capitalize}
#amoledContent .as-divider{width:40px;height:1px;background:currentColor;opacity:.3;margin:16px auto}
#amoledContent .as-row{display:flex;gap:22px;justify-content:center;flex-wrap:wrap}
#amoledContent .as-row b{font-size:1.5rem;font-weight:600;display:block;color:inherit;line-height:1.1}
#amoledContent .as-row span{font-size:.68rem;opacity:.55;display:block;margin-top:4px;letter-spacing:.1em;text-transform:uppercase}
#amoledContent .as-status{margin-top:14px;font-size:.78rem;opacity:.6;letter-spacing:.05em}
#amoledContent.night{color:rgba(255,255,255,.10)}
#amoledContent.night .as-time{color:inherit;font-weight:400}
@media (max-width:480px){
  #amoledContent .as-time{font-size:3rem}
  #amoledContent .as-row{gap:16px}
  #amoledContent .as-row b{font-size:1.2rem}
}
</style></head><body>

<div id="amoledOverlay" style="display:none;position:fixed;inset:0;background:#000;z-index:99999;">
  <div id="amoledContent"></div>
  <button id="amoledExitBtn" onclick="event.stopPropagation();toggleAmoled();" ontouchstart="event.stopPropagation();" ontouchend="event.stopPropagation();toggleAmoled();" title="Выйти из AMOLED" style="position:fixed;bottom:36px;right:32px;z-index:100000;background:rgba(255,255,255,0.06);border:1.5px solid rgba(255,255,255,0.13);border-radius:50%;width:54px;height:54px;display:flex;align-items:center;justify-content:center;cursor:pointer;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);touch-action:manipulation;transition:background .2s,transform .1s,top .9s ease,left .9s ease;-webkit-tap-highlight-color:transparent;" onpointerdown="this.style.transform='scale(.9)';this.style.background='rgba(255,255,255,0.14)'" onpointerup="this.style.transform='';this.style.background='rgba(255,255,255,0.06)'" onpointerleave="this.style.transform='';this.style.background='rgba(255,255,255,0.06)'">
    <svg width="30" height="30" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="opacity:.75;display:block">
      <path d="M12 4a5 5 0 0 1 5 5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M7 9a5 5 0 0 1 10 0" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M4.5 9a7.5 7.5 0 0 1 15 0c0 4-1 7.5-3 10" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M12 9c0 3.5-.8 6.5-2.5 9" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M12 9a3 3 0 0 1 3 3c0 2.5-.6 5-1.8 7" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M9 10.5a3 3 0 0 1 .5-1.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M6.5 12.5c0 3 .7 5.5 2 7.5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>
    </svg>
  </button>
</div>

<div class="topbar">
  <h1>&#9889; SMC Optimizer</h1>
  <span class="ver" id="verBadge">v__VER__</span>
  <button class="btn btn-go" id="btnStart" onclick="startOpt()">&#9654; Старт</button>
  <button class="btn btn-stop" id="btnStop" onclick="stopOpt()" style="display:none">&#9632; Стоп</button>
  <span id="statusBadge" style="color:#555;font-size:11px">готов</span>
  <button class="btn-sm" id="amoledBtn" onclick="toggleAmoled()" title="AMOLED режим — гасит экран через 15с неактивности, защита от выгорания пикселей">&#11044; AMOLED</button>
</div>
<div class="global-status" id="globalStatus" title="Текущий статус трёх независимых процессов: перебор параметров, монитор графика (алерты) и авто-торговля. Кнопка «Стоп» у перебора останавливает только его — монитор и авто-торговля управляются отдельно.">
  <span class="gs-pill" id="gsOpt"><span class="gs-dot" id="gsOptDot"></span><span id="gsOptTxt">Перебор: ...</span></span>
  <span class="gs-pill" id="gsMon"><span class="gs-dot" id="gsMonDot"></span><span id="gsMonTxt">Монитор: ...</span></span>
  <span class="gs-pill" id="gsTrade"><span class="gs-dot" id="gsTradeDot"></span><span id="gsTradeTxt">Авто-трейд: ...</span></span>
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
    <label>Символ</label>
    <div style="display:flex;gap:6px;align-items:center">
      <input id="sym" value="DOGE_USDT" style="flex:1">
      <label style="display:flex;align-items:center;gap:4px;color:#aaa;font-size:11px;white-space:nowrap;cursor:pointer">
        <input type="checkbox" id="scanAll" onchange="toggleScanAll(this)"> Все монеты
      </label>
    </div>
    <label>Таймфрейм</label>
    <select id="tf">
      <option>1m</option><option>5m</option><option selected>15m</option>
      <option>30m</option><option>1h</option><option>4h</option><option>1d</option>
    </select>
    <label>Дней истории</label><input id="days" type="number" value="30" min="7" max="365">
    <label>SL %</label><input id="sl_pct" type="number" value="0.6" step="0.05">
    <label>TP %</label><input id="tp_pct" type="number" value="1.2" step="0.05">
    <label>Риск на сделку %</label><input id="risk_pct" type="number" value="10" step="1">
  </div>
  <div class="card">
    <h3>🎛 Эквалайзер fitness <span style="color:#555;font-size:10px;font-weight:400">(на ходу)</span></h3>
    <div class="eq-bar" id="eqBar">
      <div class="eq-ch"><div class="eq-val" id="eqVal_wr">1.00</div>
        <div class="eq-slot" onmousedown="eqAdjust(event,'wr')" ontouchstart="eqAdjust(event,'wr')"><input type="range" class="eq-slider" id="eq_wr" min="0" max="3" step="0.05" value="1"></div>
        <div class="eq-lbl">WR</div></div>
      <div class="eq-ch"><div class="eq-val" id="eqVal_pf">1.00</div>
        <div class="eq-slot" onmousedown="eqAdjust(event,'pf')" ontouchstart="eqAdjust(event,'pf')"><input type="range" class="eq-slider" id="eq_pf" min="0" max="3" step="0.05" value="1"></div>
        <div class="eq-lbl">PF</div></div>
      <div class="eq-ch"><div class="eq-val" id="eqVal_trades">1.00</div>
        <div class="eq-slot" onmousedown="eqAdjust(event,'trades')" ontouchstart="eqAdjust(event,'trades')"><input type="range" class="eq-slider" id="eq_trades" min="0" max="3" step="0.05" value="1"></div>
        <div class="eq-lbl">Кол-во</div></div>
      <div class="eq-ch"><div class="eq-val" id="eqVal_rr">1.00</div>
        <div class="eq-slot" onmousedown="eqAdjust(event,'rr')" ontouchstart="eqAdjust(event,'rr')"><input type="range" class="eq-slider" id="eq_rr" min="0" max="3" step="0.05" value="1"></div>
        <div class="eq-lbl">RR</div></div>
      <div class="eq-ch"><div class="eq-val" id="eqVal_dd">1.00</div>
        <div class="eq-slot" onmousedown="eqAdjust(event,'dd')" ontouchstart="eqAdjust(event,'dd')"><input type="range" class="eq-slider" id="eq_dd" min="0" max="3" step="0.05" value="1"></div>
        <div class="eq-lbl">Просадка</div></div>
    </div>
    <button class="btn btn-sm" style="width:100%;margin-top:4px" onclick="resetEq()">↺ Сброс к 1.0</button>
    <div style="display:flex;gap:6px;margin-top:6px">
      <button class="btn btn-go" id="btnWtStart" style="flex:1;font-size:11px" onclick="wtStart()">🎯 Автотюнинг</button>
      <button class="btn btn-stop" id="btnWtStop" style="flex:1;font-size:11px;display:none" onclick="wtStop()">⏹ Стоп</button>
    </div>
    <div id="wtStatus" style="font-size:10px;color:#888;margin-top:4px;min-height:14px"></div>
    <div id="wtLog" style="font-size:9.5px;color:#aaa;max-height:90px;overflow-y:auto;margin-top:3px;display:none"></div>
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
        <span>T</span><span>$100→$</span><span>SL/TP/swing</span>
      </div>
    </div>
  </div>
  <div class="card" id="screenerCard" style="display:none">
    <h3>🔍 Скрининг всех монет</h3>
    <div id="screenerStatus" style="color:#555;font-size:11px;margin-bottom:8px;white-space:pre;line-height:1.6">—</div>
    <div class="prog-bar"><div class="prog-fill" id="screenerProg" style="width:0%"></div></div>
    <div id="screenerSymList" style="margin-top:6px;font-size:10px;color:#888;line-height:1.8;word-break:break-all"></div>
    <div id="screenerTable" style="margin-top:8px"></div>
  </div>
</div>
</div>
</div>
<div id="chartPanel" class="tab-panel">
  <div class="chart-bar">
    <label>Символ<input id="cSym" value="DOGE_USDT"></label>
    <label>ТФ<select id="cTf">
      <option value="1m">1m</option><option value="5m">5m</option><option value="15m" selected>15m</option>
      <option value="30m">30m</option><option value="1h">1h</option><option value="4h">4h</option><option value="1d">1d</option>
    </select></label>
    <label>Дней<input id="cDays" type="number" value="7" min="1" max="60" style="width:60px"></label>
    <label>Swing<input id="cSwing" type="number" value="10" min="3" max="50" style="width:60px"></label>
    <label>SL%<input id="cSl" type="number" value="0.8" step="0.1" style="width:60px"></label>
    <label>TP%<input id="cTp" type="number" value="1.6" step="0.1" style="width:60px"></label>
    <button class="btn btn-go" onclick="loadChart()" style="align-self:flex-end">Загрузить</button>
    <button class="btn" id="monBtn" onclick="toggleChartMonitor()" style="align-self:flex-end">🔔 Алерты</button>
    <button class="btn" id="atBtn" onclick="toggleAutoTrade()" style="align-self:flex-end;background:#1a3a5c">🤖 Авто</button>
  </div>
  <!-- Панель авто-торговли (скрыта по умолчанию) -->
  <div id="atPanel" style="display:none;background:#0d1a2a;border:1px solid #1a3a5c;border-radius:6px;padding:10px;margin-bottom:8px;font-size:12px">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
      <b style="color:#3a9eff">🤖 Авто-торговля Gate.io</b>
      <span id="atStatusBadge" style="color:#555;font-size:11px">выкл</span>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px">
      <label style="color:#888;font-size:11px">API Key
        <input id="atKey" type="password" placeholder="Gate.io API Key" style="width:100%;background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:4px 6px;border-radius:4px;font-size:11px">
      </label>
      <label style="color:#888;font-size:11px">API Secret
        <input id="atSecret" type="password" placeholder="Gate.io Secret" style="width:100%;background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:4px 6px;border-radius:4px;font-size:11px">
      </label>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px">
      <label style="color:#888;font-size:11px">Вход % депозита
        <input id="atPosPct" type="number" value="95" min="1" max="100" step="1" style="width:100%;background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:4px 6px;border-radius:4px;font-size:11px">
      </label>
      <label style="color:#888;font-size:11px">Риск % (плечо=риск÷SL)
        <input id="atRisk" type="number" value="10" min="0.5" max="20" step="0.5" style="width:100%;background:#0d0d0d;border:1px solid #333;color:#e0e0e0;padding:4px 6px;border-radius:4px;font-size:11px">
      </label>
    </div>
    <label style="display:flex;align-items:center;gap:6px;color:#888;font-size:11px;margin-bottom:6px;cursor:pointer">
      <input id="atAutoSync" type="checkbox" onchange="toggleAutoSync()">
      🔁 Автоматически подхватывать новый лучший конфиг от оптимизатора (того же символа/ТФ) — TP/SL уже открытой сделки не трогает, влияет только на поиск следующего сигнала
    </label>
    <div style="display:flex;gap:6px;margin-bottom:6px">
      <button class="btn btn-sm" style="flex:1" onclick="saveGateCfg()">💾 Сохранить ключи</button>
      <button class="btn btn-sm" id="atStartBtn" style="flex:1;background:#1a5c2a;color:#0f9" onclick="startAutoTrade()">▶ Запустить</button>
      <button class="btn btn-sm" id="atStopBtn" style="flex:1;background:#3a0a0a;color:#f45;display:none" onclick="stopAutoTrade()">⏹ Стоп</button>
    </div>
    <button class="btn btn-sm" style="width:100%;background:#3a1a0a;color:#f0b800;margin-bottom:4px" onclick="closePosition()">📤 Закрыть позицию вручную</button>
    <div id="atInfo" style="font-size:11px;color:#555;line-height:1.6">—</div>
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
var _autoAppliedAt30 = false;
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
  if(!_bestParams){ alert('Нет лучшего конфига — запустите оптимизатор'); return; }
  var p = _bestParams;
  // Сначала выставляем все значения, потом переключаем вкладку и грузим
  document.getElementById('cSym').value   = document.getElementById('sym').value;
  // TF: принудительно перебираем опции чтобы гарантированно выбрать нужную
  var tfSel = document.getElementById('cTf');
  var tfVal = document.getElementById('tf').value;
  for(var i=0; i<tfSel.options.length; i++){
    if(tfSel.options[i].value === tfVal){ tfSel.selectedIndex = i; break; }
  }
  document.getElementById('cDays').value  = document.getElementById('days').value;
  document.getElementById('cSwing').value = p.swing_len  != null ? p.swing_len  : 10;
  document.getElementById('cSl').value    = p.sl_pct     != null ? p.sl_pct     : 0.8;
  document.getElementById('cTp').value    = p.tp_pct     != null ? p.tp_pct     : 1.6;
  _chartExtra = {
    internal_len:       p.internal_len       != null ? p.internal_len       : 5,
    ob_filter:          p.ob_filter          != null ? p.ob_filter          : 'atr',
    ob_mitigation:      p.ob_mitigation      != null ? p.ob_mitigation      : 'highlow',
    fvg_enabled:        p.fvg_enabled        != null ? p.fvg_enabled        : true,
    fvg_threshold:      p.fvg_threshold      != null ? p.fvg_threshold      : 0.1,
    choch_only:         p.choch_only         != null ? p.choch_only         : false,
    use_internal:       p.use_internal       != null ? p.use_internal       : true,
    min_ob_size:        p.min_ob_size        != null ? p.min_ob_size        : 1.0,
    require_fvg_confirm:p.require_fvg_confirm!= null ? p.require_fvg_confirm: false,
  };
  // Переключаем вкладку надёжно — ищем кнопку по тексту
  var tabBtns = document.querySelectorAll('.tab');
  var chartBtn = null;
  for(var i=0;i<tabBtns.length;i++){ if(tabBtns[i].textContent.trim()==='График'){ chartBtn=tabBtns[i]; break; } }
  if(chartBtn) switchTab('chart', chartBtn);
  // setTimeout чтобы canvas успел стать видимым перед drawChart
  setTimeout(function(){ loadChart(); }, 80);
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

// ─── Авто-торговля JS ──────────────────────────────────────────────────────
var _atActive = false;
var _atPollTimer = null;

function toggleAutoTrade(){
  var panel = document.getElementById('atPanel');
  panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  if(panel.style.display === 'block') loadGateCfg();
}

function loadGateCfg(){
  fetch('/gate_cfg').then(function(r){return r.json();}).then(function(d){
    if(d.has_key){
      document.getElementById('atKey').placeholder = d.gate_key + ' (сохранён)';
      document.getElementById('atSecret').placeholder = '*** (сохранён)';
    }
  }).catch(function(){});
}

function saveGateCfg(){
  var key = document.getElementById('atKey').value.trim();
  var sec = document.getElementById('atSecret').value.trim();
  if(!key || !sec){ atInfo('Введите ключ и секрет','#f45'); return; }
  fetch('/gate_cfg',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({gate_key:key,gate_secret:sec})})
    .then(function(r){return r.json();})
    .then(function(d){ if(d.ok) atInfo('✅ Ключи сохранены','#0f9'); })
    .catch(function(e){ atInfo('Ошибка: '+e,'#f45'); });
}

function startAutoTrade(){
  var sym  = document.getElementById('cSym').value.trim()||'BTC_USDT';
  var tf   = document.getElementById('cTf').value;
  var days = parseInt(document.getElementById('cDays').value)||30;
  var risk = parseFloat(document.getElementById('atRisk').value)||10.0;
  var params = Object.assign({}, _chartExtra, {
    swing_len: parseFloat(document.getElementById('cSwing').value),
    sl_pct:    parseFloat(document.getElementById('cSl').value),
    tp_pct:    parseFloat(document.getElementById('cTp').value)
  });
  fetch('/auto_trade_start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sym:sym,tf:tf,days:days,risk_pct:risk,
      position_pct:parseFloat(document.getElementById('atPosPct').value)||95,
      params:params,
      auto_sync:document.getElementById('atAutoSync').checked})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        _atActive=true;
        document.getElementById('atStartBtn').style.display='none';
        document.getElementById('atStopBtn').style.display='';
        document.getElementById('atStatusBadge').textContent='🟢 активен · '+sym+' '+tf;
        document.getElementById('atStatusBadge').style.color='#0f9';
        document.getElementById('atBtn').style.background='#1a5c2a';
        atInfo('Авто-трейд запущен. Ждём нового сигнала...','#0f9');
        scheduleAtPoll();
      } else {
        atInfo('❌ '+d.msg,'#f45');
      }
    }).catch(function(e){ atInfo('Ошибка: '+e,'#f45'); });
}

function toggleAutoSync(){
  var on = document.getElementById('atAutoSync').checked;
  fetch('/auto_trade_sync',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({auto_sync:on})})
    .then(function(r){return r.json();})
    .then(function(d){
      if(d.ok) atInfo(on?'🔁 Авто-синк с оптимизатором включён':'Авто-синк выключен', on?'#0f9':'#888');
    }).catch(function(e){ atInfo('Ошибка: '+e,'#f45'); });
}

function stopAutoTrade(){
  fetch('/auto_trade_stop',{method:'POST'}).then(function(){
    _atActive=false;
    clearTimeout(_atPollTimer);
    document.getElementById('atStartBtn').style.display='';
    document.getElementById('atStopBtn').style.display='none';
    document.getElementById('atStatusBadge').textContent='выкл';
    document.getElementById('atStatusBadge').style.color='#555';
    document.getElementById('atBtn').style.background='#1a3a5c';
    atInfo('Авто-трейд остановлен.','#f0b800');
  }).catch(function(e){ atInfo('Ошибка: '+e,'#f45'); });
}

function closePosition(){
  if(!confirm('Закрыть текущую позицию рыночным ордером?')) return;
  fetch('/auto_trade_close',{method:'POST'}).then(function(r){return r.json();})
    .then(function(d){
      atInfo(d.ok?'✅ Позиция закрыта':'❌ '+d.msg, d.ok?'#0f9':'#f45');
    }).catch(function(e){ atInfo('Ошибка: '+e,'#f45'); });
}

function scheduleAtPoll(){
  if(!_atActive) return;
  _atPollTimer = setTimeout(pollAtStatus, 5000);
}

function pollAtStatus(){
  fetch('/auto_trade_status').then(function(r){return r.json();}).then(function(d){
    if(!d.enabled){ _atActive=false; return; }
    document.getElementById('atAutoSync').checked = !!d.auto_sync;
    var pos = d.position;
    var info = '';
    var p = d.params || {};
    if(p.swing_len!=null){
      info += '<span style="color:#888">Параметры бота сейчас: swing='
        +p.swing_len+' SL='+p.sl_pct+'% TP='+p.tp_pct+'%'
        +(d.auto_sync?' (🔁 авто-синк вкл)':' (зафиксированы при запуске)')+'</span><br>';
      var curSw = parseFloat(document.getElementById('cSwing').value);
      var curSl = parseFloat(document.getElementById('cSl').value);
      var curTp = parseFloat(document.getElementById('cTp').value);
      if(!d.auto_sync && (curSw!==p.swing_len || curSl!==p.sl_pct || curTp!==p.tp_pct)){
        info += '<span style="color:#f0b800">⚠ На графике сейчас другие параметры (swing='
          +curSw+' SL='+curSl+'% TP='+curTp+'%) — бот их не видит и не использует, '
          +'пока вы не перезапустите авто-трейд или не включите авто-синк</span><br>';
      }
    }
    if(pos){
      var dirEmoji = pos.dir==='long'?'🟢':'🔴';
      info += dirEmoji+' <b>Позиция: '+pos.dir.toUpperCase()+'</b><br>';
      info += 'Entry: '+pos.entry.toFixed(4)+' | SL: '+pos.sl.toFixed(4)+' | TP: '+pos.tp.toFixed(4)+'<br>';
      info += 'Size: '+pos.size+' контр<br>';
    } else {
      info += '⏳ Позиций нет, ждём сигнала...<br>';
    }
    if(d.last_error) info += '<span style="color:#f45">⚠ '+d.last_error+'</span><br>';
    if(d.last_check){
      var ago = Math.round((Date.now()/1000 - d.last_check));
      info += '<span style="color:#555">Проверка: '+ago+'с назад</span>';
    }
    document.getElementById('atInfo').innerHTML = info || '—';
    scheduleAtPoll();
  }).catch(function(){ scheduleAtPoll(); });
}

function atInfo(msg, color){
  var el = document.getElementById('atInfo');
  el.innerHTML = msg;
  el.style.color = color||'#e0e0e0';
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

var EQ_KEYS = ['wr','pf','trades','rr','dd'];
var _eqDebounce = null;
function eqAdjust(e, k){
  e.preventDefault();
  var slot = e.currentTarget;
  var rect = slot.getBoundingClientRect();
  var clientY = (e.touches && e.touches.length) ? e.touches[0].clientY : e.clientY;
  var clickY = clientY - rect.top;
  var input = document.getElementById('eq_'+k);
  var min = parseFloat(input.min), max = parseFloat(input.max), step = parseFloat(input.step);
  var val = parseFloat(input.value);
  var frac = (val - min) / (max - min);
  var thumbY = (1 - frac) * rect.height;   // визуально верх слота = max, низ = min
  var dir = (clickY < thumbY) ? 1 : -1;     // клик выше ползунка — +шаг, ниже — -шаг
  var newVal = val + dir * step;
  newVal = Math.max(min, Math.min(max, newVal));
  newVal = Math.round(newVal / step) * step;
  newVal = Math.round(newVal * 1000) / 1000;
  input.value = newVal;
  document.getElementById('eqVal_'+k).textContent = newVal.toFixed(2);
  clearTimeout(_eqDebounce);
  _eqDebounce = setTimeout(saveEqWeights, 250);
}
function saveEqWeights(){
  var body = {};
  EQ_KEYS.forEach(function(k){ body[k] = parseFloat(document.getElementById('eq_'+k).value); });
  fetch('/fitness_weights', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}).catch(function(){});
}
function resetEq(){
  EQ_KEYS.forEach(function(k){
    document.getElementById('eq_'+k).value = 1;
    document.getElementById('eqVal_'+k).textContent = '1.00';
  });
  saveEqWeights();
}
function loadEqWeights(){
  fetch('/fitness_weights').then(function(r){return r.json();}).then(function(d){
    EQ_KEYS.forEach(function(k){
      var v = (d[k] != null) ? d[k] : 1.0;
      document.getElementById('eq_'+k).value = v;
      document.getElementById('eqVal_'+k).textContent = parseFloat(v).toFixed(2);
    });
  }).catch(function(){});
}
loadEqWeights();

/* ── Автотюнинг весов ── */
var _wtPollTimer = null;
var _wtLogLen = 0;
function wtStart(){
  fetch('/weight_tune_start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({n_windows:4,bh_cycles:20,passes:2})}).then(function(r){return r.json();}).then(function(d){
    if(!d.ok){alert('Ошибка: '+(d.error||'?')); return;}
    document.getElementById('btnWtStart').style.display='none';
    document.getElementById('btnWtStop').style.display='';
    document.getElementById('wtLog').style.display='';
    _wtLogLen=0;
    if(_wtPollTimer) clearInterval(_wtPollTimer);
    _wtPollTimer=setInterval(wtPoll,2000);
  }).catch(function(){});
}
function wtStop(){
  fetch('/weight_tune_stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(function(){});
}
function wtPoll(){
  fetch('/weight_tune_status').then(function(r){return r.json();}).then(function(d){
    var status=document.getElementById('wtStatus');
    var logEl=document.getElementById('wtLog');
    if(d.running){
      status.textContent='⏳ '+( d.stage||'...');
      status.style.color='#f0b800';
    } else if(d.stage==='done'){
      status.textContent='✅ Готово — веса применены';
      status.style.color='#4caf50';
      document.getElementById('btnWtStart').style.display='';
      document.getElementById('btnWtStop').style.display='none';
      if(_wtPollTimer){clearInterval(_wtPollTimer);_wtPollTimer=null;}
      loadEqWeights(); // обновить слайдеры
    } else if(d.stage==='остановлено'){
      status.textContent='⏹ Остановлено';
      status.style.color='#888';
      document.getElementById('btnWtStart').style.display='';
      document.getElementById('btnWtStop').style.display='none';
      if(_wtPollTimer){clearInterval(_wtPollTimer);_wtPollTimer=null;}
    } else if(!d.running && _wtLogLen>0){
      document.getElementById('btnWtStart').style.display='';
      document.getElementById('btnWtStop').style.display='none';
      if(_wtPollTimer){clearInterval(_wtPollTimer);_wtPollTimer=null;}
    }
    if(d.logs && d.logs.length>_wtLogLen){
      var newLines=d.logs.slice(_wtLogLen);
      _wtLogLen=d.logs.length;
      newLines.forEach(function(l){
        var div=document.createElement('div');
        div.textContent=l.ts+' '+l.msg;
        logEl.appendChild(div);
      });
      logEl.scrollTop=logEl.scrollHeight;
    }
  }).catch(function(){});
}

/* ── Единый индикатор статуса трёх независимых процессов в шапке ──
   Перебор/Монитор/Авто-торговля управляются раздельно (3 разных кнопки
   Старт/Стоп), но статус виден всегда, на любой вкладке. */
function _gsSet(pillId, dotId, txtId, state, text){
  // state: 'off' | 'on' | 'warn'
  var pill=document.getElementById(pillId), dot=document.getElementById(dotId), txt=document.getElementById(txtId);
  pill.classList.remove('on','warn'); dot.classList.remove('on','warn');
  if(state!=='off'){ pill.classList.add(state); dot.classList.add(state); }
  txt.textContent = text;
}
function pollGlobalStatus(){
  fetch('/opt_status').then(function(r){return r.json();}).then(function(d){
    if(d.running){
      if(d.eco_mode){
        _gsSet('gsOpt','gsOptDot','gsOptTxt','warn','Перебор: цикл '+(d.cycle||0)+' · 🌡 эко');
      } else {
        _gsSet('gsOpt','gsOptDot','gsOptTxt','on','Перебор: цикл '+(d.cycle||0));
      }
    } else {
      _gsSet('gsOpt','gsOptDot','gsOptTxt','off','Перебор: выкл');
    }
  }).catch(function(){});
  fetch('/chart_monitor_status').then(function(r){return r.json();}).then(function(d){
    if(d.active){
      _gsSet('gsMon','gsMonDot','gsMonTxt','on','Монитор: '+(d.symbol||'')+' '+(d.tf||''));
    } else {
      _gsSet('gsMon','gsMonDot','gsMonTxt','off','Монитор: выкл');
    }
  }).catch(function(){});
  fetch('/auto_trade_status').then(function(r){return r.json();}).then(function(d){
    if(d.enabled){
      if(d.position){
        _gsSet('gsTrade','gsTradeDot','gsTradeTxt','warn','Авто-трейд: '+(d.symbol||'')+' '+(d.tf||'')+' · позиция открыта');
      } else {
        _gsSet('gsTrade','gsTradeDot','gsTradeTxt','on','Авто-трейд: '+(d.symbol||'')+' '+(d.tf||''));
      }
    } else {
      _gsSet('gsTrade','gsTradeDot','gsTradeTxt','off','Авто-трейд: выкл');
    }
  }).catch(function(){});
}
pollGlobalStatus();
setInterval(pollGlobalStatus, 2000);

/* ── Optimizer polling ── */
var polling=null, lastLogTotal=0, logsDropped=0;

var _startingDots = null;
function startOpt(){
  var body={
    symbol:document.getElementById('sym').value,
    tf:document.getElementById('tf').value,
    days:parseInt(document.getElementById('days').value),
    sl_pct:parseFloat(document.getElementById('sl_pct').value),
    tp_pct:parseFloat(document.getElementById('tp_pct').value),
    risk_pct:parseFloat(document.getElementById('risk_pct').value),
  };
  // Сразу показываем что идёт загрузка — не ждём ответа сервера
  _autoAppliedAt30 = false;
  document.getElementById('btnStart').style.display='none';
  document.getElementById('btnStop').style.display='';
  var badge = document.getElementById('statusBadge');
  badge.style.color='#f0b800';
  var dots=0, phases=['⏳ загрузка свечей.','⏳ загрузка свечей..','⏳ загрузка свечей...'];
  if(_startingDots) clearInterval(_startingDots);
  _startingDots = setInterval(function(){
    badge.textContent = phases[dots%3]; dots++;
  }, 400);
  // Добавляем строку в лог сразу
  var lb=document.getElementById('logBox');
  var div=document.createElement('div'); div.className='log-line';
  div.innerHTML='<span style="color:#555">[--:--:--]</span> ▶ Запускаем оптимизатор: '
    +body.symbol+' '+body.tf+' '+body.days+'д SL='+body.sl_pct+'% TP='+body.tp_pct+'%';
  lb.appendChild(div); lb.scrollTop=lb.scrollHeight;

  fetch('/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(){
      clearInterval(_startingDots); _startingDots=null;
      badge.textContent='работает...'; badge.style.color='#0f9';
      scheduleNext();
    })
    .catch(function(e){
      clearInterval(_startingDots); _startingDots=null;
      badge.textContent='ошибка запуска'; badge.style.color='#f45';
      document.getElementById('btnStart').style.display='';
      document.getElementById('btnStop').style.display='none';
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
      var badge=document.getElementById('statusBadge');
      badge.textContent='завершено'; badge.style.color='#aaa';
    } else {
      var badge=document.getElementById('statusBadge');
      var cyc=d.cycle||0, tri=(d.trials||0).toLocaleString();
      badge.textContent = cyc>0 ? ('цикл '+cyc+' · '+tri+' попыток') : '⏳ инициализация...';
      badge.style.color = cyc>0?'#0f9':'#f0b800';
      scheduleNext();
    }

    if(d.best){
      var r=d.best.result, p=d.best.params;
      var prevFit = _bestParams ? (_bestParams._fitness||0) : 0;
      p._fitness = r.fitness;
      _bestParams = p;
      window._lastBestResult = r;
      // Авто-применение: каждый раз когда fitness улучшился И цикл >= 30
      if((d.cycle||0) >= 30 && r.fitness > prevFit){
        applyBestToChart();
      }
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
      var html='<div class="top20-row"><span>#</span><span>WR%</span><span>PF</span><span>DD%</span><span>T</span><span>$100→$</span><span>SL/TP/swing</span></div>';
      top.forEach(function(e,i){
        var r=e.result,p=e.params;
        var wrC=r.winrate>=55?'green':r.winrate>=45?'yellow':'red';
        var retC=r.total_return>=0?'green':'red';
        var finalBal=Math.round(100*(1+r.total_return/100));
        html+='<div class="top20-row">'+
          '<span style="color:#555">'+(i+1)+'</span>'+
          '<span class="'+wrC+'">'+r.winrate+'%</span>'+
          '<span>'+r.profit_factor+'</span>'+
          '<span class="red">'+r.max_dd+'%</span>'+
          '<span>'+r.trades+'</span>'+
          '<span class="'+retC+'">$'+finalBal+'</span>'+
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
        _camStart=Math.max(0,_cd.length-80);
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
    }).catch(function(e){
      cStatus('Ошибка загрузки: '+e);
      // Даже при ошибке перезапускаем таймер — иначе цепочка обрывается
      var tf=document.getElementById('cTf').value;
      scheduleAutoRefresh(tf);
    });
}

var _countdownTimer = null;
var _lastAutoLoad = 0;
function scheduleAutoRefresh(tf){
  if(_chartAutoTimer) clearInterval(_chartAutoTimer);
  if(_countdownTimer) clearInterval(_countdownTimer);
  var sec = TF_SEC[tf] || 900;
  _lastAutoLoad = Date.now();
  // Используем setInterval вместо setTimeout — Android не замораживает его так агрессивно,
  // и цепочка не обрывается при зависшем fetch
  _chartAutoTimer = setInterval(function(){
    var now = Date.now()/1000;
    var rem = sec - (now % sec);
    // Срабатываем в течение 5с после закрытия бара
    if(rem > sec - 5 || rem <= 2){
      clearInterval(_chartAutoTimer);
      _chartAutoTimer = null;
      loadChart(true);
    }
  }, 1000);
  // Обратный отсчёт
  _countdownTimer = setInterval(function(){
    var rem = Math.round(sec - (Date.now()/1000 % sec));
    cStatus(_cd.length+' свечей, '+_sig.length+' сигналов (авто через '+rem+'с)');
  }, 1000);
}

function drawChart(){
  if(!_cd.length)return;
  var dpr=window.devicePixelRatio||1;
  var W=cv.parentElement.clientWidth-20;
  if(W<=0)return;
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
    var exitI=sg.exit_i!==undefined?sg.exit_i:(_cd.length-1);
    if(sg.entry_i<=e&&exitI>=s){
      if(sg.tp<mn)mn=sg.tp;if(sg.tp>mx)mx=sg.tp;
      if(sg.sl<mn)mn=sg.sl;if(sg.sl>mx)mx=sg.sl;
    }
  });
  var rng=mx-mn||1, pad2=rng*0.06;
  mn-=pad2;mx+=pad2;
  function toY(p){return PAD.t+cH*(1-(p-mn)/(mx-mn));}
  function toX(i){return PAD.l+(i-s+0.5)*barW;}
  // ── Фон ─────────────────────────────────────────────────────────────────
  ctx2.fillStyle='#0d0d0d';ctx2.fillRect(0,0,W,H);
  // Сетка — только горизонтальные линии, очень тонкие
  ctx2.strokeStyle='rgba(255,255,255,0.04)';ctx2.lineWidth=0.5;
  function fmt(v){return v>1000?v.toFixed(1):v>10?v.toFixed(2):v.toFixed(4);}
  for(var g=0;g<=4;g++){
    var p=mn+(mx-mn)*g/4,y=toY(p);
    ctx2.beginPath();ctx2.moveTo(PAD.l,y);ctx2.lineTo(W-PAD.r,y);ctx2.stroke();
    ctx2.fillStyle='rgba(120,120,120,0.6)';ctx2.font='9px monospace';ctx2.textAlign='right';
    ctx2.fillText(fmt(p),PAD.l-4,y+3);
  }
  // ── FVG — очень прозрачно, только штрих по левому краю ──────────────────
  _fvg_bull.filter(function(f){return f.end_i>=s&&f.i<=e;}).forEach(function(f){
    var x1=toX(Math.max(f.i,s))-barW/2, x2=toX(Math.min(f.end_i,e))+barW/2;
    var y1=toY(f.hi),y2=toY(f.lo);
    ctx2.fillStyle='rgba(8,153,129,0.06)';ctx2.fillRect(x1,y1,x2-x1,y2-y1);
    ctx2.fillStyle='rgba(8,153,129,0.5)';ctx2.fillRect(x1,y1,2,y2-y1);
  });
  _fvg_bear.filter(function(f){return f.end_i>=s&&f.i<=e;}).forEach(function(f){
    var x1=toX(Math.max(f.i,s))-barW/2, x2=toX(Math.min(f.end_i,e))+barW/2;
    var y1=toY(f.hi),y2=toY(f.lo);
    ctx2.fillStyle='rgba(242,54,69,0.06)';ctx2.fillRect(x1,y1,x2-x1,y2-y1);
    ctx2.fillStyle='rgba(242,54,69,0.5)';ctx2.fillRect(x1,y1,2,y2-y1);
  });
  // ── OB — тонкая рамка без заливки, метка только если широко ─────────────
  _obs_bull.filter(function(o){return o.end_i>=s&&o.i<=e;}).forEach(function(o){
    var x1=toX(Math.max(o.i,s))-barW/2, x2=toX(Math.min(o.end_i,e))+barW/2;
    var y1=toY(o.hi),y2=toY(o.lo);
    ctx2.fillStyle='rgba(49,121,245,0.07)';ctx2.fillRect(x1,y1,x2-x1,y2-y1);
    ctx2.strokeStyle='rgba(49,121,245,0.35)';ctx2.lineWidth=0.8;ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
    if(x2-x1>30){ctx2.fillStyle='rgba(49,121,245,0.45)';ctx2.font='8px monospace';ctx2.textAlign='left';ctx2.fillText('OB',x1+3,y1+8);}
  });
  _obs_bear.filter(function(o){return o.end_i>=s&&o.i<=e;}).forEach(function(o){
    var x1=toX(Math.max(o.i,s))-barW/2, x2=toX(Math.min(o.end_i,e))+barW/2;
    var y1=toY(o.hi),y2=toY(o.lo);
    ctx2.fillStyle='rgba(242,54,69,0.07)';ctx2.fillRect(x1,y1,x2-x1,y2-y1);
    ctx2.strokeStyle='rgba(242,54,69,0.35)';ctx2.lineWidth=0.8;ctx2.strokeRect(x1,y1,x2-x1,y2-y1);
    if(x2-x1>30){ctx2.fillStyle='rgba(242,54,69,0.45)';ctx2.font='8px monospace';ctx2.textAlign='left';ctx2.fillText('OB',x1+3,y1+8);}
  });
  // ── Свечи ────────────────────────────────────────────────────────────────
  vis.forEach(function(c,idx){
    var xi=s+idx,x=toX(xi),bull=c.c>=c.o;
    var clr=bull?'#26a69a':'#ef5350';
    ctx2.strokeStyle=clr;ctx2.lineWidth=1;
    ctx2.beginPath();ctx2.moveTo(x,toY(c.h));ctx2.lineTo(x,toY(c.l));ctx2.stroke();
    var y1=toY(Math.max(c.o,c.c)),y2=toY(Math.min(c.o,c.c));
    ctx2.fillStyle=bull?'rgba(38,166,154,0.85)':'rgba(239,83,80,0.85)';
    ctx2.fillRect(x-candleW/2,y1,candleW,Math.max(1,y2-y1));
  });
  // ── Сигналы: только последний виден полностью, остальные — точка + тонкие линии
  var visibleSigs = _sig.filter(function(sg){return sg.entry_i>=s&&sg.entry_i<=e;});
  visibleSigs.forEach(function(sg, si){
    var isLast = (si===visibleSigs.length-1);
    var xe=toX(sg.entry_i);
    var xe2=(sg.exit_i!==undefined&&sg.exit_i<=e)?toX(sg.exit_i):W-PAD.r;
    var ye=toY(sg.entry), yt=toY(sg.tp), ys=toY(sg.sl);
    var isLong=sg.dir==='long';
    var clrTP='#26a69a', clrSL='#ef5350';
    if(isLast){
      // Зоны — лёгкие
      ctx2.fillStyle='rgba(38,166,154,0.08)';
      ctx2.fillRect(xe,Math.min(yt,ye),Math.max(0,xe2-xe),Math.abs(yt-ye));
      ctx2.fillStyle='rgba(239,83,80,0.08)';
      ctx2.fillRect(xe,Math.min(ys,ye),Math.max(0,xe2-xe),Math.abs(ys-ye));
      // TP линия
      ctx2.strokeStyle=clrTP;ctx2.lineWidth=1;ctx2.setLineDash([6,4]);
      ctx2.beginPath();ctx2.moveTo(xe,yt);ctx2.lineTo(xe2,yt);ctx2.stroke();
      // SL линия
      ctx2.strokeStyle=clrSL;
      ctx2.beginPath();ctx2.moveTo(xe,ys);ctx2.lineTo(xe2,ys);ctx2.stroke();
      // Entry линия
      ctx2.strokeStyle='rgba(200,200,200,0.4)';ctx2.lineWidth=0.8;ctx2.setLineDash([3,5]);
      ctx2.beginPath();ctx2.moveTo(xe,ye);ctx2.lineTo(xe2,ye);ctx2.stroke();
      ctx2.setLineDash([]);
      // Метки — только у правого края
      ctx2.font='bold 9px monospace';
      ctx2.fillStyle=clrTP;ctx2.textAlign='right';ctx2.fillText('TP '+fmt(sg.tp),xe2-3,yt-3);
      ctx2.fillStyle=clrSL;ctx2.textAlign='right';ctx2.fillText('SL '+fmt(sg.sl),xe2-3,ys+10);
    } else {
      // Старые сигналы — только тонкие TP/SL линии без заливки
      ctx2.strokeStyle='rgba(38,166,154,0.25)';ctx2.lineWidth=0.8;ctx2.setLineDash([4,4]);
      ctx2.beginPath();ctx2.moveTo(xe,yt);ctx2.lineTo(xe2,yt);ctx2.stroke();
      ctx2.strokeStyle='rgba(239,83,80,0.25)';
      ctx2.beginPath();ctx2.moveTo(xe,ys);ctx2.lineTo(xe2,ys);ctx2.stroke();
      ctx2.setLineDash([]);
    }
    // Точка выхода + метка PnL
    if(sg.exit_i!==undefined&&sg.exit_i>=s&&sg.exit_i<=e){
      var exitY=toY(sg.win?sg.tp:sg.sl);
      var exitX=toX(sg.exit_i);
      ctx2.fillStyle=sg.win?clrTP:clrSL;
      ctx2.beginPath();ctx2.arc(exitX,exitY,3.5,0,Math.PI*2);ctx2.fill();
      if(sg.dep_pct!==undefined){
        var lbl=(sg.dep_pct>0?'+':'')+sg.dep_pct+'%';
        ctx2.font='bold 9px monospace';
        ctx2.fillStyle=sg.win?clrTP:clrSL;
        ctx2.textAlign= exitX > W*0.85 ? 'right' : 'left';
        var lx = exitX > W*0.85 ? exitX-6 : exitX+6;
        var ly = sg.win ? exitY-5 : exitY+12;
        ctx2.fillText(lbl,lx,ly);
      }
    }
  });
  // ── Стрелки входа — маленькие, только последние N ────────────────────────
  var maxArrows = 20;
  var arrowSigs = visibleSigs.slice(-maxArrows);
  arrowSigs.forEach(function(sg){
    var xe=toX(sg.entry_i), ye=toY(sg.entry);
    var isLong=sg.dir==='long';
    var sz=5; // маленький размер
    var offset=isLong?sz*2+2:-(sz*2+2);
    // Тень
    ctx2.fillStyle='rgba(0,0,0,0.5)';
    ctx2.beginPath();
    if(isLong){ctx2.moveTo(xe-sz,ye+offset+1);ctx2.lineTo(xe+sz,ye+offset+1);ctx2.lineTo(xe,ye+1);}
    else{ctx2.moveTo(xe-sz,ye+offset-1);ctx2.lineTo(xe+sz,ye+offset-1);ctx2.lineTo(xe,ye-1);}
    ctx2.fill();
    // Стрелка
    ctx2.fillStyle=isLong?'#26a69a':'#ef5350';
    ctx2.beginPath();
    if(isLong){ctx2.moveTo(xe-sz,ye+offset);ctx2.lineTo(xe+sz,ye+offset);ctx2.lineTo(xe,ye);}
    else{ctx2.moveTo(xe-sz,ye+offset);ctx2.lineTo(xe+sz,ye+offset);ctx2.lineTo(xe,ye);}
    ctx2.fill();
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
    {l:'Return',v:m.total_return+'%'},{l:'RR',v:m.rr||'—'},{l:'Fitness',v:m.fitness},
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
var _tc=null, _pinchDist=null, _pinchVis=null, _pinchCenter=null;
function _touches2dist(e){ var dx=e.touches[0].clientX-e.touches[1].clientX, dy=e.touches[0].clientY-e.touches[1].clientY; return Math.sqrt(dx*dx+dy*dy); }
cv.addEventListener('touchstart',function(e){
  if(e.touches.length===2){
    _pinchDist=_touches2dist(e);
    _pinchVis=_camEnd-_camStart;
    _pinchCenter=(_camStart+_camEnd)/2;
    _tc=null;
  } else {
    _tc=e.touches[0].clientX; _dragCam=_camStart;
    _pinchDist=null;
  }
});
cv.addEventListener('touchmove',function(e){
  e.preventDefault();
  if(!_cd.length)return;
  if(e.touches.length===2 && _pinchDist){
    var d=_touches2dist(e);
    var ratio=_pinchDist/d;
    var nv=Math.min(_cd.length,Math.max(10,Math.round(_pinchVis*ratio)));
    _camStart=Math.max(0,Math.round(_pinchCenter-nv/2));
    _camEnd=Math.min(_cd.length-1,_camStart+nv);
    drawChart();
    return;
  }
  if(_tc===null)return;
  var W=cv.parentElement.clientWidth-20;
  var vis=_camEnd-_camStart;
  var dx=(e.touches[0].clientX-_tc)/W*vis;
  _camStart=Math.max(0,Math.min(_cd.length-vis-1,_dragCam-dx));
  _camEnd=_camStart+vis;
  drawChart();
},{passive:false});
window.addEventListener('resize',drawChart);

/* ── Screener all symbols ── */
var _screenerPoll=null;
function toggleScanAll(cb){
  document.getElementById('screenerCard').style.display=cb.checked?'':'none';
  document.getElementById('sym').disabled=cb.checked;
  document.getElementById('btnStart').textContent=cb.checked?'\u25ba Скан всех':'\u25ba Старт';
}
var _origStartOpt=startOpt;
startOpt=function(){
  if(document.getElementById('scanAll')&&document.getElementById('scanAll').checked){
    var body={tf:document.getElementById('tf').value,
      days:parseInt(document.getElementById('days').value),
      sl_pct:parseFloat(document.getElementById('sl_pct').value),
      tp_pct:parseFloat(document.getElementById('tp_pct').value),
      risk_pct:parseFloat(document.getElementById('risk_pct').value)};
    document.getElementById('btnStart').style.display='none';
    document.getElementById('btnStop').style.display='';
    document.getElementById('statusBadge').textContent='\u23f3 запуск...';
    document.getElementById('screenerStatus').textContent='Подключаемся...';
    fetch('/scan_all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){return r.json();})
      .then(function(d){
        if(!d.ok){
          document.getElementById('btnStart').style.display='';
          document.getElementById('btnStop').style.display='none';
          alert(d.msg||'ошибка');return;
        }
        document.getElementById('statusBadge').textContent='скрининг...';
        pollScreener();
      })
      .catch(function(e){
        document.getElementById('btnStart').style.display='';
        document.getElementById('btnStop').style.display='none';
        alert('Ошибка: '+e);
      });
    return;
  }
  _origStartOpt();
};
var _origStopOpt=stopOpt;
stopOpt=function(){
  if(document.getElementById('scanAll')&&document.getElementById('scanAll').checked){
    fetch('/scan_all_stop',{method:'POST'}).then(function(){
      document.getElementById('btnStop').style.display='none';
      document.getElementById('btnStart').style.display='';
      document.getElementById('statusBadge').textContent='остановлен';
      if(_screenerPoll) clearTimeout(_screenerPoll);
    });
    return;
  }
  _origStopOpt();
};
function pollScreener(){
  fetch('/scan_all_status').then(function(r){return r.json();}).then(function(d){
    var pct=d.sym_total>0?Math.round(d.sym_index/d.sym_total*100):0;
    document.getElementById('screenerProg').style.width=pct+'%';
    var workers=d.active_workers||{};
    var syms=Object.keys(workers);
    var workerLines=syms.map(function(s){
      var w=workers[s];
      return w.phase==='fetch'
        ? '  '+s+' — загрузка свечей...'
        : '  '+s+' — цикл '+w.cycle+'/'+w.max_cycles;
    }).join(String.fromCharCode(10));
    var mainLine=d.running
      ? '['+d.sym_index+'/'+d.sym_total+'] завершено'
      : d.done?('\u2705 Готово — проверено '+d.sym_total+' монет'):'—';
    document.getElementById('screenerStatus').textContent=
      workerLines ? mainLine+String.fromCharCode(10)+workerLines : mainLine;
    renderScreenerResults(d.results||[]);
    var symList=d.sym_list||[];
    if(symList.length){
      var doneSet={};
      (d.results||[]).forEach(function(r){doneSet[r.sym]=true;});
      var cur=d.current_sym;
      var chips=symList.map(function(s){
        var done=doneSet[s];
        var active=s===cur&&d.running;
        var col=done?'#4caf50':active?'#ff9800':'#555';
        return '<span style="color:'+col+';margin-right:4px">'+s.replace('_USDT','')+'</span>';
      }).join('');
      document.getElementById('screenerSymList').innerHTML=chips;
    }
    if(d.running){_screenerPoll=setTimeout(pollScreener,1000);}
    else{
      document.getElementById('btnStop').style.display='none';
      document.getElementById('btnStart').style.display='';
      document.getElementById('statusBadge').textContent=d.done?'скрининг завершён':'остановлен';
    }
  }).catch(function(){_screenerPoll=setTimeout(pollScreener,3000);});
}
function renderScreenerResults(results){
  if(!results.length){document.getElementById('screenerTable').innerHTML='';return;}
  var cols='grid-template-columns:20px 1fr 1fr 1fr 1fr 1fr 1fr 1fr';
  var html='<div class="top20-row" style="'+cols+'">'+
    '<span>#</span><span>Монета</span><span>WR%</span><span>PF</span>'+
    '<span>DD%</span><span>T</span><span>$100→$</span><span>SL/TP/sw</span></div>';
  results.forEach(function(e,i){\n    var r=e.result,p=e.params;\n    var wrC=r.winrate>=55?'green':r.winrate>=45?'yellow':'red';\n    var retC=r.total_return>=0?'green':'red';\n    var finalBal=Math.round(100*(1+r.total_return/100));\n    html+='<div class=\"top20-row\" style=\"'+cols+'\">'+\n      '<span style=\"color:#555\">'+(i+1)+'</span>'+\n      '<span style=\"color:#f0b800;font-size:10px\">'+e.sym+'</span>'+\n      '<span class=\"'+wrC+'\">'+r.winrate+'%</span>'+\n      '<span>'+r.profit_factor+'</span>'+\n      '<span class=\"red\">'+r.max_dd+'%</span>'+\n      '<span>'+r.trades+'</span>'+\n      '<span class=\"'+retC+'">$'+finalBal+'</span>'+\n      '<span style=\"color:#888\">'+p.sl_pct+'/'+p.tp_pct+'/'+p.swing_len+'</span>'+\n    '</div>';
  });
  document.getElementById('screenerTable').innerHTML=html;
}
document.addEventListener('visibilitychange',function(){
  if(!document.hidden && _cd.length){
    // Если вкладка вернулась и прошло >5с от последней загрузки — перезагружаем данные
    var tf = document.getElementById('cTf') ? document.getElementById('cTf').value : '15m';
    var sec = TF_SEC[tf] || 900;
    var elapsed = (Date.now() - _lastAutoLoad) / 1000;
    if(elapsed > sec * 0.8){
      loadChart(true);
    } else {
      drawChart();
    }
  }
});

/* ── AMOLED-режим — гасит экран чёрным после простоя, защита от выгорания
   пикселей на AMOLED-дисплеях (по аналогии с WickFill). Кнопка-отпечаток
   выхода и сам блок с данными случайно мигрируют по экрану каждые 30с. ── */
let _amoledOn = localStorage.getItem('smc_amoled')==='1';
let _amoledTimer = null;
const AMOLED_DELAY = 15000; // 15с без активности
const AMOLED_SHIFT_INTERVAL = 30000; // сдвиг раз в 30с
let _amoledShiftTimer = null;

function _amoledIsNight(){
  const h=new Date().getHours();
  return (h>=22 || h<7); // приглушённый режим ночью, не слепит
}

function _amoledPanel(night){
  const now=new Date();
  const time=now.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
  const date=now.toLocaleDateString('ru-RU',{weekday:'long',day:'numeric',month:'long'});
  let html=`<div class="as-time">${time}</div><div class="as-date">${date}</div>`;

  const p=_bestParams, r=window._lastBestResult;
  if(p && r){
    const wrCol=night?'inherit':(r.winrate>=55?'#0f9':r.winrate>=45?'#f0b800':'#f45');
    const retCol=night?'inherit':(r.total_return>=0?'#0f9':'#f45');
    html+=`<div class="as-divider"></div>`+
      `<div class="as-row">`+
        `<div><b style="color:${wrCol}">${r.winrate}%</b><span>WR</span></div>`+
        `<div><b>${r.profit_factor}</b><span>PF</span></div>`+
        `<div><b style="color:${retCol}">${r.total_return}%</b><span>Return</span></div>`+
        `<div><b>${r.trades}</b><span>T</span></div>`+
      `</div>`;
  }

  let statusLine='';
  const statusBadge=document.getElementById('statusBadge');
  if(statusBadge && statusBadge.textContent && statusBadge.textContent!=='готов'){
    statusLine+=statusBadge.textContent;
  }
  const atBadge=document.getElementById('atStatusBadge');
  if(atBadge && atBadge.textContent.indexOf('активен')>=0){
    statusLine+=(statusLine?' · ':'')+'🤖 '+atBadge.textContent.replace('🟢 ','');
  }
  const monBtn=document.getElementById('monBtn');
  if(monBtn && monBtn.classList.contains('btn-go')){
    statusLine+=(statusLine?' · ':'')+'🔔 алерты вкл';
  }
  if(statusLine) html+=`<div class="as-status">${statusLine}</div>`;

  return html;
}

function _amoledExitBtnShift(){
  // кнопка-отпечаток мигрирует по 4 углам экрана со случайным джиттером —
  // сама неподвижная кнопка тоже источник локального выгорания AMOLED.
  const btn=document.getElementById('amoledExitBtn');
  if(!btn) return;
  const w=window.innerWidth, h=window.innerHeight;
  const size=54, m=28, jitter=40;
  const corners=[
    {top:m+Math.random()*jitter,        left:m+Math.random()*jitter},
    {top:m+Math.random()*jitter,        left:w-size-m-Math.random()*jitter},
    {top:h-size-m-Math.random()*jitter, left:m+Math.random()*jitter},
    {top:h-size-m-Math.random()*jitter, left:w-size-m-Math.random()*jitter},
  ];
  const c=corners[Math.floor(Math.random()*corners.length)];
  btn.style.top=Math.max(m,c.top)+'px';
  btn.style.left=Math.max(m,c.left)+'px';
  btn.style.bottom='auto';
  btn.style.right='auto';
}

function _amoledShift(){
  const ov=document.getElementById('amoledOverlay');
  const content=document.getElementById('amoledContent');
  if(!ov||!content||ov.style.display!=='block') return;
  const night=_amoledIsNight();
  content.style.opacity='0';
  setTimeout(()=>{
    if(ov.style.display!=='block') return; // уже разбудили — не дорисовываем
    content.classList.toggle('night',night);
    content.innerHTML=_amoledPanel(night);
    // случайное смещение в пределах центральной зоны — защита от выгорания
    content.style.top=(32+Math.random()*36)+'%';
    content.style.left=(28+Math.random()*44)+'%';
    content.style.opacity='1';
    _amoledExitBtnShift();
  },350);
}

function _amoledStartScreensaver(){
  _amoledShift();
  if(_amoledShiftTimer) clearInterval(_amoledShiftTimer);
  _amoledShiftTimer=setInterval(_amoledShift, AMOLED_SHIFT_INTERVAL);
}

function _amoledStopScreensaver(){
  if(_amoledShiftTimer){clearInterval(_amoledShiftTimer);_amoledShiftTimer=null;}
  const content=document.getElementById('amoledContent');
  if(content){content.style.opacity='0';content.innerHTML='';content.classList.remove('night');}
}

/* ── Screen Wake Lock — не даём ОС гасить экран пока AMOLED активен ── */
let _wakeLock = null;
async function _acquireWakeLock(){
  if(!('wakeLock' in navigator)) return;
  try{
    _wakeLock = await navigator.wakeLock.request('screen');
    _wakeLock.addEventListener('release', ()=>{ _wakeLock=null; });
  }catch(e){ console.warn('WakeLock denied:', e); }
}
function _releaseWakeLock(){
  if(_wakeLock){ _wakeLock.release(); _wakeLock=null; }
}
document.addEventListener('visibilitychange', ()=>{
  if(document.visibilityState==='visible' && _amoledOn) _acquireWakeLock();
});

function _amoledBtnRefresh(){
  const btn=document.getElementById('amoledBtn');
  if(btn){
    btn.style.background=_amoledOn?'#1a8f4a':'';
    btn.style.color=_amoledOn?'#fff':'';
  }
}

function _resetAmoledTimer(){
  if(_amoledTimer){clearTimeout(_amoledTimer);_amoledTimer=null;}
  if(_amoledOn){
    _amoledTimer=setTimeout(()=>{
      const ov=document.getElementById('amoledOverlay');
      if(ov) ov.style.display='block';
      _amoledStartScreensaver();
    }, AMOLED_DELAY);
  }
}

function _requestFS(){
  const el=document.documentElement;
  try{
    if(el.requestFullscreen) el.requestFullscreen({navigationUI:'hide'});
    else if(el.webkitRequestFullscreen) el.webkitRequestFullscreen();
  }catch(e){}
}
function _exitFS(){
  try{
    if(document.exitFullscreen) document.exitFullscreen();
    else if(document.webkitExitFullscreen) document.webkitExitFullscreen();
  }catch(e){}
}
// Если фуллскрин закрыли свайпом/кнопкой браузера — синхронизируем состояние
document.addEventListener('fullscreenchange',()=>{
  if(!document.fullscreenElement && _amoledOn){
    _amoledOn=false;
    localStorage.setItem('smc_amoled','0');
    _amoledBtnRefresh();
    _releaseWakeLock();
    if(_amoledTimer){clearTimeout(_amoledTimer);_amoledTimer=null;}
    const ov=document.getElementById('amoledOverlay');
    if(ov) ov.style.display='none';
    _amoledStopScreensaver();
  }
});

function toggleAmoled(){
  // Если AMOLED уже был включён (восстановлен из localStorage после
  // reload/auto-update), а реального fullscreen нет — requestFullscreen()
  // нельзя вызвать программно без жеста пользователя, поэтому кнопка
  // сначала просто чинит fullscreen вместо выключения режима.
  if(_amoledOn && !document.fullscreenElement){
    _requestFS();
    _acquireWakeLock();
    _resetAmoledTimer();
    return;
  }
  _amoledOn=!_amoledOn;
  localStorage.setItem('smc_amoled', _amoledOn?'1':'0');
  _amoledBtnRefresh();
  if(_amoledOn){
    _requestFS();
    _acquireWakeLock();
    _resetAmoledTimer();
  } else {
    _exitFS();
    _releaseWakeLock();
    if(_amoledTimer){clearTimeout(_amoledTimer);_amoledTimer=null;}
    const ov=document.getElementById('amoledOverlay');
    if(ov) ov.style.display='none';
    _amoledStopScreensaver();
  }
}

['click','touchstart','mousemove','keydown','scroll'].forEach(ev=>{
  document.addEventListener(ev, ()=>{
    if(_amoledOn && !document.fullscreenElement && (ev==='click'||ev==='touchstart'||ev==='keydown')){
      _requestFS();
    }
    // пока оверлей показан — реагируем только на саму кнопку-отпечаток,
    // у неё свой onclick→toggleAmoled() с event.stopPropagation()
    const ov=document.getElementById('amoledOverlay');
    if(ov && ov.style.display==='block') return;
    _resetAmoledTimer();
  }, {passive:true});
});

_amoledBtnRefresh();
if(_amoledOn){ _acquireWakeLock(); _resetAmoledTimer(); }
</script></body></html>
""".replace("__VER__", APP_VERSION)

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
      try:
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
                        "metrics": {k:result[k] for k in ("trades","winrate","profit_factor","max_dd","total_return","fitness","rr")}})
        elif self.path == "/gate_cfg":
            self._json({"gate_key": GATE_KEY[:4]+"***" if GATE_KEY else "",
                        "gate_secret": "***" if GATE_SECRET else "",
                        "has_key": bool(GATE_KEY and GATE_SECRET)})

        elif self.path == "/auto_trade_status":
            with auto_trade_lock:
                st = dict(auto_trade_state)
            self._json(st)

        elif self.path == "/chart_monitor_status":
            with chart_mon_lock:
                self._json({k:v for k,v in chart_mon_state.items() if k != "params"})
        elif self.path == "/alert_cfg":
            self._json({"tg_token": TG_TOKEN, "tg_chat": TG_CHAT, "ntfy_url": NTFY_URL})
        elif self.path == "/fitness_weights":
            with fitness_w_lock:
                self._json(dict(FITNESS_WEIGHTS))
        elif self.path == "/weight_tune_status":
            with weight_tune_lock:
                snap = dict(weight_tune_state)
                snap["logs"] = list(weight_tune_state["logs"])
            self._json(snap)
        elif self.path == "/scan_all_status":
            with screener_lock:
                snap = dict(screener_state)
                snap["active_workers"] = {k: dict(v) for k, v in screener_state["active_workers"].items()}
            self._json(snap)
        else:
            self.send_response(404); self.end_headers()
      except Exception as e:
        try:
            self.send_response(500); self.end_headers()
        except Exception: pass

    def do_POST(self):
        global _opt_thread, _screener_thread
        try:
            length = int(self.headers.get("Content-Length",0))
            body   = json.loads(self.rfile.read(length)) if length else {}
        except Exception as e:
            self._json({"ok":False,"msg":f"bad request: {e}"}); return

        if self.path == "/scan":
            if _opt_thread and _opt_thread.is_alive():
                self._json({"ok":False,"msg":"уже работает"}); return
            _stop_flag.clear()
            with opt_lock:
                opt_state.update({
                    "running":True,"logs":[],"logs_dropped":0,
                    "best":None,"top20":[],"cycle":0,"trials":0,"progress":0,
                    "eco_mode": False,
                    "symbol": body.get("symbol","BTC_USDT"),
                    "tf":     body.get("tf","15m"),
                    "days":   body.get("days",30),
                    "sl_pct": body.get("sl_pct",0.6),
                    "tp_pct": body.get("tp_pct",1.2),
                    "risk_pct": body.get("risk_pct",10.0),
                })
            _opt_thread = threading.Thread(target=run_optimizer, daemon=True)
            _opt_thread.start()
            self._json({"ok":True})

        elif self.path == "/scan_stop":
            _stop_flag.set()
            self._json({"ok":True})

        elif self.path == "/scan_all":
            try:
                if _screener_thread and _screener_thread.is_alive():
                    self._json({"ok":False,"msg":"скрининг уже идёт"}); return
                _screener_stop.clear()
                with screener_lock:
                    screener_state.update({
                        "running":True,"done":False,
                        "tf":body.get("tf","15m"),
                        "days":int(body.get("days",30)),
                        "sl_pct":float(body.get("sl_pct",0.6)),
                        "tp_pct":float(body.get("tp_pct",1.2)),
                        "risk_pct":float(body.get("risk_pct",10.0)),
                        "current_sym":"",
                    })
                _screener_thread = threading.Thread(target=run_screener, daemon=True)
                _screener_thread.start()
                self._json({"ok":True})
            except Exception as e:
                self._json({"ok":False,"msg":f"scan_all error: {e}"})

        elif self.path == "/scan_all_stop":
            _screener_stop.set()
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

        elif self.path == "/fitness_weights":
            with fitness_w_lock:
                for k in FITNESS_WEIGHTS:
                    if k in body:
                        try:
                            FITNESS_WEIGHTS[k] = max(0.0, min(5.0, float(body[k])))
                        except (TypeError, ValueError):
                            pass
                snap = dict(FITNESS_WEIGHTS)
            _save_fitness_weights()
            self._json({"ok": True, "weights": snap})

        elif self.path == "/weight_tune_start":
            global _weight_tune_thread
            with weight_tune_lock:
                if weight_tune_state["running"]:
                    self._json({"ok": False, "error": "уже запущен"})
                    return
                if "n_windows" in body:
                    try: weight_tune_state["n_windows"] = max(2, min(8, int(body["n_windows"])))
                    except: pass
                if "bh_cycles" in body:
                    try: weight_tune_state["bh_cycles"] = max(5, min(50, int(body["bh_cycles"])))
                    except: pass
                if "passes" in body:
                    try: weight_tune_state["passes"] = max(1, min(4, int(body["passes"])))
                    except: pass
            _weight_tune_stop.clear()
            _weight_tune_thread = threading.Thread(target=_run_weight_tune, daemon=True)
            _weight_tune_thread.start()
            self._json({"ok": True})

        elif self.path == "/weight_tune_stop":
            _weight_tune_stop.set()
            self._json({"ok": True})

        elif self.path == "/alert_test":
            ok, err = _test_alert()
            self._json({"ok": ok, "error": err})

        elif self.path == "/gate_cfg":
            global GATE_KEY, GATE_SECRET
            GATE_KEY    = (body.get("gate_key")    or "").strip()
            GATE_SECRET = (body.get("gate_secret") or "").strip()
            _save_gate_cfg()
            self._json({"ok": True})

        elif self.path == "/auto_trade_start":
            global _auto_trade_thread
            sym      = body.get("sym",      "BTC_USDT")
            tf       = body.get("tf",       "15m")
            days     = int(body.get("days", 30))
            risk_pct     = float(body.get("risk_pct",     2.0))
            position_pct = float(body.get("position_pct", 10.0))
            auto_sync    = bool(body.get("auto_sync", False))
            p        = dict(body.get("params") or {})
            if "sl_pct"    not in p: p["sl_pct"]    = body.get("sl", 0.8)
            if "tp_pct"    not in p: p["tp_pct"]    = body.get("tp", 1.6)
            if "swing_len" not in p: p["swing_len"] = 10
            # Защита: без корректных sl/tp открывать реальные позиции нельзя
            try:
                sl_val = float(p["sl_pct"]); tp_val = float(p["tp_pct"])
                assert 0.1 <= sl_val <= 5.0, f"sl_pct вне диапазона: {sl_val}"
                assert 0.1 <= tp_val <= 10.0, f"tp_pct вне диапазона: {tp_val}"
            except Exception as e:
                self._json({"ok": False, "msg": f"Некорректные параметры SL/TP: {e}"}); return
            if not GATE_KEY or not GATE_SECRET:
                self._json({"ok": False, "msg": "Не настроены Gate.io ключи"}); return
            _auto_trade_stop.set()
            if _auto_trade_thread and _auto_trade_thread.is_alive():
                _auto_trade_thread.join(timeout=3)
            _auto_trade_stop.clear()
            with auto_trade_lock:
                auto_trade_state.update({
                    "enabled": True, "symbol": sym, "tf": tf, "days": days,
                    "params": p, "risk_pct": risk_pct, "position_pct": position_pct, "position": None,
                    "last_entry_ts": None, "last_check": 0, "last_error": "",
                    "auto_sync": auto_sync,
                })
            _auto_trade_thread = threading.Thread(target=_auto_trade_loop, daemon=True)
            _auto_trade_thread.start()
            self._json({"ok": True})

        elif self.path == "/auto_trade_sync":
            auto_sync = bool(body.get("auto_sync", False))
            with auto_trade_lock:
                auto_trade_state["auto_sync"] = auto_sync
            self._json({"ok": True, "auto_sync": auto_sync})

        elif self.path == "/auto_trade_stop":
            _auto_trade_stop.set()
            with auto_trade_lock:
                auto_trade_state["enabled"] = False
            self._json({"ok": True})

        elif self.path == "/auto_trade_close":
            # Ручное закрытие текущей позиции
            with auto_trade_lock:
                sym = auto_trade_state.get("symbol", "BTC_USDT")
            try:
                _gate_close_position(sym)
                with auto_trade_lock:
                    auto_trade_state["position"] = None
                self._json({"ok": True})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

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
    _load_gate_cfg()
    _load_fitness_weights()

    server = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"{_C_GRN}SMC Optimizer v{APP_VERSION} — http://0.0.0.0:{PORT}{_C_RST}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nЗавершено"); server.shutdown()

if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass
    main()


