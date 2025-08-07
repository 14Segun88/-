import ccxt
import logging
import time
import signal
import threading
from datetime import datetime
import os

import config_binance as config
from arbitrage_strategy import TriangularArbitrageStrategy

def setup_logging():
    """Настраивает основной логгер для вывода в консоль."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format, force=True)

def setup_trade_logger():
    """Настраивает логгер для записи сделок в файл для Binance."""
    os.makedirs('res_binance', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join('res_binance', f'res_{timestamp}.log')

    trade_logger = logging.getLogger('trade_logger_binance')
    trade_logger.propagate = False
    
    if trade_logger.hasHandlers():
        trade_logger.handlers.clear()
        
    trade_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_filename)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    trade_logger.addHandler(handler)
    logging.info(f"Trade results for Binance will be saved to {log_filename}")
    return trade_logger

def main():
    setup_logging()
    trade_logger = setup_trade_logger()

    exchange = ccxt.binance(config.API_CONFIG)
    try:
        exchange.load_markets(True)
        logging.info(f"Successfully connected to {exchange.name} API.")
    except (ccxt.ExchangeError, ccxt.NetworkError) as e:
        logging.error(f"Failed to connect to {exchange.name}: {e}")
        return

    # --- ДИНАМИЧЕСКАЯ ЗАГРУЗКА ТИКЕРОВ ---
    TARGET_CURRENCIES = ['USDT', 'BTC', 'ETH', 'LTC', 'TRX', 'DOGE', 'SOL', 'ADA']
    all_exchange_tickers = exchange.symbols
    tickers = [t for t in all_exchange_tickers if t.split('/')[0] in TARGET_CURRENCIES and t.split('/')[1] in TARGET_CURRENCIES]
    logging.info(f"Loaded {len(tickers)} relevant tickers from the exchange.")
    # --------------------------------------

    strategy = TriangularArbitrageStrategy(
        tickers=tickers,
        min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
        position_size=config.POSITION_SIZE,
        fee_rate=config.FEE_RATE,
        trade_logger=trade_logger,
        exchange_name=exchange.name
    )

    mode = getattr(config, 'BOT_MODE', 'paper_trader')
    loop_delay = getattr(config, 'LOOP_DELAY', 1)

    logging.info(f"Starting bot in '{mode}' mode.")
    logging.info(f"Position size: ${config.POSITION_SIZE} USDT")
    logging.info(f"Minimum profit threshold: {config.MIN_PROFIT_THRESHOLD}%")
    logging.info("Starting bot... Press Ctrl+C to stop.")

    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda s, f: stop_event.set())
    signal.signal(signal.SIGTERM, lambda s, f: stop_event.set())
    inactive_tickers = set()

    # Основной цикл бота
    while not stop_event.is_set():
        try:
            # Получаем стаканы для всех активных тикеров
            active_tickers = [t for t in tickers if t not in inactive_tickers]
            for ticker in active_tickers:
                try:
                    order_book = exchange.fetch_order_book(ticker, limit=5)
                    strategy.update_market_data(ticker, order_book)
                except (ccxt.ExchangeError, ccxt.NetworkError) as e:
                    if 'does not have market symbol' in str(e).lower() or 'invalid symbol' in str(e).lower():
                        logging.warning(f"Ticker {ticker} is invalid, adding to ignore list. Reason: {e}")
                        inactive_tickers.add(ticker)
                    else:
                        logging.warning(f"Could not fetch order book for {ticker}: {e}")
                        time.sleep(1)
            
            # Расчет и логирование дивергенции
            all_profits = strategy.calculate_all_paths_profit()
            if all_profits:
                os.system('cls' if os.name == 'nt' else 'clear')
                current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                best_path = max(all_profits, key=all_profits.get)
                best_profit = all_profits[best_path]

                print(f"--- Arbitrage Bot Status (Binance) | {current_time_str} ---")
                print(f"Paper Balance: ${strategy.paper_balance:.2f} | Min Profit: {config.MIN_PROFIT_THRESHOLD}% | Best: {best_path} ({best_profit:+.4f}%)")
                print("-" * 70)
                print("Divergence Indicator:")

                sorted_paths = sorted(all_profits.items(), key=lambda item: item[1], reverse=True)

                for path, profit in sorted_paths:
                    display_color = "\033[92m" if profit > config.MIN_PROFIT_THRESHOLD else ("\033[93m" if profit > 0 else "\033[91m")
                    reset_code = "\033[0m"
                    print(f"  {path:<25} -> {display_color}{profit:+.4f}%{reset_code}")
                    # Собираем данные для отчета по всем путям
                    strategy.divergence_data.append((datetime.now(), profit, path))
                print("-" * 70, flush=True)

                if best_profit > config.MIN_PROFIT_THRESHOLD:
                    logging.info(f"\n---> Найдена выгодная возможность на Binance: {best_path} с прибылью {best_profit:+.4f}% <---")
                    if config.BOT_MODE == 'paper_trader':
                        strategy.log_paper_trade(best_profit, best_path)

            time.sleep(loop_delay)

        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(10)

    logging.info("Shutdown signal received. Saving data...")
    strategy.save_session()
    logging.info("Data saved. Exiting.")

if __name__ == '__main__':
    main()
