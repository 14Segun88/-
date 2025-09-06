# Tiger Trade Pattern Lab & Trend Strategy D

Цель: построить честный конвейер данных Tiger Trade (EURUSD/6E), обнаружить устойчивые режимы и паттерны (OI/кластеры/«big trades» + консолидации), превратить их в простые гейты и протестировать трендовую стратегию D и/или гейтинг для A на витрине rolling 24m, 5 лет и далее (2008+).

## Структура проекта

```
`tiger_trade/`
  README.md
  requirements.txt
  .env.example
  .gitignore
  src/
    __init__.py
    config.py          # загрузка API ключей/настроек из .env/окружения
    tiger_client.py    # клиент Tiger Trade + загрузка OI (6E) / минуток / кластеров
    pattern_lab.py     # агрегация фич по неделям/месяцам, скоринг простых порогов, отчёты
    gates.py           # функции-гейты (prev OI slope, delta sum, large trades intensity и т.п.)
  data/
    external/
      TigerTrade/
        EURUSD/        # минутки EURUSD (UTC), расширяемые
        6E/            # минутки/офлоу 6E (UTC), если доступны
        6E_daily/      # дневной OI по 6E (UTC)
  out/                 # отчёты pattern_lab и вспомогательные артефакты
```

## Настройка окружения

1) Python 3.10+
2) Установить зависимости:
```
pip install -r tiger_trade/requirements.txt
```
3) Создать `.env` (см. `.env.example`):
```
TIGER_API_KEY=...                 # ключ Tiger Trade (не коммитить)
TIGER_BASE_URL=https://...        # базовый URL API
NDAQ_API_KEY=...                  # ключ Nasdaq Data Link (Quandl) для дневного OI 6E (опционально)
CME_SYMBOL_6E=6E
TT_SYMBOL_EURUSD=EURUSD
TZ=UTC
```

## Источники данных
- Tiger Trade API/экспорт: минутки/тик, кластеры, дельта, «big trades» (UTC). Положить в `data/external/TigerTrade/...` если выгрузка CSV.
- OI (Open Interest) 6E (CME) — дневные значения (через Nasdaq Data Link или CSV). Путь `data/external/TigerTrade/6E_daily/`.

## Pattern Lab: быстрый старт
Агрегировать фичи и получить первичный отчёт:
```
python -m tiger_trade.src.pattern_lab \
  --eurusd-path tiger_trade/data/external/TigerTrade/EURUSD \
  --oi-daily-path tiger_trade/data/external/TigerTrade/6E_daily \
  --out tiger_trade/out/pattern_report.csv
```
Выход: CSV со списком кандидатов-гейтов и базовых метрик устойчивости (доли активных месяцев, простые пороги и т.п.). На пилоте данные могут быть пустыми — заполните `data/external` перед запуском.

## Что считается «честно»
- OI/недельные и дневные признаки применяются только «на следующий период» (без look-ahead).
- Кластеры/дельта используют только закрытые бары на момент входа.
- Порогов немного (1–2), монотонность и штраф за сложность; валидация по эпохам.
- Проверки: rolling 24m → 5y → расширение до 2008.

## Следующие шаги
- Подключить реальные источники (API/CSV) через `tiger_client.py`.
- Сформировать первичный отчёт Pattern Lab (2021–2025), выбрать 1–2 гейта.
- Добавить гейты в наш бэктест (Strategy D, а также гейтинг A) и проверить витрину 24м/5y.

## Безопасность ключей
- Ключи храните только в `.env`/переменных окружения. `.env` не коммитим (см. `.gitignore`).
