import ccxt
import time
import logging
import json
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import os

from arbitrage_strategy import TriangularArbitrageStrategy
from config import SYMBOLS, MIN_PROFIT_THRESHOLD, POSITION_SIZE, FEE_RATE, COLLECTOR_INTERVAL, BOT_MODE, API_KEY, SECRET_KEY

def setup_loggers():
    """Настраивает основной логгер для консоли и отдельный логгер для записи сделок в файл."""
    # Основной логгер для вывода в консоль
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Отдельный логгер для результатов торговли
    trade_logger = logging.getLogger('trader')
    trade_logger.setLevel(logging.INFO)
    trade_logger.propagate = False  # Не выводить сообщения этого логгера в консоль

    log_dir = 'res'
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(log_dir, f'res_{timestamp}.log')
    
    file_handler = logging.FileHandler(filename)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    trade_logger.addHandler(file_handler)
    
    logging.info(f"Trade results will be saved to {filename}")
    return trade_logger

def main():
    trade_logger = setup_loggers()

    # Инициализация CCXT
    exchange = ccxt.huobi({
        'apiKey': API_KEY,
        'secret': SECRET_KEY,
        'options': {
            'defaultType': 'spot',
        },
        'rateLimit': 200, # Уменьшаем задержку для более частых запросов
        'enableRateLimit': True,
    })

    # Проверка доступности API
    try:
        exchange.load_markets()
        logging.info("Successfully connected to Huobi API.")
    except ccxt.BaseError as e:
        logging.error(f"Error connecting to Huobi API: {e}")
        return

    # Инициализация стратегии
    strategy = TriangularArbitrageStrategy(
        symbols=SYMBOLS,
        min_profit_threshold=MIN_PROFIT_THRESHOLD,
        position_size=POSITION_SIZE,
        fee_rate=FEE_RATE,
        trade_logger=trade_logger,
        exchange=exchange, # <-- Передаем созданный объект биржи
        exchange_name='Huobi' # <-- Указываем имя для логов
    )

    logging.info(f"Starting bot in '{BOT_MODE}' mode.")
    logging.info(f"Symbols: {SYMBOLS}")
    logging.info(f"Position size: ${POSITION_SIZE} USDT")
    logging.info(f"Minimum profit threshold: {MIN_PROFIT_THRESHOLD}%")

    try:
        while True:
            try:
                # Получаем стаканы для всех символов
                for symbol in SYMBOLS:
                    order_book = exchange.fetch_order_book(symbol, limit=20) # limit=20 - глубина стакана
                    strategy.update_market_data(symbol, order_book)
                
                # Рассчитываем арбитраж на основе полных стаканов
                profit_percentage = strategy.calculate_arbitrage()

                # Выводим текущее состояние рынка для "ощущения"
                # Используем print с \r, чтобы строка постоянно обновлялась
                print(f"Current market divergence: {profit_percentage:+.4f}%   ", end="\r")

                # Логируем и симулируем только те возможности, которые превышают наш порог
                if profit_percentage > MIN_PROFIT_THRESHOLD:
                    logging.info(f"Found potential arbitrage opportunity (before fees): {profit_percentage:.4f}%")
                    
                    # Если режим paper_trader, логируем сделку через стратегию
                    if BOT_MODE == 'paper_trader':
                        strategy.log_paper_trade(profit_percentage)

                # Собираем статистику по всем расхождениям с временными метками
                strategy.divergence_data.append((datetime.now(), profit_percentage))

            except ccxt.NetworkError as e:
                logging.warning(f"Network error: {e}. Retrying...")
                time.sleep(5)
            except ccxt.ExchangeError as e:
                logging.error(f"Exchange error: {e}. Check API keys or symbol names.")
                time.sleep(20)
            except Exception as e:
                logging.error(f"An unexpected error occurred: {e}", exc_info=True)
                time.sleep(10)

            time.sleep(COLLECTOR_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Shutdown signal received. Saving data...")
        strategy.save_divergence_data()
        logging.info("Data saved. Exiting.")

if __name__ == "__main__":
    main()