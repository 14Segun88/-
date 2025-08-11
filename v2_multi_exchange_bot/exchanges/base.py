from abc import ABC, abstractmethod
import asyncio

class BaseExchange(ABC):
    """
    Абстрактный базовый класс для всех бирж.
    Определяет архитектуру с фоновым поллингом цен.
    """

    def __init__(self, apiKey, secret):
        self.apiKey = apiKey
        self.secret = secret
        self.tickers = {}  # Словарь для хранения актуальных цен
        self._is_connected = False
        self._polling_task = None  # Задача для фонового обновления

    @abstractmethod
    async def _fetch_tickers_loop(self, symbols: list):
        """Внутренний метод: бесконечный цикл для опроса цен."""
        pass

    async def connect(self, symbols: list):
        """Подключается к бирже и запускает фоновое обновление цен."""
        if self._is_connected:
            return
        
        # Конкретная логика подключения должна быть в дочерних классах
        # ...

        # Запуск фоновой задачи
        self._polling_task = asyncio.create_task(self._fetch_tickers_loop(symbols))
        self._is_connected = True

    async def disconnect(self):
        """Отключается от биржи и останавливает фоновую задачу."""
        if not self._is_connected:
            return

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass  # Ожидаемое исключение
        
        self._is_connected = False
        # Конкретная логика отключения (например, закрытие сессии) в дочерних классах

    @abstractmethod
    async def place_order(self, symbol: str, side: str, order_type: str, amount: float, price: float = None):
        """Размещает ордер на бирже (заглушка)."""
        pass
