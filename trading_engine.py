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
import json
from decimal import Decimal, ROUND_DOWN
from collections import defaultdict

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
            if config['enabled'] and API_KEYS[exchange_id]['apiKey']:
                logger.info(f"Инициализация клиента {config['name']}")
                # Здесь будет инициализация специфичных клиентов
                self.exchange_clients[exchange_id] = {
                    'name': config['name'],
                    'api_key': API_KEYS[exchange_id]['apiKey'],
                    'secret': API_KEYS[exchange_id]['secret']
                }
    
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
            if TRADING_CONFIG['mode'] == 'real':
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
                
                # Ожидание исполнения
                filled = await self._wait_for_fills([buy_order, sell_order])
                
                if filled:
                    # Расчет прибыли
                    profit = self._calculate_realized_profit(buy_order, sell_order)
                    self._update_stats(profit, position_size)
                    logger.info(f"✅ Арбитраж успешен! Прибыль: ${profit:.2f}")
                    return True
                else:
                    logger.warning("⚠️ Ордера не исполнены полностью")
                    return False
                    
            else:  # paper или demo режим
                # Симуляция исполнения
                commission_buy = position_size * EXCHANGES_CONFIG[buy_exchange]['taker_fee']
                commission_sell = position_size * EXCHANGES_CONFIG[sell_exchange]['taker_fee']
                
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
            # Выбор метода размещения по бирже
            if exchange == 'mexc':
                await self._place_mexc_order(order)
            elif exchange == 'bybit':
                await self._place_bybit_order(order)
            elif exchange == 'huobi':
                await self._place_huobi_order(order)
            else:
                logger.warning(f"⚠️ Биржа {exchange} не поддерживается")
                order.status = OrderStatus.FAILED
                
            self.orders[order.id] = order
            return order
            
        except Exception as e:
            logger.error(f"❌ Ошибка размещения ордера: {e}")
            order.status = OrderStatus.FAILED
            self.orders[order.id] = order
            raise
    
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
        """Разместить ордер на Bybit"""
        # TODO: Реализовать размещение ордера на Bybit
        logger.warning("⚠️ Bybit ордера пока не реализованы")
        order.status = OrderStatus.FAILED
    
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
            
            # Отмена на конкретной бирже
            # TODO: Реализовать отмену для каждой биржи
            
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
        # TODO: Запросить статус с биржи
        pass
    
    async def update_balances(self):
        """Обновить балансы на всех биржах"""
        try:
            for exchange_id in self.exchange_clients:
                balance = await self._get_exchange_balance(exchange_id)
                self.balance[exchange_id] = balance
                
            logger.info("✅ Балансы обновлены")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления балансов: {e}")
    
    async def _get_exchange_balance(self, exchange: str) -> Dict[str, float]:
        """Получить баланс с биржи"""
        # TODO: Реализовать для каждой биржи
        return {'USDT': 1000.0}  # Заглушка
    
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
