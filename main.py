"""
Главный файл для запуска треугольного арбитража бота
"""

import sys
import signal
import logging
import threading

import config
from htx_api import HtxApi
from arbitrage_strategy import TriangularArbitrageStrategy
from trade_logger import TradeLogger

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Событие для координации graceful shutdown
stop_event = threading.Event()

class ArbitrageBot:
    """Основной класс бота, который инициализирует все компоненты."""
    def __init__(self, trade_logger):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.trade_logger = trade_logger
        self.api = HtxApi(
            api_key=config.API_KEY,
            secret_key=config.SECRET_KEY,
            base_url=config.API_BASE_URL
        )
        self.strategy = TriangularArbitrageStrategy(
            api=self.api,
            logger=self.trade_logger,
            min_profit_threshold=config.MIN_PROFIT_THRESHOLD,
            position_size=config.POSITION_SIZE
        )

    def start(self):
        """Запускает основной цикл стратегии в отдельном потоке."""
        self.logger.info("🚀 Запуск треугольного арбитражного бота для HTX")
        self.logger.info(f"📊 Режим: {'ДЕМО' if config.DEMO_MODE else 'РЕАЛЬНЫЙ'}")
        self.trade_logger.log_start()
        
        # Запускаем стратегию в своем потоке, чтобы основной поток мог ждать stop_event
        strategy_thread = threading.Thread(target=self.strategy.run, daemon=True)
        strategy_thread.start()

    def stop(self):
        """Останавливает стратегию и записывает лог окончания."""
        self.logger.info("🔌 Остановка бота...")
        if self.strategy:
            self.strategy.stop() # Говорим стратегии остановиться
        self.trade_logger.log_end()

def signal_handler(sig, frame):
    """Обработчик сигналов, который устанавливает событие для остановки."""
    logging.info("Получен сигнал на остановку, инициирую завершение...")
    stop_event.set()

def main():
    """Главная функция: настраивает и запускает бота, ожидает сигнала завершения."""
    trade_logger = TradeLogger()
    bot = ArbitrageBot(trade_logger)

    # Настройка обработчиков сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot.start()

    # Основной поток ждет сигнала к завершению
    logging.info("Бот запущен. Нажмите Ctrl+C для остановки.")
    stop_event.wait() # Блокирует выполнение до вызова stop_event.set()

    # После получения сигнала, корректно останавливаем бота
    bot.stop()
    logging.info("Работа бота завершена.")

if __name__ == "__main__":
    main()
