import asyncio
import logging
import ccxt.async_support as ccxt
from .base import BaseExchange

class KrakenExchange(BaseExchange):
    """Интеграция с Kraken, использующая фоновый REST API поллинг."""

    def __init__(self, apiKey, secret):
        super().__init__(apiKey, secret)
        self.client = ccxt.kraken({
            'apiKey': self.apiKey,
            'secret': self.secret,
            'enableRateLimit': True,
        })

    async def _fetch_tickers_loop(self, symbols: list):
        """Бесконечный цикл для опроса цен всех указанных символов."""
        logging.info(f"Starting Kraken REST API polling loop for {len(symbols)} symbols.")
        while self._is_connected:
            try:
                fetched_tickers = await self.client.fetch_tickers(symbols)
                now = self.client.milliseconds()
                for symbol, data in fetched_tickers.items():
                    if data.get('bid') and data.get('ask'):
                        self.tickers[symbol] = {
                            'bid': data['bid'],
                            'ask': data['ask'],
                            'timestamp': data.get('timestamp', now)
                        }
                await asyncio.sleep(1)  # Пауза между запросами
            except asyncio.CancelledError:
                logging.info("Kraken polling loop cancelled.")
                break
            except Exception as e:
                logging.error(f"Error in Kraken ticker loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # В случае ошибки ждем дольше

    async def connect(self, symbols: list):
        """Подключается к Kraken и запускает фоновый поллинг."""
        try:
            logging.info("Testing Kraken connection...")
            await self.client.fetch_time()
            logging.info("Kraken connection successful.")
            # Вызываем родительский метод, который запускает _fetch_tickers_loop
            await super().connect(symbols)
        except Exception as e:
            logging.error(f"Failed to connect to Kraken: {e}")
            self._is_connected = False
            await self.disconnect()
            raise

    async def disconnect(self):
        """Отключается от Kraken и закрывает сессию."""
        logging.info("Disconnecting from Kraken...")
        await super().disconnect()  # Отменяет _polling_task
        if self.client:
            await self.client.close()
            logging.info("Kraken client session closed.")

    async def place_order(self, symbol: str, side: str, order_type: str, amount: float, price: float = None):
        logging.warning("place_order is a placeholder and not implemented for KrakenExchange.")
        return {'status': 'not_implemented'}
