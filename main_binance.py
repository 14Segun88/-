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
        exchange.load_markets()
        logging.info("Successfully connected to Binance API.")
    except (ccxt.ExchangeError, ccxt.NetworkError) as e:
        logging.error(f"Failed to connect to Binance: {e}")
        return

    # --- ФИЛЬТРАЦИЯ ТОРГОВЫХ ПАР ---
    # Используем заранее определенный список валют, чтобы получить ~84 релевантные пары
    TARGET_CURRENCIES = ['USDT', 'BTC', 'ETH', 'LTC', 'TRX', 'DOGE', 'SOL', 'ADA']
    all_exchange_tickers = exchange.symbols
    relevant_tickers = [t for t in all_exchange_tickers if t.split('/')[0] in TARGET_CURRENCIES and t.split('/')[1] in TARGET_CURRENCIES]
    
    logging.info(f"Loaded {len(relevant_tickers)} relevant tickers from the exchange.")

    # --- ИНИЦИАЛИЗАЦИЯ СТРАТЕГИИ ---
    # Создаем экземпляр нашей арбитражной стратегии
    strategy = TriangularArbitrageStrategy(
        exchange=exchange,
        tickers=relevant_tickers,
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

    # Настройка для периодического сохранения
    last_save_time = datetime.now()
    SAVE_INTERVAL_MINUTES = 10 # Сохранять каждые 10 минут

    while not stop_event.is_set():
        try:
            # Получаем стаканы для всех активных тикеров
            active_tickers = [t for t in relevant_tickers if t not in inactive_tickers]
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
            if not all_profits:
                continue

            # Найти лучший путь, используя правильный ключ для словаря
            best_path = max(all_profits, key=lambda x: x['profit_percent'])

            # Отсортировать все пути для отображения дивергенций
            sorted_paths = sorted(all_profits, key=lambda x: x['profit_percent'], reverse=True)

            # --- ВЫВОД ИНДИКАТОРА В КОНСОЛЬ ---
            # Формируем заголовок с балансом, минимальной прибылью и лучшим путем
            header = f"-- Arbitrage Bot Status ({config.EXCHANGE_NAME}) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} --\n"
            status_line = f"Paper Balance: ${strategy.paper_balance:.2f} | Min Profit: {config.MIN_PROFIT_THRESHOLD}% | Best: {best_path['path_name']} ({best_path['profit_percent']:.4f}%)\n"
            separator = '-' * (len(status_line) -1)

            # Формируем блок с дивергенциями
            divergence_lines = ["Divergence Indicator:"]
            for path_info in sorted_paths: 
                divergence_lines.append(f"  {path_info['path_name']:<25} -> {path_info['profit_percent']:+.4f}%")

            # Очищаем консоль и выводим всю информацию
            os.system('cls' if os.name == 'nt' else 'clear')
            print(header + status_line + separator)
            print('\n'.join(divergence_lines))
            print(separator)

            # Собираем данные для отчета по всем путям, включая отбракованные
            for path_info in all_profits:
                strategy.divergence_data.append((datetime.now(), path_info['profit_percent'], path_info['path_name']))

            # --- ЛОГИРОВАНИЕ И СИМУЛЯЦИЯ СДЕЛКИ ---
            # Если найденный лучший путь превышает порог, логируем его как сделку
            if best_path['profit_percent'] > config.MIN_PROFIT_THRESHOLD:
                strategy.log_paper_trade(best_path['profit_percent'], best_path['path_name'])

            # --- ПЕРИОДИЧЕСКОЕ СОХРАНЕНИЕ ДАННЫХ ---
            current_time = datetime.now()
            if (current_time - last_save_time).total_seconds() > SAVE_INTERVAL_MINUTES * 60:
                strategy.save_divergence_chunk() # Новый метод для сохранения части данных
                last_save_time = current_time

            time.sleep(loop_delay)

        except Exception as e:
            logging.error(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
            time.sleep(10)

    logging.info("Shutdown signal received. Saving data...")
    strategy.save_session() # Эта функция теперь будет читать из файла
    logging.info("Data saved. Exiting.")

if __name__ == '__main__':
    main()
