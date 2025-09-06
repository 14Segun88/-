# FX Backtesting (Dukascopy + Backtesting.py)

Простой каркас для загрузки минутных данных (M1) с Dukascopy, ресемплинга в M15 и бэктеста трёх идей:
- A: Bollinger + RSI (mean-reversion), RR 1:3
- B: Asia fade (возврат в азиатский диапазон), RR 1:3
- C: EMA pullback (в тренде от отката), RR 1:3

Учитываются издержки: спред + проскальзывание (в пипсах), комиссия (в б.п., basis points),
сессионный множитель спреда. Всё приводится к нужному виду для `Backtest(spread=..., commission=...)`.

## Установка

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Загрузка данных (5 лет M1)

```bash
. .venv/bin/activate
python data_fetch.py --symbol EURUSD --out data --offer-side bid
# Можно задать явный диапазон
# python data_fetch.py --symbol EURUSD --start 2020-09-01 --end 2025-09-01 --out data --offer-side bid
```

Данные сохраняются по месяцам в `data/<SYMBOL>/M1/year=YYYY/month=MM/*.parquet`.

## Бэктест

```bash
. .venv/bin/activate
python backtest.py \
  --data-root data \
  --symbol EURUSD \
  --timeframe M15 \
  --strategy ALL \
  --spread-pips 0.8 \
  --slippage-pips 0.2 \
  --cash 10000 \
  --plot
```

`--strategy` может быть `A`, `B`, `C` или `ALL`.

## CLI параметры

### Риск-менеджмент (позиционный риск)
- `--risk-pct` — доля депозита на риск в одной сделке. По умолчанию `0.01` (1%).
- `--fixed-size` — фиксированный размер позиции (юнитов). Если задан, перекрывает `--risk-pct`.

Формула динамического размера:

```
size = floor((risk_pct * equity) / abs(entry - SL))
# Ограничение сверху по кэшу (без плеча):
size <= floor(0.99 * equity / entry)
```

Примеры:

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --risk-pct 0.005  # риск 0.5% на сделку

python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy C \
  --fixed-size 10000  # фиксированный размер 10k юнитов
```

### Общие параметры стратегий
- `--rr-tp` — RR-множитель для `TP` (по умолчанию `3.0`).
- `--atr-mult-sl` — множитель ATR для `SL` (по умолчанию `1.0`).

### Параметры Strategy A (Bollinger + RSI)
- `--rsi-len` — длина RSI (по умолчанию `14`).
- `--rsi-os` — уровень перепроданности (по умолчанию `30`).
- `--rsi-ob` — уровень перекупленности (по умолчанию `70`).
- `--bb-len` — длина Bollinger (по умолчанию `20`).
- `--bb-std` — StdDev для Bollinger (по умолчанию `2.0`).

### Антишумовые фильтры (Strategy A)
Опционально ограничивают входы для снижения «шумовых» сделок:

- `--a-atr-min` — минимальный ATR (в ценовых единицах), ниже которого входы запрещены.
- `--a-edge-mult` — требуемое расстояние до края полос Боллинджера в мультипликаторах ATR.
- `--a-session-start`, `--a-session-end` — часовой интервал (UTC), в который разрешены входы.

Пример:

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --a-atr-min 0.0005 --a-edge-mult 0.5 --a-session-start 7 --a-session-end 18
```

### Отчёт по скользящим 24 месяцам (Strategy A)
Флаг `--rolling-24m` запускает помесячный прогон за последние 24 месяцев и сохраняет CSV со столбцами
`month,trades,pf,winrate,dd`.

По умолчанию файл сохраняется в `out/rolling_A_24m_{tag}.csv`, где `{tag}` автоматически формируется из параметров и фильтров:

- базовые параметры: `rsi{rsi_len}_bb{bb_std}_atr{atr_mult_sl}_risk{risk_pct%}`
- опционально добавляются: `rr{rr_tp}`, `london{start}-{end}`, `atrmin{value}`, `edge{value}`

Примеры:

