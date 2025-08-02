import logging
import re
from typing import Dict, List, Optional
import requests
import urllib
import datetime
import hmac
import hashlib
import base64

from huobi.client.market import MarketClient
from huobi.client.trade import TradeClient
from huobi.client.generic import GenericClient
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
        self.generic_client = GenericClient(api_key=self.api_key, secret_key=self.secret_key, url=base_url)
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
                    market_data[symbol.lower()] = {'price': float(price)}
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

    def get_historical_kline(self, symbol: str, period: str, size: int) -> Optional[List[Dict]]:
        """Получает исторические данные (свечи) для символа."""
        try:
            # Получаем данные о свечах (klines)
            list_obj = self.market_client.get_candlestick(symbol, period, size)
            if not list_obj:
                self.logger.warning(f"Не удалось получить исторические данные для {symbol}.")
                return None

            # Форматируем данные в более удобный вид (список словарей)
            klines = []
            for candle in list_obj:
                klines.append({
                    'timestamp': candle.id,  # 'id' в ответе API - это и есть timestamp
                    'open': candle.open,
                    'close': candle.close,
                    'high': candle.high,
                    'low': candle.low,
                    'vol': candle.vol
                })
            return klines
        except HuobiApiException as e:
            self.logger.error(f"Ошибка API при получении исторических данных для {symbol}: {e.error_message}")
            return None

    def _send_request(self, method: str, path: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Отправляет подписанный запрос к API HTX."""
        if params is None:
            params = {}

        timestamp = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        params.update({
            'AccessKeyId': self.api_key,
            'SignatureMethod': 'HmacSHA256',
            'SignatureVersion': '2',
            'Timestamp': timestamp
        })

        host = urllib.parse.urlparse(self.base_url).hostname
        if host is None:
            self.logger.error("Не удалось извлечь хост из base_url")
            return None

        sorted_params = sorted(params.items())
        encode_params = urllib.parse.urlencode(sorted_params)
        
        payload = [method, host, path, encode_params]
        payload_str = '\n'.join(payload)

        signature = hmac.new(self.secret_key.encode('utf-8'), payload_str.encode('utf-8'), hashlib.sha256).digest()
        signature_b64 = base64.b64encode(signature).decode()

        params['Signature'] = signature_b64
        
        url = f"{self.base_url}{path}?{urllib.parse.urlencode(params)}"

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('code') == 200 and data.get('data'):
                return data['data']
            else:
                self.logger.error(f"Ошибка от API: {data}")
                return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ошибка HTTP запроса: {e}")
            return None

    def get_fee_rate(self, symbol: str) -> Optional[Dict]:
        """Получает актуальную торговую комиссию для указанного символа."""
        try:
            params = {'symbols': symbol.lower()}
            fee_data_list = self._send_request('GET', '/v2/reference/transact-fee-rate', params)

            if not fee_data_list:
                self.logger.warning(f"Не удалось получить информацию о комиссиях для {symbol.upper()}.")
                return None

            fee_data = fee_data_list[0]
            return {
                'symbol': symbol,
                'maker_fee': float(fee_data['makerFeeRate']),
                'taker_fee': float(fee_data['takerFeeRate'])
            }
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при получении комиссии для {symbol}: {e}", exc_info=True)
            return None
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при получении исторических данных для {symbol}: {e}", exc_info=True)
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
