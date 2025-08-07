API_CONFIG = {
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'options': {
        'defaultType': 'spot',
    },
    'rateLimit': 200,
    'enableRateLimit': True,
}

# --- ОСНОВНЫЕ НАСТРОЙКИ ---
MODE = 'paper_trader'  # 'paper_trader' или 'live_trader'
POSITION_SIZE = 100.0  # Размер позиции в USDT
MIN_PROFIT_THRESHOLD = 0.1  # Минимальный порог прибыли в % для логирования
FEE_RATE = 0.002  # Комиссия Huobi (0.2%)
LOOP_DELAY = 2 # Пауза между циклами опроса в секундах
