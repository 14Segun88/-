import asyncio
import logging
import os
from binance import AsyncClient
import time
from .base import BaseExchange

class BinanceExchange(BaseExchange):
    """Интеграция с Binance, использующая фоновый REST API поллинг."""

    def __init__(self, apiKey, secret):
        super().__init__(apiKey, secret)
        self.client = None
        
        # Настройка прокси из переменных окружения
        proxy_url = os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY')
        if proxy_url:
            logging.info(f"Using proxy for Binance: {proxy_url}")

    async def _fetch_tickers_loop(self, symbols: list):
        """Бесконечный цикл для опроса цен всех указанных символов."""
        logging.info(f"Starting Binance REST API polling loop for {len(symbols)} symbols.")
        while self._is_connected:
            try:
                # Получаем тикеры для всех символов одним запросом
                tickers_data = []
                for symbol in symbols:
                    try:
                        formatted_symbol = symbol.replace('/', '')
                        ticker = await self.client.get_orderbook_ticker(symbol=formatted_symbol)
                        if ticker.get('bidPrice') and ticker.get('askPrice'):
                            self.tickers[symbol] = {
                                'bid': float(ticker['bidPrice']),
                                'ask': float(ticker['askPrice']),
                                'timestamp': int(time.time() * 1000)
                            }
                    except Exception as e:
                        logging.warning(f"Failed to fetch ticker for {symbol}: {e}")
                        continue
                
                await asyncio.sleep(1)  # Пауза между запросами
            except asyncio.CancelledError:
                logging.info("Binance polling loop cancelled.")
                break
            except Exception as e:
                logging.error(f"Error in Binance ticker loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # В случае ошибки ждем дольше

    async def connect(self, symbols: list):
        """Подключается к Binance и запускает фоновый поллинг."""
        try:
            logging.info("Testing Binance connection...")
            self.client = await AsyncClient.create(
                api_key=self.apiKey,
                api_secret=self.secret
            )
            # Проверяем соединение
            await self.client.ping()
            logging.info("Binance connection successful.")
            # Вызываем родительский метод, который запускает _fetch_tickers_loop
            await super().connect(symbols)
        except Exception as e:
            logging.error(f"Failed to connect to Binance: {e}")
            self._is_connected = False
            await self.disconnect()
            raise

    async def disconnect(self):
        """Отключается от Binance и закрывает сессию."""
        logging.info("Disconnecting from Binance...")
        await super().disconnect()  # Отменяет _polling_task
        if self.client:
            await self.client.close_connection()
            logging.info("Binance client session closed.")

    async def place_order(self, symbol: str, side: str, order_type: str, amount: float, price: float = None):
        logging.warning("place_order is a placeholder and not implemented for BinanceExchange.")
        return {'status': 'not_implemented'}
