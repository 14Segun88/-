#!/usr/bin/env python3
"""
💰 TRADING ENGINE
Движок для исполнения арбитражных сделок
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import hmac
import hashlib
import base64
import json
import uuid
from decimal import Decimal, ROUND_DOWN
from collections import defaultdict
import ccxt
from datetime import datetime, timezone

from production_config import (
    API_KEYS, EXCHANGES_CONFIG, TRADING_CONFIG, 
    RISK_MANAGEMENT, POSITION_SIZING
)

logger = logging.getLogger('TradingEngine')

class OrderStatus(Enum):
    """Статус ордера"""
    PENDING = "pending"
    PLACED = "placed"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"

class OrderType(Enum):
    """Тип ордера"""
    MARKET = "market"
    LIMIT = "limit"
    LIMIT_MAKER = "limit_maker"

@dataclass
class Order:
    """Ордер"""
    id: str
    exchange: str
    symbol: str
    side: str  # buy/sell
    type: OrderType
    price: float
    amount: float
    status: OrderStatus = OrderStatus.PENDING
    filled_amount: float = 0
    filled_price: float = 0
    commission: float = 0
    timestamp: float = field(default_factory=time.time)
    exchange_order_id: Optional[str] = None
    
    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED
    
    @property
    def is_active(self) -> bool:
        return self.status in [OrderStatus.PENDING, OrderStatus.PLACED, OrderStatus.PARTIALLY_FILLED]
    
    @property
    def fill_ratio(self) -> float:
        return self.filled_amount / self.amount if self.amount > 0 else 0

@dataclass
class ArbitrageOpportunity:
    """Арбитражная возможность"""
    type: str  # 'inter_exchange' или 'triangular'
    path: List[str]  # Путь сделки
    exchanges: List[str]
    symbols: List[str]
    prices: Dict[str, float]
    volumes: Dict[str, float]
    expected_profit_pct: float
    expected_profit_usd: float
    min_volume: float
    timestamp: float = field(default_factory=time.time)
    
    @property
    def age(self) -> float:
        return time.time() - self.timestamp
    
    @property
    def is_fresh(self) -> bool:
        return self.age < TRADING_CONFIG['max_opportunity_age']

class TradingEngine:
    """Торговый движок"""
    
    def __init__(self):
        self.orders = {}
        self.active_positions = {}
        self.balance = defaultdict(lambda: defaultdict(float))
        self.trade_history = []
        self.session_stats = {
            'trades': 0,
            'successful': 0,
            'failed': 0,
            'total_profit_usd': 0,
            'total_profit_pct': 0,
            'total_volume': 0,
            'start_time': time.time()
        }
        self.exchange_clients = {}
        self.running = False
        
    async def start(self):
        """Запуск торгового движка"""
        self.running = True
        logger.info("🚀 Запуск торгового движка")
        
        # Инициализация клиентов бирж
        await self._init_exchange_clients()
        
        # Загрузка балансов
        await self.update_balances()
        
        # Запуск фоновых задач
        asyncio.create_task(self._monitor_orders())
        asyncio.create_task(self._risk_monitor())
        
    async def stop(self):
        """Остановка движка"""
        logger.info("Остановка торгового движка...")
        self.running = False
        
        # Отмена активных ордеров
        for order_id, order in self.orders.items():
            if order.is_active:
                await self.cancel_order(order)
        
        # Сохранение статистики
        self._save_session_stats()
    
    async def _init_exchange_clients(self):
        """Инициализация клиентов для бирж"""
        for exchange_id, config in EXCHANGES_CONFIG.items():
            if not config['enabled']:
                continue
            
            # Проверяем наличие ключей в API_KEYS
            if exchange_id not in API_KEYS:
                logger.warning(f"⚠️ Нет API ключей для {config['name']}")
                continue
                
            if API_KEYS[exchange_id]['apiKey']:
                logger.info(f"Инициализация клиента {config['name']}")
                # Базовые данные клиента
                client_data = {
                    'name': config['name'],
                    'api_key': API_KEYS[exchange_id]['apiKey'],
                    'secret': API_KEYS[exchange_id]['secret']
                }
                # Добавляем passphrase для бирж, которые его требуют
                if exchange_id in ['bitget', 'okx', 'kucoin'] and 'passphrase' in API_KEYS[exchange_id]:
                    client_data['passphrase'] = API_KEYS[exchange_id]['passphrase']
                
                # 🎯 Передаем флаги из конфигурации API_KEYS
                if 'demo_trading' in API_KEYS[exchange_id]:
                    client_data['demo_trading'] = API_KEYS[exchange_id]['demo_trading']
                if 'env' in API_KEYS[exchange_id]:
                    client_data['env'] = API_KEYS[exchange_id]['env']

                # Инициализация ccxt клиента для real/demo режимов
                ccxt_client = None
                try:
                    if TRADING_CONFIG['mode'] in ['real', 'demo']:
                        if hasattr(ccxt, exchange_id):
                            params = {
                                'apiKey': client_data['api_key'],
                                'secret': client_data['secret'],
                                'enableRateLimit': True,
                            }
                            # OKX/Bitget требуют passphrase/password
                            if exchange_id in ['okx', 'bitget', 'kucoin'] and 'passphrase' in client_data:
                                params['password'] = client_data['passphrase']
                                params['passphrase'] = client_data['passphrase']
                            ccxt_client = getattr(ccxt, exchange_id)(params)

                            # Настройки spot по умолчанию
                            if hasattr(ccxt_client, 'options'):
                                ccxt_client.options = {**getattr(ccxt_client, 'options', {}), 'defaultType': 'spot'}

                            # Включаем sandbox/testnet в demo-режиме
                            if TRADING_CONFIG['mode'] == 'demo':
                                # Внимание: у OKX/Bitget/Phemex демо-режим активируется заголовками,
                                # а публичные REST/markets берутся с production URL. Переключение
                                # sandbox в ccxt меняет базовый URL и ломает load_markets
                                # (ошибки вида 40404/"NoneType" + str). Поэтому здесь sandbox отключаем.
                                if hasattr(ccxt_client, 'set_sandbox_mode'):
                                    try:
                                        if exchange_id in ['okx', 'bitget', 'phemex']:
                                            ccxt_client.set_sandbox_mode(False)
                                        else:
                                            ccxt_client.set_sandbox_mode(True)
                                    except Exception:
                                        pass
                                # Настройка для реальной торговли (без demo заголовков)
                                if exchange_id == 'okx':
                                    headers = getattr(ccxt_client, 'headers', {}) or {}
                                    # Убираем x-simulated-trading для реальной торговли
                                    headers.pop('x-simulated-trading', None)
                                    ccxt_client.headers = headers
                                    logger.info("OKX настроен для реальной торговли")
                                if exchange_id == 'bitget':
                                    try:
                                        headers = getattr(ccxt_client, 'headers', {}) or {}
                                        # Убираем PAPTRADING для реальной торговли
                                        headers.pop('PAPTRADING', None)
                                        ccxt_client.headers = headers
                                        logger.info("Bitget настроен для реальной торговли")
                                    except Exception:
                                        pass
                                # Phemex настройка для реального режима  
                                if exchange_id == 'phemex':
                                    try:
                                        # Отключаем sandbox для реальной торговли
                                        ccxt_client.set_sandbox_mode(False)
                                        logger.info("Phemex настроен для реальной торговли (sandbox отключен)")
                                        # Отключить любые прокси на уровне клиента requests
                                        if hasattr(ccxt_client, 'proxies'):
                                            ccxt_client.proxies = {'http': None, 'https': None}
                                        # На всякий случай отключить generic proxy поле
                                        if hasattr(ccxt_client, 'proxy'):
                                            ccxt_client.proxy = None
                                        logger.info("Phemex demo: прокси отключены для клиента ccxt")
                                    except Exception:
                                        pass
                            # Предзагрузка рынков для стабильной работы create_order
                            try:
                                loop = asyncio.get_running_loop()
                                await loop.run_in_executor(None, ccxt_client.load_markets)
                                try:
                                    markets_count = len(getattr(ccxt_client, 'markets', {}) or {})
                                except Exception:
                                    markets_count = 0
                                logger.info(f"{exchange_id.upper()} markets loaded: {markets_count}")
                            except Exception as e:
                                logger.warning(f"⚠️ Не удалось load_markets для {exchange_id}: {e}")
                        else:
                            logger.debug(f"ccxt не поддерживает {exchange_id}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось инициализировать ccxt для {exchange_id}: {e}")

                client_data['ccxt'] = ccxt_client
                self.exchange_clients[exchange_id] = client_data
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Исполнить арбитражную сделку"""
        try:
            logger.info(f"🎯 Исполнение арбитража: {opportunity.type}")
            
            # Проверка риск-менеджмента
            if not await self._check_risk_limits(opportunity):
                logger.warning("❌ Отклонено риск-менеджментом")
                return False
            
            # Расчет размера позиции
            position_size = self._calculate_position_size(opportunity)
            if position_size < POSITION_SIZING['min_position_usd']:
                logger.warning(f"❌ Размер позиции слишком мал: ${position_size:.2f}")
                return False
            
            # Исполнение в зависимости от типа
            if opportunity.type == 'inter_exchange':
                return await self._execute_inter_exchange(opportunity, position_size)
            elif opportunity.type == 'triangular':
                return await self._execute_triangular(opportunity, position_size)
            else:
                logger.error(f"Неизвестный тип арбитража: {opportunity.type}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка исполнения арбитража: {e}")
            return False
    
    async def _execute_inter_exchange(
        self, 
        opportunity: ArbitrageOpportunity, 
        position_size: float
    ) -> bool:
        """Исполнить межбиржевой арбитраж"""
        try:
            buy_exchange = opportunity.exchanges[0]
            sell_exchange = opportunity.exchanges[1]
            symbol = opportunity.symbols[0]
            
            # В paper режиме опираемся на REST данные, а не на CCXT markets
            if TRADING_CONFIG.get('mode') == 'real':
                # Только в реальном режиме проверяем CCXT markets
                try:
                    p_buy, m_buy, s_buy = self._ccxt_presence(buy_exchange, symbol)
                    p_sell, m_sell, s_sell = self._ccxt_presence(sell_exchange, symbol)
                    if not (p_buy and p_sell):
                        logger.info(
                            f"⏭️ Пропуск: {symbol} отсутствует по CCXT "
                            f"[{buy_exchange}: present={p_buy}, markets={m_buy}, symbols={s_buy}; "
                            f"{sell_exchange}: present={p_sell}, markets={m_sell}, symbols={s_sell}]"
                        )
                        return False
                except Exception:
                    # Не блокируем поток, если проверка не удалась
                    pass
            
            # Расчет объема
            buy_price = opportunity.prices[f'{buy_exchange}_ask']
            sell_price = opportunity.prices[f'{sell_exchange}_bid']
            amount = position_size / buy_price
            
            logger.info(
                f"📊 Межбиржевой арбитраж {symbol}: "
                f"Покупка на {buy_exchange} @ ${buy_price:.4f}, "
                f"Продажа на {sell_exchange} @ ${sell_price:.4f}, "
                f"Объем: {amount:.4f}"
            )
            
            # Параллельное размещение ордеров
            if TRADING_CONFIG['mode'] in ['real', 'demo']:
                # В demo разрешаем только поддерживаемые биржи
                if TRADING_CONFIG['mode'] == 'demo':
                    allowed = set(TRADING_CONFIG.get('demo_supported_exchanges', []))
                    if not all(ex in allowed for ex in [buy_exchange, sell_exchange]):
                        logger.info("⏭️ Пропуск: связка не поддерживается в demo/testnet")
                        return False
                buy_task = self._place_order(
                    buy_exchange, symbol, 'buy', amount, buy_price
                )
                sell_task = self._place_order(
                    sell_exchange, symbol, 'sell', amount, sell_price
                )
                
                buy_order, sell_order = await asyncio.gather(
                    buy_task, sell_task, return_exceptions=True
                )
                
                # Проверка успешности
                if isinstance(buy_order, Exception) or isinstance(sell_order, Exception):
                    logger.error("❌ Ошибка размещения ордеров")
                    # Отмена успешных ордеров
                    if not isinstance(buy_order, Exception):
                        await self.cancel_order(buy_order)
                    if not isinstance(sell_order, Exception):
                        await self.cancel_order(sell_order)
                    return False
                
                # Дополнительная проверка статусов FAILED
                if buy_order.status == OrderStatus.FAILED or sell_order.status == OrderStatus.FAILED:
                    logger.error("❌ Один из ордеров отклонен биржей (FAILED)")
                    if hasattr(buy_order, 'is_active') and buy_order.is_active:
                        await self.cancel_order(buy_order)
                    if hasattr(sell_order, 'is_active') and sell_order.is_active:
                        await self.cancel_order(sell_order)
                    return False
                
                # Ожидание исполнения
                filled = await self._wait_for_fills([buy_order, sell_order])
                
                if filled:
                    # Расчет прибыли
                    profit = self._calculate_realized_profit(buy_order, sell_order)
                    # Лог успешной реальной сделки в историю для метрик
                    try:
                        revenue = sell_order.filled_amount * sell_order.filled_price
                        cost = buy_order.filled_amount * buy_order.filled_price
                        trade = {
                            'timestamp': time.time(),
                            'type': opportunity.type,
                            'exchanges': [buy_exchange, sell_exchange],
                            'symbols': [symbol],
                            'position_size': position_size,
                            'gross_profit': revenue - cost,
                            'net_profit': profit,
                            'profit_pct': (profit / position_size * 100) if position_size > 0 else 0
                        }
                        self.trade_history.append(trade)
                    except Exception:
                        # История — вспомогательная, не должна ломать основной поток
                        pass
                    self._update_stats(profit, position_size)
                    logger.info(f"✅ Арбитраж успешен! Прибыль: ${profit:.2f}")
                    return True
                else:
                    logger.warning("⚠️ Ордера не исполнены полностью")
                    return False
                    
            else:  # paper или demo режим
                # Симуляция исполнения - используем правильные комиссии
                buy_fee_rate = EXCHANGES_CONFIG[buy_exchange].get('fee', 0.001)
                sell_fee_rate = EXCHANGES_CONFIG[sell_exchange].get('fee', 0.001)
                commission_buy = position_size * buy_fee_rate
                commission_sell = position_size * sell_fee_rate
                
                gross_profit = (sell_price - buy_price) * amount
                net_profit = gross_profit - commission_buy - commission_sell
                
                self._log_paper_trade(
                    opportunity, position_size, gross_profit, net_profit
                )
                
                logger.info(
                    f"📝 [PAPER] Арбитраж: Прибыль ${net_profit:.2f} "
                    f"({net_profit/position_size*100:.3f}%)"
                )
                return True
                
        except Exception as e:
            logger.error(f"❌ Ошибка межбиржевого арбитража: {e}")
            return False

    def _ccxt_presence(self, exchange: str, symbol: str) -> Tuple[bool, int, int]:
        """Проверка наличия символа по данным ccxt: возвращает (present, markets_count, symbols_count)."""
        try:
            info = self.exchange_clients.get(exchange, {}) if isinstance(self.exchange_clients, dict) else {}
            ccxt_client = info.get('ccxt') if isinstance(info, dict) else None
            if not ccxt_client:
                return False, 0, 0
            try:
                markets = getattr(ccxt_client, 'markets', {}) or {}
                mkt_count = len(markets)
            except Exception:
                markets = {}
                mkt_count = 0
            try:
                symbols = getattr(ccxt_client, 'symbols', []) or list(markets.keys())
            except Exception:
                symbols = list(markets.keys())
            sym_set = set(symbols) if isinstance(symbols, (list, set)) else set()
            present = (symbol in sym_set) or (symbol in markets)
            return present, mkt_count, len(sym_set)
        except Exception:
            return False, 0, 0
    
    async def _execute_triangular(
        self, 
        opportunity: ArbitrageOpportunity,
        position_size: float
    ) -> bool:
        """Исполнить треугольный арбитраж"""
        try:
            exchange = opportunity.exchanges[0]
            path = opportunity.path
            
            logger.info(
                f"📊 Треугольный арбитраж на {exchange}: "
                f"Путь {' -> '.join(path)}"
            )
            
            # TODO: Реализовать треугольный арбитраж
            # Это требует последовательного исполнения 3 сделок
            
            logger.warning("⚠️ Треугольный арбитраж пока не реализован")
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка треугольного арбитража: {e}")
            return False
    
    async def _place_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None
    ) -> Order:
        """Разместить ордер на бирже"""
        order = Order(
            id=f"{exchange}_{symbol}_{side}_{time.time()}",
            exchange=exchange,
            symbol=symbol,
            side=side,
            type=OrderType.LIMIT if price else OrderType.MARKET,
            price=price or 0,
            amount=amount
        )
        
        try:
            # Если есть ccxt клиент — используем его (для demo/real)
            client_info = self.exchange_clients.get(exchange, {})
            ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None

            # 🔄 ПРИНУДИТЕЛЬНО используем REST для Bitget demo режима (CCXT не передает PAPTRADING)
            demo_trading = client_info.get('demo_trading', False)
            if ccxt_client and not (exchange == 'bitget' and demo_trading):
                # Базовые параметры ордера
                params = {}
                # Биржеспецифичные параметры для стабильности DEMO/REAL
                ex = (exchange or '').lower()
                # IOC/FOK
                use_ioc = bool(TRADING_CONFIG.get('use_ioc', False))
                if ex == 'bitget':
                    # Для spot требуется указать тип принудительного исполнения
                    params.update({'force': 'ioc' if use_ioc else 'normal'})
                else:
                    # Только для известных бирж, где ccxt поддерживает timeInForce
                    if use_ioc and ex in {'binance', 'bybit', 'mexc', 'kucoin', 'gate', 'phemex', 'okx'}:
                        params.update({'timeInForce': 'IOC'})
                ccxt_type = 'limit' if order.type == OrderType.LIMIT else 'market'

                # Округление количества/цены согласно точности/лимитам рынка
                s_amount, s_price = self._sanitize_amount_price(exchange, ccxt_client, symbol, amount, price)
                try:
                    # Диагностика параметров перед отправкой
                    logger.debug({
                        'action': 'ccxt_create_order',
                        'exchange': exchange,
                        'symbol': symbol,
                        'side': side,
                        'type': ccxt_type,
                        'amount': s_amount,
                        'price': s_price,
                        'params': params
                    })
                    created = await self._ccxt_create_order(ccxt_client, symbol, ccxt_type, side, s_amount, s_price, params)
                    order.exchange_order_id = str(created.get('id') or created.get('orderId') or created.get('clientOrderId') or '')
                    order.status = OrderStatus.PLACED
                    logger.info(f"✅ {exchange.upper()} ордер размещен (ccxt): {order.exchange_order_id}")
                except Exception as e:
                    # Диагностика заголовков для DEMO режимов OKX/Bitget
                    try:
                        headers_dbg = getattr(ccxt_client, 'headers', {})
                    except Exception:
                        headers_dbg = {}
                    err_msg = str(e)
                    logger.error(f"❌ Ошибка размещения ордера через ccxt [{exchange}]: {err_msg}")
                    logger.info(f"Headers[{exchange}]: {headers_dbg}")
                    # Фолбек для Bitget v2 DEMO: прямой REST при 40404 Request URL NOT FOUND
                    if ex == 'bitget' and ('40404' in err_msg or 'Request URL NOT FOUND' in err_msg):
                        try:
                            created = await self._bitget_place_order_rest(client_info, symbol, ccxt_type, side, s_amount, s_price)
                            order.exchange_order_id = str(created.get('orderId') or created.get('id') or created.get('clientOrderId') or '')
                            order.status = OrderStatus.PLACED
                            logger.info(f"✅ {exchange.upper()} ордер размещен (REST v2): {order.exchange_order_id}")
                        except Exception as re:
                            logger.error(f"❌ Bitget REST v2 фолбек неудачен: {re}")
                            order.status = OrderStatus.FAILED
                    # Фолбек для OKX в DEMO при нетиповой ошибке ccxt (например, NoneType + str)
                    elif ex == 'okx' and ('NoneType' in err_msg or 'unsupported operand type' in err_msg):
                        try:
                            created = await self._okx_place_order_rest(client_info, symbol, ccxt_type, side, s_amount, s_price)
                            order.exchange_order_id = str(created.get('ordId') or created.get('orderId') or created.get('id') or '')
                            order.status = OrderStatus.PLACED
                            logger.info(f"✅ {exchange.upper()} ордер размещен (REST v5): {order.exchange_order_id}")
                        except Exception as re:
                            logger.error(f"❌ OKX REST v5 фолбек неудачен: {re}")
                            order.status = OrderStatus.FAILED
                    else:
                        order.status = OrderStatus.FAILED
            else:
                # Fallback: нативные реализации
                if exchange == 'mexc':
                    await self._place_mexc_order(order)
                elif exchange == 'bitget':
                    # Используем прямой REST API для Bitget
                    created = await self._bitget_place_order_rest(client_info, symbol, 'limit' if price else 'market', side, amount, price)
                    order.exchange_order_id = str(created.get('orderId') or created.get('id') or '')
                    order.status = OrderStatus.PLACED
                    logger.info(f"✅ {exchange.upper()} ордер размещен (REST): {order.exchange_order_id}")
                elif exchange == 'phemex':
                    await self._place_phemex_order(order)
                elif exchange == 'bybit':
                    await self._place_bybit_order(order)
                elif exchange == 'huobi':
                    await self._place_huobi_order(order)
                else:
                    logger.warning(f"⚠️ Биржа {exchange} не поддерживается для нативного размещения")
                    order.status = OrderStatus.FAILED
            
            self.orders[order.id] = order
            return order
            
        except Exception as e:
            logger.error(f"❌ Ошибка размещения ордера: {e}")
            order.status = OrderStatus.FAILED
            self.orders[order.id] = order
            raise

    async def _ccxt_create_order(self, client, symbol, type_, side, amount, price=None, params=None, timeout: float = 12.0):
        """Асинхронная обертка для ccxt createOrder (через thread executor) с таймаутом"""
        loop = asyncio.get_running_loop()
        params = params or {}
        fut = loop.run_in_executor(
            None,
            lambda: client.create_order(symbol, type_, side, amount, price, params)
        )
        return await asyncio.wait_for(fut, timeout=timeout)

    def _format_number(self, value) -> str:
        """Безэкспоненциальное строковое представление числа для REST-параметров."""
        try:
            # Используем 16 знаков после запятой, затем обрезаем лишние нули и точку
            s = f"{float(value):.16f}"
            s = s.rstrip('0').rstrip('.')
            return s if s != '' else '0'
        except Exception:
            return str(value)

    def _sanitize_amount_price(
        self,
        exchange: str,
        ccxt_client,
        symbol: str,
        amount: float,
        price: Optional[float]
    ) -> Tuple[float, Optional[float]]:
        """Округление объема/цены по точности биржи и мягкая валидация min-лимитов.

        - Использует ccxt amount_to_precision/price_to_precision, если доступны.
        - Падает вниз (ROUND_DOWN) по количеству знаков при отсутствии хелперов.
        - Не повышает значения до min-лимитов (чтобы не рисковать размером позиции),
          но пишет диагностику, если значения ниже min.
        """
        try:
            market = None
            if ccxt_client:
                try:
                    market = ccxt_client.market(symbol)
                except Exception:
                    try:
                        market = (getattr(ccxt_client, 'markets', {}) or {}).get(symbol, {})
                    except Exception:
                        market = None

            amt = amount
            prc = price

            # Количество
            try:
                if ccxt_client and hasattr(ccxt_client, 'amount_to_precision'):
                    amt = float(ccxt_client.amount_to_precision(symbol, amount))
                else:
                    prec = None
                    if isinstance(market, dict):
                        prec = (market.get('precision') or {}).get('amount')
                    if isinstance(prec, int) and prec >= 0:
                        q = Decimal(str(amount)).quantize(Decimal('1e-' + str(prec)), rounding=ROUND_DOWN)
                        amt = float(q)
            except Exception:
                pass

            # Цена
            if price is not None:
                try:
                    if ccxt_client and hasattr(ccxt_client, 'price_to_precision'):
                        prc = float(ccxt_client.price_to_precision(symbol, price))
                    else:
                        pprec = None
                        if isinstance(market, dict):
                            pprec = (market.get('precision') or {}).get('price')
                        if isinstance(pprec, int) and pprec >= 0:
                            q = Decimal(str(price)).quantize(Decimal('1e-' + str(pprec)), rounding=ROUND_DOWN)
                            prc = float(q)
                except Exception:
                    pass

            # Диагностика min-лимитов
            try:
                if isinstance(market, dict):
                    limits = market.get('limits') or {}
                    a_limits = limits.get('amount') or {}
                    c_limits = limits.get('cost') or {}
                    min_amt = a_limits.get('min')
                    min_cost = c_limits.get('min')
                    warn_msgs = []
                    if min_amt is not None and amt < float(min_amt):
                        warn_msgs.append(f"amount {amt} < min {min_amt}")
                    if prc is not None and min_cost is not None and (amt * prc) < float(min_cost):
                        warn_msgs.append(f"notional {amt * prc:.8f} < min_notional {min_cost}")
                    if warn_msgs:
                        logger.debug(f"[{exchange.upper()}] Limits warn for {symbol}: " + "; ".join(warn_msgs))
            except Exception:
                pass

            logger.debug(f"Sanitized[{exchange}] {symbol}: amount {amount} -> {amt}; price {price} -> {prc}")
            return amt, prc
        except Exception as e:
            logger.debug(f"Sanitize failed [{exchange} {symbol}]: {e}")
            return amount, price

    async def _bitget_place_order_rest(self, client_info, symbol, type_, side, amount, price=None):
        """Фолбек размещения ордера на Bitget через прямой REST v2 со включённым DEMO (PAPTRADING: 1)."""
        api_key = client_info.get('api_key', '')
        secret = client_info.get('secret', '')
        passphrase = client_info.get('passphrase', '')
        if not api_key or not secret:
            raise Exception('Нет API ключей для Bitget')

        # Нормализация символа для Bitget SPOT v2: простой формат без суффикса
        # Пример: "CORE/USDT" -> "COREUSDT"
        base_quote = symbol.replace('/', '').replace(':', '').replace('_', '')
        symbol_id = base_quote.upper()

        base = 'https://api.bitget.com'
        path = '/api/v2/spot/trade/place-order'
        url = f"{base}{path}"
        # Санитизация количества/цены по точности рынков ccxt
        ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None
        s_amount, s_price = self._sanitize_amount_price('bitget', ccxt_client, symbol, amount, price)
        fmt_qty = self._format_number(s_amount)
        fmt_px = self._format_number(s_price) if (type_ == 'limit' and s_price is not None) else None
        # IOC по флагу конфигурации
        use_ioc = bool(TRADING_CONFIG.get('use_ioc', False))
        payload = {
            'symbol': symbol_id,
            'side': side,
            'orderType': 'limit' if type_ == 'limit' else 'market',
            'force': 'ioc' if use_ioc else 'normal',
            'quantity': fmt_qty,
        }
        if type_ == 'limit' and fmt_px is not None:
            payload['price'] = fmt_px
        # Рекомендуется указывать clientOid для идемпотентности
        payload['clientOid'] = str(uuid.uuid4())
        logger.debug({
            'action': 'bitget_rest_place_order',
            'symbol': symbol,
            'symbol_id': symbol_id,
            'side': side,
            'type': type_,
            'quantity_raw': amount,
            'price_raw': price,
            'quantity_sanitized': s_amount,
            'price_sanitized': s_price,
            'payload': payload,
        })

        ts = str(int(time.time() * 1000))
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        prehash = f"{ts}POST{path}{body}"
        sign = base64.b64encode(hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()

        headers = {
            'ACCESS-KEY': api_key,
            'ACCESS-SIGN': sign,
            'ACCESS-TIMESTAMP': ts,
            'ACCESS-PASSPHRASE': passphrase,
            'Content-Type': 'application/json',
        }
        
        # Добавляем заголовок для демо торговли если настроен demo режим
        if client_info.get('demo_trading', False) or client_info.get('env') == 'demo':
            headers['PAPTRADING'] = '1'
            logger.info("🎯 Bitget DEMO режим активирован (PAPTRADING: 1)")
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=body, headers=headers) as resp:
                txt = await resp.text()
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {txt[:200]}")
                try:
                    data = json.loads(txt)
                except Exception:
                    raise Exception(f"Невалидный ответ Bitget: {txt[:200]}")
                code = str(data.get('code') or '')
                if code == '00000':
                    # data may contain { "data": { "orderId": "..." } }
                    d = data.get('data') or {}
                    if isinstance(d, dict):
                        d.setdefault('id', d.get('orderId'))
                    return d
                raise Exception(f"Bitget error {code}: {txt[:200]}")

    async def _okx_place_order_rest(self, client_info, symbol, type_, side, amount, price=None):
        """Фолбек размещения ордера на OKX через прямой REST v5 (демо поддерживается через x-simulated-trading)."""
        api_key = client_info.get('api_key', '')
        secret = client_info.get('secret', '')
        passphrase = client_info.get('passphrase', '')
        if not api_key or not secret or not passphrase:
            raise Exception('Нет API ключей/пароля (passphrase) для OKX')

        # instId для OKX: "BASE-QUOTE" (например, VELO-USDT)
        inst_id = symbol.replace('/', '-').upper()

        base = 'https://www.okx.com'
        path = '/api/v5/trade/order'
        url = f"{base}{path}"
        # Санитизация количества/цены по данным рынков ccxt
        ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None
        s_amount, s_price = self._sanitize_amount_price('okx', ccxt_client, symbol, amount, price)
        fmt_sz = self._format_number(s_amount)
        fmt_px = self._format_number(s_price) if (type_ == 'limit' and s_price is not None) else None
        # Применяем IOC для OKX через ordType = 'ioc' (для лимитных ордеров)
        use_ioc = bool(TRADING_CONFIG.get('use_ioc', False))
        ord_type = 'market' if type_ == 'market' else ('ioc' if use_ioc else 'limit')
        payload = {
            'instId': inst_id,
            'tdMode': 'cash',
            'side': side,
            'ordType': ord_type,
            'sz': fmt_sz,
        }
        if type_ == 'limit' and fmt_px is not None:
            payload['px'] = fmt_px
        logger.debug({
            'action': 'okx_rest_place_order',
            'symbol': symbol,
            'instId': inst_id,
            'side': side,
            'type': type_,
            'ordType': ord_type,
            'sz_raw': amount,
            'px_raw': price,
            'sz_sanitized': s_amount,
            'px_sanitized': s_price,
            'payload': payload,
        })

        # OKX требует ISO8601 UTC с миллисекундами, тот же ts используется в подписи и заголовке
        ts = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        body = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
        prehash = f"{ts}POST{path}{body}"
        sign = base64.b64encode(hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()

        headers = {
            'OK-ACCESS-KEY': api_key,
            'OK-ACCESS-SIGN': sign,
            'OK-ACCESS-TIMESTAMP': ts,
            'OK-ACCESS-PASSPHRASE': passphrase,
            'x-simulated-trading': '0',  # Реальная торговля
            'Content-Type': 'application/json',
        }

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=body, headers=headers) as resp:
                txt = await resp.text()
                if resp.status != 200:
                    raise Exception(f"HTTP {resp.status}: {txt[:200]}")
                try:
                    data = json.loads(txt)
                except Exception:
                    raise Exception(f"Невалидный ответ OKX: {txt[:200]}")
                code = str(data.get('code') or '')
                if code == '0':
                    d = (data.get('data') or [{}])[0]
                    return d
                raise Exception(f"OKX error {code}: {txt[:200]}")
    
    async def _place_mexc_order(self, order: Order):
        """Разместить ордер на MEXC"""
        try:
            client = self.exchange_clients.get('mexc')
            if not client:
                raise Exception("MEXC клиент не инициализирован")
            
            # Подготовка параметров
            params = {
                'symbol': order.symbol.replace('/', ''),
                'side': order.side.upper(),
                'type': 'LIMIT' if order.type == OrderType.LIMIT else 'MARKET',
                'quantity': str(order.amount),
                'timestamp': int(time.time() * 1000)
            }
            
            if order.type == OrderType.LIMIT:
                params['price'] = str(order.price)
            
            # Подпись запроса
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = hmac.new(
                client['secret'].encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            params['signature'] = signature
            
            # Отправка запроса
            url = f"{EXCHANGES_CONFIG['mexc']['rest_url']}/api/v3/order"
            headers = {'X-MEXC-APIKEY': client['api_key']}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        order.exchange_order_id = str(data['orderId'])
                        order.status = OrderStatus.PLACED
                        logger.info(f"✅ MEXC ордер размещен: {order.exchange_order_id}")
                    else:
                        error = await resp.text()
                        raise Exception(f"MEXC API error: {error}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка MEXC ордера: {e}")
            order.status = OrderStatus.FAILED
            raise
    
    async def _place_bybit_order(self, order: Order):
        """Разместить ордер на Bybit через REST API"""
        try:
            client_info = self.exchange_clients.get('bybit', {})
            api_key = client_info.get('api_key', '')
            secret = client_info.get('secret', '')
            
            if not api_key or not secret:
                raise Exception("API ключи Bybit не настроены")
            
            # Подготовка параметров
            timestamp = str(int(time.time() * 1000))
            symbol = order.symbol.replace('/', '')
            
            params = {
                'category': 'spot',
                'symbol': symbol,
                'side': order.side.capitalize(),
                'orderType': 'Limit' if order.type == OrderType.LIMIT else 'Market',
                'qty': str(order.amount)
            }
            
            if order.type == OrderType.LIMIT:
                params['price'] = str(order.price)
            
            # Подпись запроса
            query_string = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
            param_str = timestamp + api_key + '5000' + query_string
            signature = hmac.new(secret.encode('utf-8'), param_str.encode('utf-8'), hashlib.sha256).hexdigest()
            
            # Заголовки
            headers = {
                'X-BAPI-API-KEY': api_key,
                'X-BAPI-SIGN': signature,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-RECV-WINDOW': '5000',
                'Content-Type': 'application/json'
            }
            
            # Отправка запроса
            url = f"{EXCHANGES_CONFIG['bybit']['rest_url']}/v5/order/create"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=params, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('retCode') == 0:
                            result = data.get('result', {})
                            order.exchange_order_id = str(result.get('orderId', ''))
                            order.status = OrderStatus.PLACED
                            logger.info(f"✅ Bybit ордер размещен: {order.exchange_order_id}")
                        else:
                            raise Exception(f"Bybit API error: {data}")
                    else:
                        error = await resp.text()
                        raise Exception(f"Bybit HTTP error {resp.status}: {error}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка Bybit ордера: {e}")
            order.status = OrderStatus.FAILED
            raise
    
    async def _place_phemex_order(self, order: Order):
        """Разместить ордер на Phemex через REST API"""
        try:
            client_info = self.exchange_clients.get('phemex', {})
            api_key = client_info.get('api_key', '')
            secret = client_info.get('secret', '')
            
            if not api_key or not secret:
                raise Exception("API ключи Phemex не настроены")
            
            # Phemex использует цены в масштабированном формате
            symbol = order.symbol.replace('/', '')
            price_scale = 10000 if 'BTC' in symbol else 100000000  # BTC: 4 знака, остальные: 8
            qty_scale = 1000000  # Количество в микроединицах
            
            params = {
                'symbol': symbol,
                'clOrdID': str(uuid.uuid4()),
                'side': order.side.capitalize(),
                'priceEp': int(order.price * price_scale) if order.type == OrderType.LIMIT else 0,
                'orderQtyEv': int(order.amount * qty_scale),
                'ordType': 'Limit' if order.type == OrderType.LIMIT else 'Market',
                'timeInForce': 'GoodTillCancel'
            }
            
            # Подпись запроса
            timestamp = str(int(time.time()))
            body = json.dumps(params, separators=(',', ':'))
            message = f"POST/orders{timestamp}{body}"
            signature = hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
            
            # Заголовки
            headers = {
                'x-phemex-access-token': api_key,
                'x-phemex-request-signature': signature,
                'x-phemex-request-timestamp': timestamp,
                'Content-Type': 'application/json'
            }
            
            # Отправка запроса
            url = f"{EXCHANGES_CONFIG['phemex']['rest_url']}/orders"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=body, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('code') == 0:
                            result = data.get('data', {})
                            order.exchange_order_id = str(result.get('orderID', ''))
                            order.status = OrderStatus.PLACED
                            logger.info(f"✅ Phemex ордер размещен: {order.exchange_order_id}")
                        else:
                            raise Exception(f"Phemex API error: {data}")
                    else:
                        error = await resp.text()
                        raise Exception(f"Phemex HTTP error {resp.status}: {error}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка Phemex ордера: {e}")
            order.status = OrderStatus.FAILED
            raise
    
    async def _place_huobi_order(self, order: Order):
        """Разместить ордер на Huobi"""
        # TODO: Реализовать размещение ордера на Huobi
        logger.warning("⚠️ Huobi ордера пока не реализованы")
        order.status = OrderStatus.FAILED
    
    async def cancel_order(self, order: Order) -> bool:
        """Отменить ордер"""
        try:
            if not order.is_active:
                return True
                
            logger.info(f"🚫 Отмена ордера {order.id}")
            
            # Отмена через ccxt если доступен клиент
            client_info = self.exchange_clients.get(order.exchange, {})
            ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None
            if ccxt_client and order.exchange_order_id:
                try:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, lambda: ccxt_client.cancel_order(order.exchange_order_id, order.symbol))
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отменить ордер на {order.exchange}: {e}")
            
            order.status = OrderStatus.CANCELLED
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отмены ордера: {e}")
            return False
    
    async def _wait_for_fills(
        self, 
        orders: List[Order], 
        timeout: float = 30
    ) -> bool:
        """Ожидать исполнения ордеров"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            all_filled = all(o.is_filled for o in orders)
            if all_filled:
                return True
                
            # Обновление статусов
            for order in orders:
                if order.is_active:
                    await self._update_order_status(order)
            
            await asyncio.sleep(0.5)
        
        return False
    
    async def _update_order_status(self, order: Order):
        """Обновить статус ордера"""
        try:
            client_info = self.exchange_clients.get(order.exchange, {})
            ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None
            if not ccxt_client or not order.exchange_order_id:
                return

            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, lambda: ccxt_client.fetch_order(order.exchange_order_id, order.symbol))

            status_map = {
                'open': OrderStatus.PLACED,
                'closed': OrderStatus.FILLED,
                'canceled': OrderStatus.CANCELLED,
                'canceled_by_user': OrderStatus.CANCELLED,
                'rejected': OrderStatus.FAILED,
                'expired': OrderStatus.CANCELLED,
                'partially_filled': OrderStatus.PARTIALLY_FILLED,
            }
            ccxt_status = (data.get('status') or '').lower()
            order.status = status_map.get(ccxt_status, order.status)

            # Обновляем заполнение
            filled = float(data.get('filled') or 0)
            avg = float(data.get('average') or (order.price if order.price else 0))
            order.filled_amount = filled
            if filled > 0 and avg > 0:
                order.filled_price = avg

            # Комиссии (если доступны)
            fees = data.get('fees') or []
            if fees:
                try:
                    order.commission = sum(float(f.get('cost') or 0) for f in fees)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Не удалось обновить статус ордера через ccxt: {e}")
    
    async def update_balances(self):
        """Обновить балансы на всех биржах"""
        try:
            for exchange_id in self.exchange_clients:
                balance = await self._get_exchange_balance(exchange_id)
                self.balance[exchange_id] = balance
                # Логируем баланс каждой биржи в стабильном формате для монитора
                try:
                    amount = float(balance.get('USDT') or 0)
                    ex_name = EXCHANGES_CONFIG.get(exchange_id, {}).get('name', exchange_id.upper())
                    logger.info(f"Баланс: ${amount:.2f} {ex_name}")
                except Exception:
                    pass
                
            logger.info("✅ Балансы обновлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления балансов: {e}")
    
    async def _get_exchange_balance(self, exchange: str) -> Dict[str, float]:
        """Получить баланс с биржи"""
        try:
            client_info = self.exchange_clients.get(exchange, {})
            ccxt_client = client_info.get('ccxt') if isinstance(client_info, dict) else None
            if ccxt_client:
                loop = asyncio.get_running_loop()
                data = await loop.run_in_executor(None, lambda: ccxt_client.fetch_balance())
                total = data.get('total') or {}
                free = data.get('free') or {}
                # Предпочитаем свободный баланс
                usdt = float(free.get('USDT') or total.get('USDT') or 0)
                return {'USDT': usdt}
        except Exception as e:
            logger.debug(f"Не удалось получить баланс через ccxt [{exchange}]: {e}")
        # Фолбек: в demo вернуть минимум для старта, в остальных — 0
        if TRADING_CONFIG['mode'] == 'demo':
            return {'USDT': float(TRADING_CONFIG.get('demo_initial_usdt', 100))}
        return {'USDT': 0.0}
    
    async def _check_risk_limits(self, opportunity: ArbitrageOpportunity) -> bool:
        """Проверить риск-лимиты"""
        # Проверка максимального числа позиций
        active_positions = sum(1 for o in self.orders.values() if o.is_active)
        if active_positions >= RISK_MANAGEMENT['max_concurrent_positions']:
            logger.warning("⚠️ Достигнут лимит активных позиций")
            return False
        
        # Проверка дневного убытка
        if self.session_stats['total_profit_usd'] < -RISK_MANAGEMENT['max_daily_loss']:
            logger.warning("⚠️ Достигнут дневной лимит убытков")
            return False
        
        # Проверка минимальной прибыли
        if opportunity.expected_profit_pct < TRADING_CONFIG['min_profit_threshold']:
            logger.warning(f"⚠️ Прибыль ниже минимума: {opportunity.expected_profit_pct:.3f}%")
            return False
        
        return True
    
    def _calculate_position_size(self, opportunity: ArbitrageOpportunity) -> float:
        """Рассчитать размер позиции"""
        # Базовый размер
        base_size = POSITION_SIZING['default_position_usd']
        
        # Корректировка по волатильности
        if opportunity.expected_profit_pct > 0.5:
            base_size *= 1.5
        elif opportunity.expected_profit_pct > 0.3:
            base_size *= 1.2
        
        # Ограничение по объему
        max_by_volume = opportunity.min_volume * 0.1  # 10% от доступного объема
        
        # Ограничение по балансу
        available_balance = min(
            self.balance[ex].get('USDT', 0) 
            for ex in opportunity.exchanges
        )
        max_by_balance = available_balance * 0.3  # 30% от баланса
        
        # Финальный размер
        position_size = min(
            base_size,
            max_by_volume,
            max_by_balance,
            POSITION_SIZING['max_position_usd']
        )
        
        return max(position_size, POSITION_SIZING['min_position_usd'])
    
    def _calculate_realized_profit(
        self, 
        buy_order: Order, 
        sell_order: Order
    ) -> float:
        """Рассчитать реализованную прибыль"""
        revenue = sell_order.filled_amount * sell_order.filled_price
        cost = buy_order.filled_amount * buy_order.filled_price
        total_commission = buy_order.commission + sell_order.commission
        
        return revenue - cost - total_commission
    
    def _update_stats(self, profit: float, volume: float):
        """Обновить статистику"""
        self.session_stats['trades'] += 1
        if profit > 0:
            self.session_stats['successful'] += 1
        else:
            self.session_stats['failed'] += 1
            
        self.session_stats['total_profit_usd'] += profit
        self.session_stats['total_volume'] += volume
        
        if volume > 0:
            profit_pct = (profit / volume) * 100
            self.session_stats['total_profit_pct'] = (
                self.session_stats['total_profit_usd'] / 
                self.session_stats['total_volume'] * 100
            )
    
    def _log_paper_trade(
        self, 
        opportunity: ArbitrageOpportunity,
        position_size: float,
        gross_profit: float,
        net_profit: float
    ):
        """Записать paper-сделку"""
        trade = {
            'timestamp': time.time(),
            'type': opportunity.type,
            'exchanges': opportunity.exchanges,
            'symbols': opportunity.symbols,
            'position_size': position_size,
            'gross_profit': gross_profit,
            'net_profit': net_profit,
            'profit_pct': (net_profit / position_size * 100) if position_size > 0 else 0
        }
        
        self.trade_history.append(trade)
        self._update_stats(net_profit, position_size)
    
    async def _monitor_orders(self):
        """Мониторинг активных ордеров"""
        while self.running:
            try:
                for order_id, order in list(self.orders.items()):
                    if order.is_active:
                        await self._update_order_status(order)
                        
                        # Проверка таймаута
                        if time.time() - order.timestamp > 60:
                            logger.warning(f"⚠️ Таймаут ордера {order_id}")
                            await self.cancel_order(order)
                
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга ордеров: {e}")
                await asyncio.sleep(10)
    
    async def _risk_monitor(self):
        """Мониторинг рисков"""
        while self.running:
            try:
                # Проверка стоп-лосса
                if self.session_stats['total_profit_usd'] < -RISK_MANAGEMENT['stop_loss']:
                    logger.critical("🛑 СТОП-ЛОСС! Остановка торговли")
                    await self.stop()
                    break
                
                # Проверка тейк-профита
                if self.session_stats['total_profit_usd'] > RISK_MANAGEMENT['take_profit']:
                    logger.info("🎯 ТЕЙК-ПРОФИТ! Цель достигнута")
                    await self.stop()
                    break
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Ошибка мониторинга рисков: {e}")
                await asyncio.sleep(30)
    
    def _save_session_stats(self):
        """Сохранить статистику сессии"""
        duration = (time.time() - self.session_stats['start_time']) / 3600
        
        logger.info("=" * 50)
        logger.info("📊 СТАТИСТИКА СЕССИИ")
        logger.info(f"Продолжительность: {duration:.2f} часов")
        logger.info(f"Всего сделок: {self.session_stats['trades']}")
        logger.info(f"Успешных: {self.session_stats['successful']}")
        logger.info(f"Неудачных: {self.session_stats['failed']}")
        logger.info(f"Общий объем: ${self.session_stats['total_volume']:.2f}")
        logger.info(f"Прибыль USD: ${self.session_stats['total_profit_usd']:.2f}")
        logger.info(f"Прибыль %: {self.session_stats['total_profit_pct']:.3f}%")
        logger.info("=" * 50)
    
    def get_stats(self) -> Dict:
        """Получить текущую статистику"""
        return {
            **self.session_stats,
            'active_orders': sum(1 for o in self.orders.values() if o.is_active),
            'total_orders': len(self.orders),
            'balances': dict(self.balance)
        }
