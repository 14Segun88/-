# Конфигурация для треугольного арбитража бота

# Tiger Trade API настройки
API_KEY = "685d99fa-frbghq7rnm-d31ff320-13b69"  # Access Key
SECRET_KEY = "69c659d1-3c7b48ef-0794161a-994b3"  # Secret Key
BASE_URL = "https://api.huobi.pro"  # Базовый URL для API HTX
DEMO_MODE = True  # True для демо-счета, False для реального

# Настройки стратегии
MIN_PROFIT_THRESHOLD = 0.1  # Минимальный процент прибыли для входа в сделку
# Комиссия за одну сделку (0.2% = 0.002)
FEE_RATE = 0.00075

# --- РЕЖИМ РАБОТЫ БОТА ---
# 'scanner' - только сканирует рынок и собирает статистику.
# 'paper_trader' - симулирует сделки при обнаружении возможности.
BOT_MODE = 'paper_trader'  # Измените на 'scanner' для простого сбора статистики
POSITION_SIZE = 15  # Размер позиции в USDT
COLLECTOR_INTERVAL = 1  # Интервал между запросами к API в секундах

# Торговые пары
# Формат CCXT: 'BASE/QUOTE'
SYMBOLS = ['BTC/USDT', 'LTC/USDT', 'LTC/BTC']

# Настройки логирования
LOG_LEVEL = 'INFO'
LOG_FILE = 'arbitrage_bot.log'
