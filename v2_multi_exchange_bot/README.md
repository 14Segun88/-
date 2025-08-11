# Multi-Exchange Arbitrage Bot (Binance + Kraken)

Стабильная версия мультибиржевого арбитражного бота c отчётами:
- Межбиржевой арбитраж (Binance ↔ Kraken)
- Треугольный арбитраж на каждой бирже
- Автоматическая генерация CSV и PNG при остановке бота (Ctrl+C)

## Возможности
- Асинхронный REST-поллинг цен
- Учёт реальных минимальных комиссий:
  - Binance: 0.075% (скидка BNB)
  - Kraken: 0.16% maker (для оценки)
- Конфиг через переменные окружения (секреты не в репозитории)
- PNG-отчёты:
  - Межбиржевой: цены/спреды, Profitability Over Time, Distribution of Arbitrage Opportunities
  - Треугольный: общий отчёт (обе биржи) + per-exchange (`..._report_binance.png`, `..._report_kraken.png`)
  - Агрегированный межбиржевой дистрибутив `..._overall_distribution.png`

## Быстрый старт
1) Установите Python 3.10+
2) Установите зависимости:
```bash
pip install -r requirements.txt
```
3) Создайте `.env` на основе `.env.example` и заполните ключи:
```env
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
KRAKEN_API_KEY=...
KRAKEN_API_SECRET=...
# опционально
HTTP_PROXY=http://172.31.128.1:2080
HTTPS_PROXY=http://172.31.128.1:2080
```
4) Запуск бота:
```bash
python3 -u main.py
```
Остановить Ctrl+C — данные сохранятся в `results/`, PNG будут сгенерированы автоматически.

## Структура
- `main.py` — инициализация, сбор данных, сохранение CSV/PNG
- `config.py` — параметры бота и бирж (секреты читаются из env)
- `exchanges/` — реализации бирж
- `generate_report.py` — межбиржевой PNG
- `generate_triangular_report.py` — треугольный PNG (общий и per-exchange)
- `logs/`, `results/` — артефакты (в .gitignore)

## Отчёты вручную (по существующим CSV)
```bash
python3 generate_report.py results/cross_arbitrage_data_YYYYMMDD_HHMMSS.csv
python3 generate_triangular_report.py results/triangular_arbitrage_data_YYYYMMDD_HHMMSS.csv
```

## Настройки и пороги
- Пары для межбиржи: `config.py` → `SYMBOLS`
- Треугольные цепочки: `TRIANGULAR_ARBITRAGE_CONFIG['chains']`
- Минимальный чистый профит для логирования: `MIN_PROFIT_THRESHOLD` (в %)

## Безопасность
- Секреты в `.env` (в .gitignore)
- Публичный шаблон `.env.example` — для удобства развёртывания

## Лицензия
MIT
