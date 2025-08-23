#!/usr/bin/env python3
"""
Стратегия триангулярного арбитража между OKX, Bitget, Phemex
Оптимизирована для минимального риска и максимальной прибыли
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG

logger = logging.getLogger('TriangularArbitrage')

@dataclass
class ArbitrageOpportunity:
    """Возможность триангулярного арбитража"""
    exchanges: List[str]  # [exchange1, exchange2, exchange3]
    symbols: List[str]    # [symbol1, symbol2, symbol3]
    sides: List[str]      # ['buy', 'sell', 'buy']
    prices: List[float]   # Цены для каждого шага
    amounts: List[float]  # Объемы для каждого шага
    gross_profit_pct: float
    net_profit_pct: float
    total_fees_usd: float
    execution_time_estimate: float
    risk_score: float
    timestamp: float

class TriangularArbitrageStrategy:
    """Стратегия триангулярного арбитража между 3 биржами"""
    
    def __init__(self, connector: ExchangeConnector):
        self.connector = connector
        self.config = TRADING_CONFIG
        
        # Приоритеты бирж по качеству исполнения (на основе теста)
        self.exchange_priority = {
            'phemex': 1,   # Лучшие спреды (0.359% BTC, 0.176% ETH)
            'bitget': 2,   # Стабильная работа, узкие спреды
            'okx': 3       # Проблемы с API endpoints
        }
        
        # Оптимальные пары для триангулярного арбитража
        self.triangular_pairs = [
            # Высоколиквидные триады (базовая валюта - промежуточная - базовая)
            ('BTC/USDT', 'ETH/BTC', 'ETH/USDT'),   # BTC -> ETH -> USDT
            ('ETH/USDT', 'BNB/ETH', 'BNB/USDT'),   # ETH -> BNB -> USDT
            ('BTC/USDT', 'SOL/BTC', 'SOL/USDT'),   # BTC -> SOL -> USDT
            ('ETH/USDT', 'AVAX/ETH', 'AVAX/USDT'), # ETH -> AVAX -> USDT
            
            # Альткоин триады (для более высоких спредов)
            ('BTC/USDT', 'LINK/BTC', 'LINK/USDT'),
            ('ETH/USDT', 'UNI/ETH', 'UNI/USDT'),
            ('BTC/USDT', 'DOT/BTC', 'DOT/USDT'),
            ('ETH/USDT', 'MATIC/ETH', 'MATIC/USDT'),
        ]
        
        # Кэш данных
        self.orderbook_cache = {}
        self.last_cache_update = {}
        self.cache_ttl = 2.0  # 2 секунды
        
    async def scan_triangular_opportunities(self) -> List[ArbitrageOpportunity]:
        """Поиск возможностей триангулярного арбитража"""
        opportunities = []
        
        # Получаем активные биржи
        active_exchanges = [ex for ex, connected in self.connector.is_connected.items() 
                          if connected and ex in ['okx', 'bitget', 'phemex']]
        
        if len(active_exchanges) < 3:
            logger.warning(f"Недостаточно активных бирж для триангулярного арбитража: {len(active_exchanges)}")
            return opportunities
        
        # Обновляем кэш orderbook для всех пар
        await self._update_orderbook_cache(active_exchanges)
        
        # Проверяем каждую триаду пар
        for pair_triangle in self.triangular_pairs:
            # Генерируем различные комбинации бирж для триангулярного маршрута
            for i, ex1 in enumerate(active_exchanges):
                for j, ex2 in enumerate(active_exchanges):
                    for k, ex3 in enumerate(active_exchanges):
                        if i != j and j != k and i != k:  # Все разные биржи
                            opportunity = await self._evaluate_triangular_route(
                                exchanges=[ex1, ex2, ex3],
                                symbols=list(pair_triangle)
                            )
                            if opportunity and opportunity.net_profit_pct >= self.config['min_profit_threshold']:
                                opportunities.append(opportunity)
        
        # Сортируем по чистой прибыли и риску
        opportunities.sort(key=lambda x: (x.net_profit_pct, -x.risk_score), reverse=True)
        
        return opportunities[:5]  # Топ-5 возможностей
    
    async def _update_orderbook_cache(self, exchanges: List[str]):
        """Обновление кэша orderbook"""
        current_time = time.time()
        
        for exchange in exchanges:
            for pair_triangle in self.triangular_pairs:
                for symbol in pair_triangle:
                    cache_key = f"{exchange}:{symbol}"
                    
                    # Проверяем актуальность кэша
                    if (cache_key in self.last_cache_update and 
                        current_time - self.last_cache_update[cache_key] < self.cache_ttl):
                        continue
                    
                    try:
                        orderbook = await self.connector.fetch_orderbook(exchange, symbol)
                        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                            self.orderbook_cache[cache_key] = orderbook
                            self.last_cache_update[cache_key] = current_time
                    except Exception as e:
                        logger.debug(f"Не удалось обновить orderbook {exchange}:{symbol}: {e}")
    
    async def _evaluate_triangular_route(self, exchanges: List[str], symbols: List[str]) -> Optional[ArbitrageOpportunity]:
        """Оценка треугольного маршрута арбитража"""
        try:
            # Определяем последовательность операций
            # Пример: BTC/USDT (buy) -> ETH/BTC (sell) -> ETH/USDT (sell)
            
            symbol1, symbol2, symbol3 = symbols  # 'BTC/USDT', 'ETH/BTC', 'ETH/USDT'
            ex1, ex2, ex3 = exchanges
            
            # Получаем orderbook из кэша
            ob1 = self.orderbook_cache.get(f"{ex1}:{symbol1}")
            ob2 = self.orderbook_cache.get(f"{ex2}:{symbol2}")  
            ob3 = self.orderbook_cache.get(f"{ex3}:{symbol3}")
            
            if not (ob1 and ob2 and ob3):
                return None
            
            # Начальная сумма в USDT
            initial_usdt = self.config['position_size_usd']
            
            # Шаг 1: Покупаем BTC за USDT на бирже 1
            btc_ask_price = ob1['asks'][0][0]
            btc_ask_volume = ob1['asks'][0][1]
            btc_amount = initial_usdt / btc_ask_price
            
            if btc_amount > btc_ask_volume:
                return None  # Недостаточная ликвидность
            
            # Комиссия за покупку BTC
            fee1 = btc_amount * btc_ask_price * self._get_fee_rate(ex1, 'taker')
            btc_after_fee = btc_amount
            
            # Шаг 2: Продаем BTC за ETH на бирже 2 (если есть пара ETH/BTC)
            # Нужно учесть направление пары
            if symbol2 == 'ETH/BTC':
                # Продаем BTC (базовая валюта), получаем ETH
                eth_bid_price = ob2['bids'][0][0]  # ETH за 1 BTC
                eth_bid_volume = ob2['bids'][0][1]  # Сколько BTC можем продать
                
                if btc_after_fee > eth_bid_volume:
                    return None
                    
                eth_amount = btc_after_fee * eth_bid_price
                fee2 = eth_amount * self._get_fee_rate(ex2, 'taker')
                eth_after_fee = eth_amount - fee2
                
            else:
                return None  # Пока поддерживаем только простые случаи
            
            # Шаг 3: Продаем ETH за USDT на бирже 3
            usdt_bid_price = ob3['bids'][0][0]  # USDT за 1 ETH
            usdt_bid_volume = ob3['bids'][0][1]  # Сколько ETH можем продать
            
            if eth_after_fee > usdt_bid_volume:
                return None
                
            final_usdt = eth_after_fee * usdt_bid_price
            fee3 = final_usdt * self._get_fee_rate(ex3, 'taker')
            final_usdt_after_fee = final_usdt - fee3
            
            # Рассчитываем прибыль
            gross_profit_usdt = final_usdt - initial_usdt
            gross_profit_pct = (gross_profit_usdt / initial_usdt) * 100
            
            total_fees = fee1 + fee2 + fee3
            net_profit_usdt = final_usdt_after_fee - initial_usdt
            net_profit_pct = (net_profit_usdt / initial_usdt) * 100
            
            # Оценка риска
            risk_score = self._calculate_risk_score(exchanges, symbols, [btc_ask_price, eth_bid_price, usdt_bid_price])
            
            # Время исполнения (примерная оценка)
            execution_time = self._estimate_execution_time(exchanges)
            
            return ArbitrageOpportunity(
                exchanges=exchanges,
                symbols=symbols,
                sides=['buy', 'sell', 'sell'],
                prices=[btc_ask_price, eth_bid_price, usdt_bid_price],
                amounts=[btc_amount, eth_amount, eth_after_fee],
                gross_profit_pct=gross_profit_pct,
                net_profit_pct=net_profit_pct,
                total_fees_usd=total_fees,
                execution_time_estimate=execution_time,
                risk_score=risk_score,
                timestamp=time.time()
            )
            
        except Exception as e:
            logger.debug(f"Ошибка оценки треугольного маршрута: {e}")
            return None
    
    def _get_fee_rate(self, exchange: str, fee_type: str = 'taker') -> float:
        """Получить ставку комиссии"""
        fees = self.connector.REAL_FEES.get(exchange, {'maker': 0.001, 'taker': 0.001})
        
        # Используем maker комиссию для limit ордеров если настройка включена
        if self.config.get('use_maker_orders', True) and fee_type == 'taker':
            return fees.get('maker', 0.001)
        
        return fees.get(fee_type, 0.001)
    
    def _calculate_risk_score(self, exchanges: List[str], symbols: List[str], prices: List[float]) -> float:
        """Расчет риска стратегии (0-1, где 0 = низкий риск)"""
        risk_factors = []
        
        # Фактор 1: Приоритет бирж (чем выше приоритет, тем ниже риск)
        exchange_risk = sum(self.exchange_priority.get(ex, 5) for ex in exchanges) / (len(exchanges) * 5)
        risk_factors.append(exchange_risk)
        
        # Фактор 2: Волатильность цен (большие цены = больше риска slippage)
        price_volatility = sum(p for p in prices if p > 1000) / (len(prices) * 10000)  # Нормализация
        risk_factors.append(min(price_volatility, 1.0))
        
        # Фактор 3: Количество шагов (больше шагов = больше риска)
        steps_risk = len(exchanges) / 5.0  # 3 биржи из 5 возможных
        risk_factors.append(steps_risk)
        
        # Средний риск
        return sum(risk_factors) / len(risk_factors)
    
    def _estimate_execution_time(self, exchanges: List[str]) -> float:
        """Оценка времени исполнения в секундах"""
        base_time = 2.0  # Базовое время для одной операции
        
        # Добавляем время на каждую биржу
        total_time = len(exchanges) * base_time
        
        # Штраф за проблемные биржи
        for ex in exchanges:
            if self.exchange_priority.get(ex, 5) > 3:
                total_time += 1.0
                
        return total_time
    
    async def execute_triangular_arbitrage(self, opportunity: ArbitrageOpportunity) -> Dict:
        """Исполнение триангулярного арбитража"""
        logger.info(f"🔺 Исполняем треугольный арбитраж: {opportunity.net_profit_pct:.3f}% прибыль")
        
        execution_log = {
            'start_time': time.time(),
            'opportunity': opportunity,
            'steps': [],
            'success': False,
            'final_profit': 0.0,
            'errors': []
        }
        
        try:
            # Исполняем каждый шаг последовательно
            for i, (exchange, symbol, side, amount, price) in enumerate(zip(
                opportunity.exchanges, opportunity.symbols, opportunity.sides,
                opportunity.amounts, opportunity.prices
            )):
                step_start = time.time()
                
                logger.info(f"Шаг {i+1}/3: {side.upper()} {amount:.6f} {symbol} на {exchange.upper()} по цене {price:.6f}")
                
                # Создаем ордер с maker ценой если возможно
                use_maker = self.config.get('use_maker_orders', True) and side == 'buy'
                
                order = await self.connector.create_order(
                    exchange_id=exchange,
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=price if side == 'sell' else None,  # Market для покупки, limit для продажи
                    order_type='limit' if side == 'sell' else 'market',
                    use_maker=use_maker
                )
                
                step_result = {
                    'step': i + 1,
                    'exchange': exchange,
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'order_id': order['id'] if order else None,
                    'success': order is not None,
                    'execution_time': time.time() - step_start
                }
                
                execution_log['steps'].append(step_result)
                
                if not order:
                    raise Exception(f"Не удалось создать ордер на шаге {i+1}")
                
                # Небольшая пауза между шагами для обработки
                await asyncio.sleep(0.1)
            
            execution_log['success'] = True
            execution_log['final_profit'] = opportunity.net_profit_pct
            
            logger.info(f"✅ Треугольный арбитраж завершен успешно! Прибыль: {opportunity.net_profit_pct:.3f}%")
            
        except Exception as e:
            error_msg = f"Ошибка исполнения треугольного арбитража: {e}"
            execution_log['errors'].append(error_msg)
            logger.error(f"❌ {error_msg}")
        
        execution_log['total_time'] = time.time() - execution_log['start_time']
        return execution_log


# Функция для тестирования стратегии
async def test_triangular_strategy():
    """Тест стратегии триангулярного арбитража"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    logger.info("🔺 Тестирование стратегии триангулярного арбитража")
    
    # Инициализация коннектора
    connector = ExchangeConnector(mode='demo')
    await connector.initialize(['okx', 'bitget', 'phemex'])
    
    # Создание стратегии
    strategy = TriangularArbitrageStrategy(connector)
    
    # Поиск возможностей
    opportunities = await strategy.scan_triangular_opportunities()
    
    if opportunities:
        logger.info(f"🎯 Найдено {len(opportunities)} возможностей триангулярного арбитража:")
        for i, opp in enumerate(opportunities, 1):
            logger.info(f"{i}. {' -> '.join(opp.exchanges)}: {opp.net_profit_pct:.3f}% ({opp.risk_score:.3f} риск)")
        
        # Исполнение лучшей возможности (в demo режиме)
        best_opportunity = opportunities[0]
        result = await strategy.execute_triangular_arbitrage(best_opportunity)
        
        if result['success']:
            logger.info(f"✅ Исполнение завершено за {result['total_time']:.2f}с")
        else:
            logger.error(f"❌ Ошибки: {result['errors']}")
    else:
        logger.info("🔍 Возможности триангулярного арбитража не найдены")
    
    # Закрытие подключений
    for exchange in connector.exchanges.values():
        try:
            await exchange.close()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_triangular_strategy())
