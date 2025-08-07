import ccxt
import logging
import time
import signal
import threading
from datetime import datetime
import os

import config
from arbitrage_strategy import TriangularArbitrageStrategy

def setup_logging():
    """Настраивает основной логгер для вывода в консоль."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format)

def setup_trade_logger():
    """Настраивает логгер для записи сделок в файл."""
    os.makedirs('res', exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join('res', f'res_{timestamp}.log')

    trade_logger = logging.getLogger('trade_logger')
    trade_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_filename)
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    trade_logger.addHandler(handler)
    logging.info(f"Trade results will be saved to {log_filename}")
    return trade_logger

def display_divergence(all_profits, strategy_instance):
    """Отображает таблицу с данными о дивергенции в консоли."""
    if not all_profits:
        return

    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"--- Arbitrage Opportunities (Huobi) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    best_path_data = max(all_profits.values(), key=lambda x: x['profit_percent'])
    print(f"Paper Balance: ${strategy_instance.paper_balance:.2f} | Min Profit: {strategy_instance.min_profit_threshold}% | Best: {best_path_data['path']} ({best_path_data['profit_percent']:+.4f}%)")
    print("-" * 70)

    sorted_paths = sorted(all_profits.values(), key=lambda x: x['path'])
    
    columns = 2
    col_width = 35
    num_items = len(sorted_paths)
    rows = (num_items + columns - 1) // columns

    for i in range(rows):
        row_str = ""
        for j in range(columns):
            index = i + j * rows
            if index < num_items:
                item = sorted_paths[index]
                display_color = "\033[92m" if item['profit_percent'] > 0 else "\033[91m"
                reset_color = "\033[0m"
                path_str = f"{item['path']:<25} -> {display_color}{item['profit_percent']:+.4f}%{reset_color}"
                row_str += f"{path_str:<{col_width+9}}"
        print(row_str)
    print("-" * 70, flush=True)

def main():
    setup_logging()
    trade_logger = setup_trade_logger()

    exchange = ccxt.huobi(config.API_CONFIG)
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

    logging.info(f"Starting bot in '{config.MODE}' mode.")
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
                    if 'invalid symbol' in str(e).lower() or 'invalid-parameter' in str(e).lower():
                        logging.warning(f"Ticker {ticker} is invalid, adding to ignore list. Reason: {e}")
                        inactive_tickers.add(ticker)
                    else:
                        logging.warning(f"Could not fetch order book for {ticker}: {e}")
                        time.sleep(1)
            
            # Расчет и логирование дивергенции
            divergence_data = strategy.calculate_divergence()
            if divergence_data:
                current_time = datetime.now()
                profit_percent = divergence_data['profit_percent']
                path_name = divergence_data['path_name']
                
                strategy.divergence_data.append((current_time, profit_percent, path_name))
                
                print(f"\r{current_time.strftime('%Y-%m-%d %H:%M:%S')} | Max divergence: {profit_percent:+.4f}% on {path_name.ljust(25)}", end="")

                if profit_percent > config.MIN_PROFIT_THRESHOLD:
                    print() # Перевод строки перед сделкой
                    strategy.log_paper_trade(profit_percent, path_name)

            time.sleep(config.LOOP_DELAY)

        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(10)

    logging.info("Shutdown signal received. Saving data...")
    strategy.save_session()
    logging.info("Data saved. Exiting.")

if __name__ == '__main__':
    main()