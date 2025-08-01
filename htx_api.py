import logging
from typing import Dict, List, Optional

from huobi.client.market import MarketClient
from huobi.client.trade import TradeClient
from huobi.constant import *
from huobi.exception.huobi_api_exception import HuobiApiException

import config

class HtxApi:
    """Класс для взаимодействия с API биржи HTX (Huobi)."""

    def __init__(self, api_key: str, secret_key: str, base_url: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        # Клиенты SDK ожидают параметр 'url'
        self.market_client = MarketClient(api_key=self.api_key, secret_key=self.secret_key, url=base_url)
        self.trade_client = TradeClient(api_key=self.api_key, secret_key=self.secret_key, url=base_url)
        self.logger = logging.getLogger(__name__)

    def get_market_data(self, symbols: List[str]) -> Optional[Dict]:
        """Получает последние цены для указанных символов."""
        market_data = {}
        try:
            for symbol in symbols:
                # Используем get_market_detail для получения актуальной цены
                detail = self.market_client.get_market_detail(symbol)
                
                # Проверяем, что данные получены
                # Объект MarketDetail содержит поля 'open', 'close', 'high', 'low' напрямую
                if detail and hasattr(detail, 'close'):
                    # Используем цену последней сделки ('close') как текущую рыночную цену
                    price = detail.close
                    market_data[symbol.upper()] = {'price': float(price)}
                else:
                    self.logger.warning(f"Не удалось получить данные для символа: {symbol}")
                    return None # Если не удалось получить данные хотя бы по одному символу, выходим

            # Проверяем, что мы нашли данные для всех запрошенных символов
            if len(market_data) != len(symbols):
                self.logger.warning("Не удалось получить данные для всех запрошенных символов.")
                return None

            return market_data
        except HuobiApiException as e:
            self.logger.error(f"Ошибка API при получении рыночных данных: {e.error_message}")
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при получении рыночных данных: {e}", exc_info=True)
            return None

    def place_order(self, symbol: str, direction: str, quantity: float, order_type: str = "market") -> Optional[int]:
        """Размещает рыночный ордер."""
        try:
            if direction.upper() == 'BUY':
                order_direction = OrderSide.BUY
            elif direction.upper() == 'SELL':
                order_direction = OrderSide.SELL
            else:
                raise ValueError("Неверное направление ордера")

            if order_type.lower() == 'market':
                if order_direction == OrderSide.BUY:
                    order_type_val = OrderType.BUY_MARKET
                    # Для рыночной покупки HTX требует сумму в USDT, а не количество BTC
                    # Мы передаем сумму из config.POSITION_SIZE
                    amount = quantity 
                else:
                    order_type_val = OrderType.SELL_MARKET
                    amount = quantity # Для продажи указываем количество базовой валюты
            else:
                # Можно добавить логику для лимитных ордеров
                raise NotImplementedError("Поддерживаются только рыночные ордера")

            order_id = self.trade_client.create_order(
                symbol=symbol,
                account_id=self._get_spot_account_id(),
                order_type=order_type_val,
                amount=amount,
                price=0  # Для рыночных ордеров цена не указывается
            )
            self.logger.info(f"Ордер {direction} {quantity} {symbol} успешно размещен. ID: {order_id}")
            return order_id
        except HuobiApiException as e:
            self.logger.error(f"Ошибка API при размещении ордера: {e.error_message}")
            return None
        except Exception as e:
            self.logger.error(f"Непредвиденная ошибка при размещении ордера: {e}")
            return None

    def _get_spot_account_id(self) -> Optional[int]:
        """Получает ID спотового аккаунта."""
        try:
            from huobi.client.account import AccountClient
            account_client = AccountClient(api_key=self.api_key, secret_key=self.secret_key, url=self.base_url)
            list_obj = account_client.get_accounts()
            if list_obj and list_obj.data:
                for account in list_obj.data:
                    if account.type == "spot":
                        return account.id
            self.logger.error("Не удалось найти спотовый аккаунт.")
            return None
        except HuobiApiException as e:
            self.logger.error(f"Ошибка API при получении ID аккаунта: {e.error_message}")
            return None
