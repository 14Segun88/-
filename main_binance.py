import asyncio
import logging
import os
import signal
from datetime import datetime
import ccxt.pro as ccxt_pro

import config_binance as config
from arbitrage_strategy import TriangularArbitrageStrategy
from websocket_manager import WebsocketManager

# --- Глобальные переменные ---
strategy = None
last_save_time = None
SAVE_INTERVAL_MINUTES = 10

def setup_logging():
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_format, force=True)

def setup_trade_logger():
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

async def handle_orderbook_update(orderbook: dict):
    """
    Callback-функция, которая вызывается при каждом обновлении стакана через WebSocket.
    """
    global strategy, last_save_time

    # 1. Обновление данных в стратегии
    symbol = orderbook['symbol']
    strategy.update_market_data(symbol, orderbook)

    # 2. Измерение и обновление задержки
    receive_time_ms = datetime.now().timestamp() * 1000
    server_time_ms = orderbook['timestamp']
    latency = receive_time_ms - server_time_ms
    strategy.update_latency(latency)

    # 3. Расчет всех арбитражных путей
    all_profits = strategy.calculate_all_paths_profit()
    if not all_profits:
        return

    # 4. Поиск лучшего пути и отображение в консоли
    best_path = max(all_profits, key=lambda x: x['profit_percent'])
    header = f"-- Arbitrage Bot Status (Binance) | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} --\n"
    status_line = f"Balance: ${strategy.paper_balance:.2f} | Latency: {latency:.1f}ms | Best: {best_path['path_name']} ({best_path['profit_percent']:.4f}%)\n"
    separator = '-' * (len(status_line) - 1)
    os.system('cls' if os.name == 'nt' else 'clear')
    print(header + status_line + separator)

    # 5. Логирование сделки, если найден профит
    if best_path['profit_percent'] > config.MIN_PROFIT_THRESHOLD:
        strategy.log_paper_trade(best_path['profit_percent'], best_path['path_name'])

    # 6. Периодическое сохранение данных
    current_time = datetime.now()
    if (current_time - last_save_time).total_seconds() > SAVE_INTERVAL_MINUTES * 60:
        strategy.save_divergence_chunk()
        last_save_time = current_time

async def main_async():
    """Основная асинхронная функция для запуска бота."""
    global strategy, last_save_time
    setup_logging()
    trade_logger = setup_trade_logger()

    # Используем временный синхронный клиент для получения списка тикеров
    temp_exchange = ccxt_pro.binance()
    await temp_exchange.load_markets()
    TARGET_CURRENCIES = ['USDT', 'BTC', 'ETH', 'LTC', 'TRX', 'DOGE', 'SOL', 'ADA']
    relevant_tickers = [t for t in temp_exchange.symbols if t.split('/')[0] in TARGET_CURRENCIES and t.split('/')[1] in TARGET_CURRENCIES]
    await temp_exchange.close()

    logging.info(f"Loaded {len(relevant_tickers)} relevant tickers.")

    existing_tickers = ['LTC/BTC', 'ETH/BTC', 'LTC/ETH', 'LTC/USDT', 'ETH/USDT', 'BTC/USDT']
    new_tickers = ['SOL/USDT', 'SOL/BTC', 'ADA/USDT', 'ADA/BTC']
    all_tickers = existing_tickers + new_tickers

    strategy = TriangularArbitrageStrategy(
        exchange=None, # Exchange больше не нужен здесь, т.к. данные идут через WS
        tickers=all_tickers,
        new_tickers=new_tickers,  # Pass new tickers for special handling
        min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
        position_size=config.POSITION_SIZE,
        fee_rate=config.FEE_RATE,
        trade_logger=trade_logger,
        exchange_name='binance'
    )
    last_save_time = datetime.now()

    # Инициализация и запуск WebSocket менеджера
    ws_manager = WebsocketManager(on_message_callback=handle_orderbook_update)
    ws_task = await ws_manager.start(all_tickers, config.API_CONFIG)

    # Настройка graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT, stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    logging.info("Bot is running with WebSocket. Press Ctrl+C to stop.")
    await stop_event.wait()

    # Остановка и очистка
    logging.info("Stopping bot...")
    await ws_manager.stop()
    await ws_task
    strategy.save_session()
    logging.info("Bot has been stopped.")

if __name__ == '__main__':
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logging.info("Main process interrupted.")
