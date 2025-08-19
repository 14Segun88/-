#!/usr/bin/env python3
"""
Exchange Connector - Реальная интеграция с биржами через CCXT
Поддержка 7 бирж с реальными API и демо счетами
"""

import ccxt
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os
from dotenv import load_dotenv
import time

load_dotenv('config.env')
logger = logging.getLogger('ExchangeConnector')

@dataclass
class ExchangeConfig:
    """Конфигурация биржи"""
    exchange_id: str
    testnet: bool = False
    api_key: str = None
    api_secret: str = None
    passphrase: str = None
    demo_balance: float = 100.0  # $100 на каждой бирже
    real_fees: Dict = None

class ExchangeConnector:
    """Универсальный коннектор для всех 7 бирж"""
    
    # Реальные комиссии БЕЗ скидок (taker fees)
    REAL_FEES = {
        'mexc': {'maker': 0.002, 'taker': 0.002},      # 0.2% без скидок
        'bybit': {'maker': 0.001, 'taker': 0.001},     # 0.1% без VIP
        'huobi': {'maker': 0.002, 'taker': 0.002},     # 0.2% стандарт
        'binance': {'maker': 0.001, 'taker': 0.001},   # 0.1% без BNB
        'okx': {'maker': 0.001, 'taker': 0.0015},      # 0.1-0.15% стандарт
        'kucoin': {'maker': 0.001, 'taker': 0.001},    # 0.1% без KCS
        'kraken': {'maker': 0.0016, 'taker': 0.0026}   # 0.16-0.26% стандарт
    }
    
    # Testnet/Demo endpoints где доступны
    TESTNET_URLS = {
        'binance': {
            'apiKey': os.getenv('BINANCE_TESTNET_API_KEY', ''),
            'secret': os.getenv('BINANCE_TESTNET_API_SECRET', ''),
            'test': True,
            'options': {
                'defaultType': 'spot',
                'adjustForTimeDifference': True
            }
        },
        'bybit': {
            'apiKey': os.getenv('BYBIT_TESTNET_API_KEY', ''),
            'secret': os.getenv('BYBIT_TESTNET_API_SECRET', ''),
            'test': True,
            'urls': {
                'api': {
                    'public': 'https://api-testnet.bybit.com',
                    'private': 'https://api-testnet.bybit.com'
                }
            }
        },
        'okx': {
            'apiKey': os.getenv('OKX_DEMO_API_KEY', ''),
            'secret': os.getenv('OKX_DEMO_API_SECRET', ''),
            'passphrase': os.getenv('OKX_DEMO_PASSPHRASE', ''),
            'test': True,
            'urls': {
                'api': 'https://www.okx.com',  # OKX использует флаг x-simulated-trading
            },
            'options': {
                'defaultType': 'spot',
                'sandboxMode': True
            }
        },
        'kucoin': {
            'apiKey': os.getenv('KUCOIN_SANDBOX_API_KEY', ''),
            'secret': os.getenv('KUCOIN_SANDBOX_API_SECRET', ''),
            'passphrase': os.getenv('KUCOIN_SANDBOX_PASSPHRASE', ''),
            'test': True,
            'urls': {
                'api': {
                    'public': 'https://openapi-sandbox.kucoin.com',
                    'private': 'https://openapi-sandbox.kucoin.com'
                }
            }
        }
    }
    
    def __init__(self, mode: str = 'demo'):
        """
        Args:
            mode: 'demo' для демо счетов, 'real' для реальных
        """
        self.mode = mode
        self.exchanges = {}
        self.balances = {}
        self.orderbooks = {}
        self.is_connected = {}
        
        # Прокси настройки для заблокированных бирж
        self.proxy = None
        if os.getenv('HTTP_PROXY'):
            self.proxy = {
                'http': os.getenv('HTTP_PROXY'),
                'https': os.getenv('HTTPS_PROXY', os.getenv('HTTP_PROXY'))
            }
    
    async def initialize(self, exchange_list: List[str] = None):
        """Инициализация подключений к биржам"""
        if exchange_list is None:
            exchange_list = ['mexc', 'bybit', 'huobi', 'binance', 'okx', 'kucoin', 'kraken']
        
        logger.info(f"🚀 Инициализация {len(exchange_list)} бирж в режиме {self.mode}")
        
        for exchange_id in exchange_list:
            try:
                exchange = await self._create_exchange(exchange_id)
                if exchange:
                    self.exchanges[exchange_id] = exchange
                    self.is_connected[exchange_id] = True
                    
                    # Инициализируем демо баланс
                    if self.mode == 'demo':
                        self.balances[exchange_id] = {
                            'USDT': {'free': 100.0, 'used': 0.0, 'total': 100.0}
                        }
                    
                    logger.info(f"✅ {exchange_id.upper()} подключен")
                else:
                    self.is_connected[exchange_id] = False
                    logger.warning(f"⚠️ {exchange_id.upper()} не удалось подключить")
                    
            except Exception as e:
                self.is_connected[exchange_id] = False
                logger.error(f"❌ {exchange_id.upper()} ошибка: {e}")
    
    async def _create_exchange(self, exchange_id: str):
        """Создание экземпляра биржи через CCXT"""
        try:
            # Базовая конфигурация
            config = {
                'enableRateLimit': True,
                'rateLimit': 100,
                'timeout': 30000,
            }
            
            # Добавляем прокси если нужно
            if self.proxy and exchange_id in ['binance', 'bybit']:
                config['proxies'] = self.proxy
                config['proxy'] = self.proxy['http']
            
            # В демо режиме не требуем API ключи
            if self.mode == 'demo':
                # Используем testnet если доступен
                if exchange_id in self.TESTNET_URLS and self.TESTNET_URLS[exchange_id].get('apiKey'):
                    config.update(self.TESTNET_URLS[exchange_id])
                    logger.info(f"📝 {exchange_id.upper()} использует TESTNET режим")
                # Иначе работаем без ключей (только публичные данные)
                else:
                    logger.info(f"📊 {exchange_id.upper()} использует публичные данные (без API ключей)")
            else:
                # Реальные API ключи для реального режима
                config['apiKey'] = os.getenv(f'{exchange_id.upper()}_API_KEY', '')
                config['secret'] = os.getenv(f'{exchange_id.upper()}_API_SECRET', '')
                
                if exchange_id in ['okx', 'kucoin']:
                    config['password'] = os.getenv(f'{exchange_id.upper()}_PASSPHRASE', '')
            
            # Создаем экземпляр биржи
            exchange_class = getattr(ccxt, exchange_id)
            exchange = exchange_class(config)
            
            # Загружаем рынки
            try:
                exchange.load_markets()
            except Exception as e:
                logger.warning(f"Не удалось загрузить рынки {exchange_id}: {e}, продолжаем без них")
            
            return exchange
            
        except Exception as e:
            logger.error(f"Ошибка создания {exchange_id}: {e}")
            return None
    
    async def fetch_orderbook(self, exchange_id: str, symbol: str, limit: int = 10):
        """Получить стакан ордеров"""
        try:
            if exchange_id not in self.exchanges:
                return None
            
            # KuCoin требует limit 20 или 100
            if exchange_id == 'kucoin':
                limit = 20
            
            exchange = self.exchanges[exchange_id]
            orderbook = exchange.fetch_order_book(symbol, limit)
            
            # Сохраняем в кэш
            if exchange_id not in self.orderbooks:
                self.orderbooks[exchange_id] = {}
            self.orderbooks[exchange_id][symbol] = orderbook
            
            return orderbook
            
        except Exception as e:
            logger.error(f"Ошибка получения стакана {exchange_id} {symbol}: {e}")
            return None
    
    async def fetch_balance(self, exchange_id: str):
        """Получить реальный баланс с биржи"""
        try:
            if self.mode == 'demo':
                # В демо режиме возвращаем фиксированный баланс
                return self.balances.get(exchange_id, {
                    'USDT': {'free': 100.0, 'used': 0.0, 'total': 100.0}
                })
            
            if exchange_id not in self.exchanges:
                return None
            
            exchange = self.exchanges[exchange_id]
            balance = exchange.fetch_balance()
            
            # Сохраняем в кэш
            self.balances[exchange_id] = balance
            
            return balance
            
        except Exception as e:
            logger.error(f"Ошибка получения баланса {exchange_id}: {e}")
            return None
    
    async def create_order(self, exchange_id: str, symbol: str, side: str, 
                          amount: float, price: float = None, order_type: str = 'limit'):
        """Создать реальный ордер на бирже"""
        try:
            if exchange_id not in self.exchanges:
                logger.error(f"Биржа {exchange_id} не подключена")
                return None
            
            exchange = self.exchanges[exchange_id]
            
            # В демо режиме симулируем исполнение
            if self.mode == 'demo':
                order_id = f"DEMO_{exchange_id}_{int(time.time()*1000)}"
                
                # Обновляем демо баланс
                if exchange_id in self.balances:
                    usdt_balance = self.balances[exchange_id].get('USDT', {})
                    if side == 'buy':
                        cost = amount * price if price else amount
                        if usdt_balance['free'] >= cost:
                            usdt_balance['free'] -= cost
                            usdt_balance['used'] += cost
                    
                return {
                    'id': order_id,
                    'symbol': symbol,
                    'side': side,
                    'type': order_type,
                    'amount': amount,
                    'price': price,
                    'status': 'closed',  # Считаем что исполнился мгновенно в демо
                    'filled': amount,
                    'remaining': 0,
                    'timestamp': int(time.time() * 1000),
                    'datetime': exchange.iso8601(int(time.time() * 1000)),
                    'fee': {
                        'cost': amount * price * self.REAL_FEES[exchange_id]['taker'],
                        'currency': 'USDT'
                    }
                }
            
            # Реальный ордер
            if order_type == 'limit' and price:
                order = await exchange.create_limit_order(symbol, side, amount, price)
            else:
                order = await exchange.create_market_order(symbol, side, amount)
            
            logger.info(f"📝 Ордер создан на {exchange_id}: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания ордера {exchange_id}: {e}")
            return None
    
    async def cancel_order(self, exchange_id: str, order_id: str, symbol: str):
        """Отменить ордер"""
        try:
            if self.mode == 'demo':
                return {'id': order_id, 'status': 'canceled'}
            
            if exchange_id not in self.exchanges:
                return None
            
            exchange = self.exchanges[exchange_id]
            result = await exchange.cancel_order(order_id, symbol)
            
            logger.info(f"🚫 Ордер отменен на {exchange_id}: {order_id}")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка отмены ордера {exchange_id}: {e}")
            return None
    
    async def fetch_order_status(self, exchange_id: str, order_id: str, symbol: str):
        """Проверить статус ордера"""
        try:
            if self.mode == 'demo':
                # В демо считаем все ордера исполненными
                return {'id': order_id, 'status': 'closed', 'filled': 1.0}
            
            if exchange_id not in self.exchanges:
                return None
            
            exchange = self.exchanges[exchange_id]
            order = await exchange.fetch_order(order_id, symbol)
            
            return order
            
        except Exception as e:
            logger.error(f"Ошибка проверки статуса ордера {exchange_id}: {e}")
            return None
    
    async def fetch_ticker(self, exchange_id: str, symbol: str):
        """Получить тикер (последние цены)"""
        try:
            if exchange_id not in self.exchanges:
                return None
            
            exchange = self.exchanges[exchange_id]
            ticker = exchange.fetch_ticker(symbol)
            
            return ticker
            
        except Exception as e:
            logger.error(f"Ошибка получения тикера {exchange_id} {symbol}: {e}")
            return None
    
    async def fetch_markets(self, exchange_id: str):
        """Получить список доступных рынков"""
        try:
            if exchange_id not in self.exchanges:
                return []
            
            exchange = self.exchanges[exchange_id]
            markets = exchange.markets
            
            # Фильтруем только спотовые USDT пары
            spot_usdt_markets = []
            for market_id, market in markets.items():
                if market['spot'] and market['quote'] == 'USDT' and market['active']:
                    spot_usdt_markets.append(market['symbol'])
            
            return spot_usdt_markets
            
        except Exception as e:
            logger.error(f"Ошибка получения рынков {exchange_id}: {e}")
            return []
    
    def get_real_fee(self, exchange_id: str, side: str = 'taker'):
        """Получить реальную комиссию биржи"""
        return self.REAL_FEES.get(exchange_id, {}).get(side, 0.002)
    
    async def calculate_arbitrage(self, symbol: str, buy_exchange: str, sell_exchange: str):
        """Рассчитать реальную арбитражную возможность"""
        try:
            # Получаем стаканы с обеих бирж
            buy_orderbook = await self.fetch_orderbook(buy_exchange, symbol)
            sell_orderbook = await self.fetch_orderbook(sell_exchange, symbol)
            
            if not buy_orderbook or not sell_orderbook:
                return None
            
            # Лучшие цены
            best_ask = buy_orderbook['asks'][0][0] if buy_orderbook['asks'] else None
            best_bid = sell_orderbook['bids'][0][0] if sell_orderbook['bids'] else None
            
            if not best_ask or not best_bid:
                return None
            
            # Доступные объемы
            ask_volume = buy_orderbook['asks'][0][1] if buy_orderbook['asks'] else 0
            bid_volume = sell_orderbook['bids'][0][1] if sell_orderbook['bids'] else 0
            
            # Минимальный объем для сделки
            available_volume = min(ask_volume, bid_volume)
            
            # Проверяем что есть спред
            if best_bid <= best_ask:
                return None
            
            # Рассчитываем с РЕАЛЬНЫМИ комиссиями
            buy_fee = self.get_real_fee(buy_exchange, 'taker')
            sell_fee = self.get_real_fee(sell_exchange, 'taker')
            
            # Валовая прибыль
            gross_profit_pct = ((best_bid - best_ask) / best_ask) * 100
            
            # Чистая прибыль после комиссий
            total_fees_pct = (buy_fee + sell_fee) * 100
            net_profit_pct = gross_profit_pct - total_fees_pct
            
            # Только если есть реальная прибыль
            if net_profit_pct <= 0:
                return None
            
            return {
                'symbol': symbol,
                'buy_exchange': buy_exchange,
                'sell_exchange': sell_exchange,
                'buy_price': best_ask,
                'sell_price': best_bid,
                'available_volume': available_volume,
                'gross_profit_pct': gross_profit_pct,
                'buy_fee_pct': buy_fee * 100,
                'sell_fee_pct': sell_fee * 100,
                'total_fees_pct': total_fees_pct,
                'net_profit_pct': net_profit_pct,
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета арбитража: {e}")
            return None
    
    async def close(self):
        """Закрыть все соединения"""
        for exchange_id, exchange in self.exchanges.items():
            try:
                await exchange.close()
                logger.info(f"🔌 {exchange_id.upper()} отключен")
            except:
                pass
        self.exchanges.clear()
        self.is_connected.clear()


async def test_connector():
    """Тестирование коннектора"""
    connector = ExchangeConnector(mode='demo')
    
    # Инициализируем все 7 бирж
    await connector.initialize()
    
    # Проверяем подключения
    print("\n📊 Статус подключений:")
    for exchange_id, status in connector.is_connected.items():
        status_emoji = "✅" if status else "❌"
        print(f"{status_emoji} {exchange_id.upper()}: {'Подключен' if status else 'Отключен'}")
    
    # Тестируем получение данных
    test_symbol = 'BTC/USDT'
    print(f"\n📈 Тестирование {test_symbol}:")
    
    for exchange_id in connector.exchanges.keys():
        ticker = await connector.fetch_ticker(exchange_id, test_symbol)
        if ticker:
            print(f"{exchange_id.upper()}: Bid=${ticker.get('bid', 0):.2f}, Ask=${ticker.get('ask', 0):.2f}")
    
    # Проверяем арбитражные возможности
    print("\n🔍 Поиск арбитражных возможностей:")
    exchanges = list(connector.exchanges.keys())
    
    for i in range(len(exchanges)):
        for j in range(i+1, len(exchanges)):
            opportunity = await connector.calculate_arbitrage(
                test_symbol, exchanges[i], exchanges[j]
            )
            if opportunity:
                print(f"💰 {opportunity['buy_exchange']} → {opportunity['sell_exchange']}: "
                      f"Чистая прибыль {opportunity['net_profit_pct']:.3f}% "
                      f"(комиссии {opportunity['total_fees_pct']:.2f}%)")
    
    await connector.close()


if __name__ == "__main__":
    asyncio.run(test_connector())
