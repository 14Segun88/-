#!/usr/bin/env python3
import ccxt
import logging
import time
import signal
import threading
from datetime import datetime
import os

# Импортируем конфигурацию и стратегию
import config_binance as config
from arbitrage_strategy import TriangularArbitrageStrategy

# Флаг для корректного завершения работы (используем threading.Event)
shutdown_flag = threading.Event()

def setup_loggers():
    """Настраивает основной логгер для консоли и отдельный логгер для записи сделок в файл."""
    # Убедимся, что папки для логов существуют
    os.makedirs('res_binance', exist_ok=True)
    os.makedirs('statistics', exist_ok=True)

    # Основной логгер
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')

    # Логгер для сделок (с уникальным именем для Binance)
    trade_logger = logging.getLogger('trade_logger_binance')
    trade_logger.propagate = False
    if not trade_logger.handlers:
        log_filename = f"res_binance/trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        trade_logger.addHandler(file_handler)
        trade_logger.setLevel(logging.INFO)
        logging.info(f"Trade results will be saved to {log_filename}")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения работы."""
    logging.info("\nShutdown signal received. Finishing current cycle and saving data...")
    shutdown_flag.set()

def main():
    """Основная функция для запуска бота."""
    setup_loggers()
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logging.info("--- Starting Binance Triangular Arbitrage Bot ---")
    logging.info(f"Bot Mode: {config.BOT_MODE}")

    try:
        exchange = ccxt.binance(config.API_CONFIG)
        exchange.load_markets()
        logging.info("Successfully connected to Binance.")
    except Exception as e:
        logging.error(f"Failed to connect to Binance: {e}")
        return

    strategy = TriangularArbitrageStrategy(
        exchange=exchange,
        symbols=config.SYMBOLS,
        min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
        position_size=config.POSITION_SIZE,
        fee_rate=config.FEE_RATE,
        trade_logger=logging.getLogger('trade_logger_binance'),
        exchange_name='Binance'
    )

    # The arbitrage paths are defined within the strategy's __init__ method.
    if not strategy.paths:
        logging.error("No triangular arbitrage paths were defined in the strategy. Exiting.")
        return
    logging.info(f"Using {len(strategy.paths)} potential arbitrage paths defined in the strategy.")

    logging.info("Starting market scan...")



    # --- Main Bot Loop ---
    while not shutdown_flag.is_set():
        try:
            # 1. Fetch order books for all required symbols
            all_books_fetched = True
            for symbol in strategy.symbols:
                try:
                    order_book = exchange.fetch_order_book(symbol, limit=5)
                    strategy.update_market_data(symbol, order_book)
                except Exception as e:
                    logging.warning(f"Could not fetch order book for {symbol}: {e}")
                    all_books_fetched = False
                    break # Don't calculate if one symbol fails
            
            if not all_books_fetched:
                time.sleep(config.COLLECTOR_INTERVAL)
                continue

            # 2. Calculate arbitrage based on the new data
            profit_percentage = strategy.calculate_arbitrage()

            # 3. Process the result
            if profit_percentage is not None:
                print(f"\rCurrent Binance market divergence: {profit_percentage:+.4f}%", end="", flush=True)
                strategy.divergence_data.append((datetime.now(), profit_percentage))

                if profit_percentage > config.MIN_PROFIT_THRESHOLD:
                    logging.info(f"\n---> Found profitable opportunity on Binance: {profit_percentage:+.4f}% <---")
                    
                    if config.BOT_MODE == 'paper_trader':
                        # Вся логика симуляции и логирования теперь внутри стратегии
                        strategy.log_paper_trade(profit_percentage)

        except ccxt.NetworkError as e:
            logging.warning(f"\nNetwork error: {e}. Retrying...")
            time.sleep(5)
        except ccxt.ExchangeError as e:
            logging.error(f"\nExchange error: {e}. Check API keys or symbol names.")
            time.sleep(20)
        except Exception as e:
            logging.error(f"\nUnexpected error: {e}")
            time.sleep(10)
        
        time.sleep(config.COLLECTOR_INTERVAL)

    # Сохранение данных после завершения
    logging.info("\nBot is shutting down. Saving collected data...")
    strategy.save_divergence_data()
    logging.info("Data saved successfully. Goodbye!")

if __name__ == "__main__":
    main()

