# ==============================================================================
# API Ключи и Настройки Бирж
# ==============================================================================
import os

# Настройки Binance
BINANCE_CONFIG = {
    'enabled': True,
    'apiKey': os.getenv('BINANCE_API_KEY', ''),
    'secret': os.getenv('BINANCE_API_SECRET', ''),
    'taker_fee': 0.00075,  # 0.075% с учетом скидки BNB
    'maker_fee': 0.00075,
}

# Настройки Kraken
KRAKEN_CONFIG = {
    'enabled': True,
    'apiKey': os.getenv('KRAKEN_API_KEY', ''),  # Для публичных данных ключ не нужен
    'secret': os.getenv('KRAKEN_API_SECRET', ''),  # Для публичных данных ключ не нужен
    'taker_fee': 0.0026,  # 0.26%
    'maker_fee': 0.0016,
}

# ==============================================================================
# Общие Настройки Бота
# ==============================================================================

# Торговые пары для МЕЖБИРЖЕВОГО арбитража
SYMBOLS = ['BTC/USDT', 'ETH/USDT']

# Минимальный чистый профит для логирования (в процентах)
MIN_PROFIT_THRESHOLD = 0.1  # 0.1%

# Комиссии для оценки (десятичная доля за одну сделку)
# Эти значения переопределят дефолтные комиссии в main.py
FEES = {
    'binance': 0.00075,  # 0.075% с BNB-скидкой
    'kraken': 0.0016,    # 0.16% (maker) базовый уровень Kraken Pro
}

# Настройки прокси (если нужен)
PROXY_URL = os.getenv('HTTP_PROXY', os.getenv('HTTPS_PROXY', 'http://172.31.128.1:2080'))

# ==============================================================================
# Конфигурация треугольного арбитража
# ==============================================================================
# Определите цепочки для поиска. Например: ['USDT', 'BTC', 'ETH']
# Это означает, что бот будет искать возможность провернуть сделку:
# USDT -> BTC (купить BTC за USDT)
# BTC -> ETH (купить ETH за BTC)
# ETH -> USDT (продать ETH за USDT)
# ...и получить в итоге больше USDT.
TRIANGULAR_ARBITRAGE_CONFIG = {
    'enabled': True,
    'chains': [
        ['USDT', 'BTC', 'ETH'],  # Ваша цепочка USDT -> BTC -> ETH -> USDT
    ]
}

# ==============================================================================
# Не трогайте эту часть, если не уверены
# ==============================================================================

EXCHANGES = {
    'binance': {
        'enabled': BINANCE_CONFIG['enabled'],
        'class': 'binance',
        'api_config': {
            'apiKey': BINANCE_CONFIG['apiKey'],
            'secret': BINANCE_CONFIG['secret'],
            'proxy': PROXY_URL
        },
        'fees': {
            'taker': BINANCE_CONFIG['taker_fee'],
            'maker': BINANCE_CONFIG['maker_fee']
        }
    },
    'kraken': {
        'enabled': KRAKEN_CONFIG['enabled'],
        'class': 'kraken',
        'api_config': {
            'apiKey': KRAKEN_CONFIG['apiKey'],
            'secret': KRAKEN_CONFIG['secret']
        },
        'fees': {
            'taker': KRAKEN_CONFIG['taker_fee'],
            'maker': KRAKEN_CONFIG['maker_fee']
        }
    }
}