```bash
# 1) Базовый роллинг без фильтров → out/rolling_A_24m_rsi14_bb2.0_atr1.0_risk1.csv
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --rolling-24m

# 2) Роллинг с фильтрами (сессия/ATRmin/edge) + дублирование "базы" в корне проекта
#    → out/rolling_A_24m_rsi14_bb2.0_atr1.0_risk1_london7-18_atrmin0.0005_edge0.5.csv
#    → rolling_A_24m.csv (для обратной совместимости пайплайнов)
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --a-session-start 7 --a-session-end 18 --a-atr-min 0.0005 --a-edge-mult 0.5 \
  --rolling-24m --rolling-save-current

# 3) Пользовательский путь с плейсхолдером {tag}
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --rolling-24m --rolling-out "out/custom/rolling_A_24m_{tag}.csv"
```

#### Сводка стабильности (stability_score.py)
Утилита агрегирует все `rolling_A_24m*.csv`, считает стабильность (доля месяцев с PF>1, медианы PF/WR/DD, минимум PF) и
сохраняет рейтинг в `out/rolling_A_24m_summary.csv`.

```bash
. .venv/bin/activate
python stability_score.py --search-root . --pattern "rolling_A_24m*.csv" \
  --out "out/rolling_A_24m_summary.csv" --verbose
```

## Методология устойчивости (Milkshake Score) и гейты

Стандарт оценки стратегии — «честная витрина» на окне скользящих 24 месяцев.

- Витрина: запуск роллинга с флагами `--rolling-24m` и `--rolling-exclude-partial` (исключаем неполные месяцы)
- Честные издержки: всегда указывать `--spread-pips 0.8 --slippage-pips 0.2 --commission-bps 5`
- Ключевые метрики из `stability_score.py`:
  - `pf_min` — минимум PF по месяцам («пол вкуса», главный гейт)
  - `pf_median` — медиана PF («тело вкуса»)
  - `share_pf_gt1` — доля месяцев с PF > 1 («регулярность сладких месяцев»)
  - `dd_median` — медианная просадка
- Router/kill-switch для A: блокирование слабых месяцев с параметрами
  `--a-router-prev-m <N> --a-router-prev-pf-thr <thr> --a-router-min-trades <k>`
  (пример умеренных значений: `3 / 0.6 / 6`).

### Портфель A + D: веса и гейтинг

Компонент D добавляем в портфель только при прохождении порогов качества (гейтинг). Для комбинаций A×D используйте утилиту
`portfolio_compare.py` c поддержкой весов и гейтинга.

Пример (базовый режим, без весов и гейтинга):

```bash
. .venv/bin/activate
python portfolio_compare.py \
  --a out/rolling_A_24m_portA_micro10_s8-17_rr2.0_...csv \
  --d-glob "out/rolling_D_24m_portD_*.csv" \
  --out out/rolling_AD_24m_compare.csv
```

Пример (с весами и гейтингом D):

```bash
. .venv/bin/activate
python portfolio_compare.py \
  --a out/rolling_A_24m_portA_micro10_s8-17_rr2.0_...csv \
  --d-glob "out/rolling_D_24m_portD_*.csv" \
  --a-weight 1.0 --d-weight 0.2 \
  --d-min-pf 0.12 --d-min-share 0.20 --d-min-months 18 \
  --out out/rolling_AD_24m_compare_weighted.csv
```

Рекомендованные начальные пороги допуска D: `pf_min ≥ 0.12`, `share_pf_gt1 ≥ 0.20`, `months ≥ 18`.
Если ни один файл D не проходит гейт, ослабьте пороги или доработайте стратегию D (усиление тренд-фильтров, ATR‑trail, добавление router).

### Кэш ресемплинга (ускорение повторных прогонов)
Флаг `--cache-resampled` включает построение и использование кэша ресемплинга `data/<SYMBOL>/<TF>/resampled_full.parquet`.
Кэш автоматически пересобирается, если исходные M1-файлы были обновлены.

