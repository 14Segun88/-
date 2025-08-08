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
EXCHANGE_NAME = 'Binance' # Название биржи для отчетов и логов
BOT_MODE = 'paper_trader'

# Минимальная прибыль для фиксации (в процентах)
MIN_PROFIT_THRESHOLD = 0.3  # 0.3%

# Размер одной сделки в базовой валюте (например, в USDT)
POSITION_SIZE = 11  # Рекомендуется > 10 USDT

# Интервал опроса данных (в секундах)
COLLECTOR_INTERVAL = 2

# 4. Торговые пары (Символы)
# 4 арбитражные связки:
# 1. USDT -> BTC -> ETH -> USDT
# 2. USDT -> BTC -> LTC -> USDT
# 3. USDT -> BTC -> XRP -> USDT
# 4. USDT -> BTC -> ADA -> USDT
SYMBOLS = [
    # Основные пары к USDT
    'BTC/USDT', 'ETH/USDT', 'LTC/USDT', 'ADA/USDT', 'SOL/USDT',
    'DOGE/USDT', 'TRX/USDT',

    # Пары к BTC для создания связок
    'ETH/BTC', 'LTC/BTC', 'ADA/BTC', 'SOL/BTC',
    'DOGE/BTC', 'TRX/BTC',

    # Дополнительная пара для связок через ETH
    'ETH/BTC',
]
BNB_FEE_DISCOUNT = True  # Использовать BNB для оплаты комиссий (25% скидка)

# Дополнительные настройки безопасности
MAX_POSITION_SIZE = 100  # Максимальный размер позиции в USDT
STOP_LOSS_PERCENTAGE = 2.0  # Стоп-лосс в процентах
