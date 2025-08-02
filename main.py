"""
Главный файл для запуска треугольного арбитража бота
"""

import sys
import signal
import logging
import threading
import time

import config
from htx_api import HtxApi
from arbitrage_strategy import TriangularArbitrageStrategy
from htx_api import HtxApi
from trade_logger import TradeLogger


class ArbitrageBot:
    """Основной класс, управляющий ботом."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.api = HtxApi(api_key=config.API_KEY, secret_key=config.SECRET_KEY, base_url=config.BASE_URL)
        self.trade_logger = TradeLogger()
        self.strategy = TriangularArbitrageStrategy(
            api=self.api,
            logger=self.trade_logger,
            min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
            position_size=config.POSITION_SIZE,
            fee_rate=config.FEE_RATE
        )
        self.strategy_thread = None

    def start(self):
        """Запускает основной цикл стратегии в отдельном потоке."""
        self.logger.info("🚀 Запуск бота...")
        self.strategy.start() # Устанавливаем running = True
        
        self.strategy_thread = threading.Thread(target=self.strategy.run, daemon=True)
        self.strategy_thread.start()

    def stop(self):
        """Останавливает стратегию и записывает лог окончания."""
        self.logger.info("🔌 Остановка бота...")
        if self.strategy:
            self.strategy.stop()
        if self.strategy_thread and self.strategy_thread.is_alive():
            self.strategy_thread.join()
        
        # Передаем итоговый баланс в логгер
        if self.strategy:
            self.trade_logger.log_end(self.strategy.balance)


def signal_handler(sig, frame):
    """Обработчик сигналов, который инициирует остановку."""
    global bot
    if bot:
        bot.stop()
    # Даем время на завершение и выходим
    time.sleep(5) 
    exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    bot = ArbitrageBot()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot.start()

    try:
        # Основной поток просто ждет завершения, так как strategy_thread - демон
        # и завершится вместе с основным потоком.
        # signal_handler обеспечит корректную остановку.
        while bot.strategy_thread.is_alive():
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logging.info("Получен сигнал на выход из основного потока.")
    finally:
        if bot.strategy.running:
            bot.stop()
