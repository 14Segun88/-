# Конфигурация для треугольного арбитража бота - BINANCE

# 1. Настройки API (Обязательно)
API_CONFIG = {
    'apiKey': 'MvV3eNsenTdNinmtt1hXVOjNg1VsmjtNY4iZpqddN6f03DuX1GB8DuuKPOiUSOEy',
    'secret': 'XcDJGf39tlsl4G8qUu86wQqpEoqZgRfrl5yS8j7yiampncgrJ05PxQYUJYdUyPmG',
    'options': {
        'defaultType': 'spot',
    },
}

# 2. Настройки комиссии (Binance с BNB)
# Используем комиссию 'maker' (0.075%), так как будем выставлять лимитные ордера.
FEE_RATE = 0.00075  # 0.075%

# 3. Настройки бота
# Режим работы: 'scanner' (только ищет) или 'paper_trader' (симулирует сделки)
BOT_MODE = 'paper_trader'

# Минимальная прибыль для фиксации (в процентах)
MIN_PROFIT_THRESHOLD = 0.01  # 0.01%

# Размер одной сделки в базовой валюте (например, в USDT)
POSITION_SIZE = 11  # Рекомендуется > 10 USDT

# Интервал опроса данных (в секундах)
COLLECTOR_INTERVAL = 2

# 4. Торговые пары (Символы)
# Пример для Binance
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'ETH/BTC',
    'LTC/USDT', 'LTC/BTC', 'LTC/ETH',
    'XRP/USDT', 'XRP/BTC', 'XRP/ETH',
    'ADA/USDT', 'ADA/BTC', 'ADA/ETH',
    'BNB/USDT', 'BNB/BTC', 'BNB/ETH'
]
BNB_FEE_DISCOUNT = True  # Использовать BNB для оплаты комиссий (25% скидка)

# Торговые пары для Binance (те же самые)
SYMBOLS = ['BTC/USDT', 'LTC/USDT', 'LTC/BTC']

# Дополнительные настройки безопасности
MAX_POSITION_SIZE = 100  # Максимальный размер позиции в USDT
STOP_LOSS_PERCENTAGE = 2.0  # Стоп-лосс в процентах