Пример:

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --cache-resampled
```

### Экспорт артефактов (CSV/JSON)
Можно сохранять результаты прогона на диск:

- `--export-trades <csv>` — журнал сделок (CSV).
- `--export-equity <csv>` — кривая капитала (CSV).
- `--export-signals <csv|json>` — сигналы входа с параметрами позиции; поддерживает CSV и JSON (по расширению).
- `--save-run <json>` — конфиг запуска и сводные метрики (JSON).

В путях можно использовать `{key}` для подстановки имени прогона (стратегии): `A`, `B`, `C`. Если `{key}`
не указан и стратегия не `ALL`, к имени файла будет добавлен суффикс `_<key>`.

Пример (все стратегии):

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --cache-resampled \
  --export-trades out/trades_{key}.csv \
  --export-equity out/equity_{key}.csv \
  --export-signals out/signals_{key}.csv \
  --save-run out/run_{key}.json
```

Схема экспортируемых сигналов (`--export-signals`):

- `symbol` — тикер, например `EURUSD`.
- `strategy` — ключ прогона: `A`, `B` или `C`.
- `timestamp` — время сигнала в ISO‑8601 UTC, например `2024-01-15T10:45:00Z`.
- `side` — `buy` или `sell`.
- `price` — цена входа (подсказка, т.к. в живой торговле исполняется по рынку/по правилам брокера).
- `sl` — цена стоп-лосса.
- `tp` — цена тейк-профита.
- `size` — размер позиции (юнитов), рассчитанный по риску или заданный `--fixed-size`.
- `tag` — произвольная метка стратегии (например, `A_long`).

Если файл заканчивается на `.json`, сохраняется JSON-массив объектов. Иначе — CSV.

### Издержки (спред/слиппедж/комиссия/сессии)

- `--spread-pips` — базовый спред в пипсах.
- `--slippage-pips` — базовый слиппедж в пипсах (прибавляется к спреду и переводится в долю цены).
- `--commission-bps` — комиссия в б.п. (basis points) на вход и выход. Передаётся в `Backtest(commission=...)` как доля: `bps / 10000`.
- `--session-spread` — сессионные множители спреда, строка формата `asia=1.2,london=1.0,ny=1.1,other=1.0`.
  Множители усредняются по доле баров в каждой сессии (Asia [0,6), London [7,12), NY [13,17), Other — остальное).

Пример:

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --spread-pips 0.8 --slippage-pips 0.2 --commission-bps 5 \
  --session-spread "asia=1.3,london=1.0,ny=1.1"
```

### Стресс‑матрица издержек

Флаг `--matrix-costs` запускает серию прогонов с комбинациями издержек:
множители по пипсам `x1` и `x2` и комиссии `0` и `10` б.п. Результаты сохраняются в CSV `--matrix-save` (по умолчанию `matrix_results.csv`).

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --matrix-costs --matrix-save out/matrix_results.csv
```

### Монте‑Карло по слиппеджу

Параметры `--mc-slip-std-pips` и `--mc-runs` добавляют к базовому спреду случайный неотрицательный слиппедж `|N(0, σ)|` в пипсах на каждый прогон и запускают серию Монте‑Карло. Результат сохраняется в `mc_slippage_results.csv`.

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --mc-slip-std-pips 0.3 --mc-runs 50
```

### Мини-грид: подбор параметров Strategy A (train/OOS)
Флаг `--tune-a` запускает мини-грид по параметрам `rsi_len`, `bb_std`, `atr_mult_sl`, `risk_pct`.
Результаты сохраняются в CSV (`--tune-save`, по умолчанию `tune_A_results.csv`).
Можно явно задать интервалы train/OOS через `--tune-train-start/--tune-train-end` и `--tune-oos-start/--tune-oos-end`.
Если интервалы не указаны, используется разбиение по времени 70/30.

Пример:

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --cache-resampled \
  --tune-a --tune-save results_A.csv \
  --tune-train-start 2023-01-01 --tune-train-end 2024-06-30 \
  --tune-oos-start 2024-07-01 --tune-oos-end 2024-12-31
```

## Мост к реальной торговле (шаблон коннектора)

Файл `live_connector.py` — пример потребителя экспортированных сигналов для дальнейшей интеграции с брокером/шиной.

Возможности:

- Читает сигналы из CSV/JSON, созданные флагом `--export-signals`.
- Нормализует и выводит заявки (ордеры) в консоль.
- Опционально сохраняет заявки в JSONL (по строке на ордер) для простых пайплайнов.
- По умолчанию работает в режиме `--dry-run`. Режим `--live` — заглушка под реальную интеграцию (TODO).

Примеры:

```bash
. .venv/bin/activate
# Экспорт сигналов из бэктеста
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --export-signals out/signals_A.csv

# Потребление сигналов коннектором (сохранить заявки в JSONL)
python live_connector.py consume out/signals_A.csv --out out/orders_A.jsonl --dry-run

# То же, если экспортировать в JSON
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --export-signals out/signals_A.json
python live_connector.py consume out/signals_A.json --out out/orders_A.jsonl --dry-run
```

JSONL-строки содержат поля: `symbol, side, quantity, order_type, timestamp, price_hint, sl, tp, strategy, client_tag`.
Реальную отправку ордеров необходимо реализовать в `live_connector.py` (раздел TODO),
добавив, например, HTTP‑вызовы к вашему брокеру или запись файлов в «аутбокс».

## Проверки надёжности (быстрая серия)

1) Экзамен на другом периоде:
```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --start 2021-01-01 --end 2023-12-31 --spread-pips 0.8 --slippage-pips 0.2 --cash 10000
```

2) Скользящие месяцы (пример на год):
```bash
# 2024-01 — 2024-12
for m in {01..12}; do \
  python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
    --start 2024-$m-01 --end 2024-$m-28 --spread-pips 0.8 --slippage-pips 0.2 --cash 10000; \
done
```

3) Плохая погода (x2 спред и слиппедж):
```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --spread-pips 1.6 --slippage-pips 0.4 --cash 10000
```

4) Стресс‑матрица издержек (автоматически переберёт несколько сценариев):
```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --matrix-costs --matrix-save out/matrix_results.csv
```

5) Монте‑Карло вариации слиппеджа (распределение чувствительности к σ):
```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy ALL \
  --mc-slip-std-pips 0.3 --mc-runs 100
```

## Примечания
- `spread` в backtesting.py задаётся как доля цены (например, ~0.0001 соответствует ~0.01%). Мы переводим пипсы в долю от медианной цены выборки.
- Данные приводятся к UTC.
- Для кросс-пар типа `USDJPY` размер пипса учитывается (`pip_size()`), чтобы корректно посчитать издержки.
 - `commission` задаётся как доля (например, 0.0005 = 5 б.п.). В CLI используйте `--commission-bps`.
 - При использовании `--save-run` в JSON добавляется раздел `env` с версиями Python/pandas/numpy/backtesting и UTC‑временной меткой.

## Рекомендации по перезапускам (до 10/10)

1) Расширенный подбор параметров Strategy A (expanded grid):

```bash
. .venv/bin/activate
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --cache-resampled \
  --tune-a --tune-grid expanded --tune-save out/tune_A_results.csv
```

2) Выберите 2–3 лучших набора по OOS (PF, WR, DD) и прогоните роллинг с фильтрами:

```bash
# Пример для rsi=18, bb=2.0, atr=1.2, risk=1%
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --rsi-len 18 --bb-std 2.0 --atr-mult-sl 1.2 --risk-pct 0.01 \
  --a-session-start 7 --a-session-end 18 --a-atr-min 0.0005 --a-edge-mult 0.5 \
  --rolling-24m --rolling-out "out/rolling_A_24m_{tag}.csv"
```

3) Пересчитайте сводку стабильности:

```bash
python stability_score.py --search-root . --pattern "rolling_A_24m*.csv" \
  --out "out/rolling_A_24m_summary.csv" --verbose
```

4) Диагностика (по желанию): экспортировать сделки/кривые для топ-наборов

```bash
python backtest.py --data-root data --symbol EURUSD --timeframe M15 --strategy A \
  --export-trades out/trades_{key}.csv --export-equity out/equity_{key}.csv
```
