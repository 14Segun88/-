"""
🔺 Модуль треугольного арбитража
Находит прибыльные циклы внутри одной биржи
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class TriangularOpportunity:
    """Возможность треугольного арбитража"""
    exchange: str
    path: List[str]  # Например: ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']
    direction: List[str]  # ['buy', 'sell', 'sell']
    prices: List[float]
    expected_profit_pct: float
    volume_usd: float
    timestamp: datetime
    
    def __str__(self):
        path_str = " → ".join([f"{p.split('/')[0]}" for p in self.path])
        return f"🔺 {self.exchange}: {path_str} → USDT | Profit: {self.expected_profit_pct:.3f}%"

class TriangularArbitrageScanner:
    """Сканер треугольного арбитража"""
    
    def __init__(self):
        self.min_profit_pct = 0.05  # Минимальная прибыль 0.05%
        self.common_bases = ['USDT', 'USDC', 'BUSD', 'BTC', 'ETH', 'BNB']
        self.triangular_paths = []
        self.initialized = False
        
    def initialize_paths(self, available_pairs: List[str]) -> None:
        """Инициализирует возможные треугольные пути"""
        self.triangular_paths = []
        
        # Создаем словарь пар по базовой валюте
        pairs_by_base = {}
        pairs_by_quote = {}
        
        for pair in available_pairs:
            try:
                base, quote = pair.split('/')
                
                if quote not in pairs_by_base:
                    pairs_by_base[quote] = []
                pairs_by_base[quote].append((base, pair))
                
                if base not in pairs_by_quote:
                    pairs_by_quote[base] = []
                pairs_by_quote[base].append((quote, pair))
                
            except:
                continue
        
        # Находим треугольные пути через стейблкоины
        for stable in ['USDT', 'USDC', 'BUSD']:
            if stable not in pairs_by_base:
                continue
                
            # Пары вида XXX/USDT
            direct_pairs = pairs_by_base[stable]
            
            for base1, pair1 in direct_pairs:
                if base1 in ['BTC', 'ETH', 'BNB']:  # Промежуточные валюты
                    # Ищем пары вида YYY/BTC
                    if base1 in pairs_by_base:
                        for base2, pair2 in pairs_by_base[base1]:
                            if base2 != stable and base2 != base1:
                                # Проверяем существование прямой пары YYY/USDT
                                closing_pair = f"{base2}/{stable}"
                                if closing_pair in available_pairs:
                                    # Нашли треугольник: USDT → BTC → YYY → USDT
                                    path = {
                                        'pairs': [pair1, pair2, closing_pair],
                                        'path': [stable, base1, base2, stable],
                                        'directions': ['buy', 'buy', 'sell']
                                    }
                                    self.triangular_paths.append(path)
                                    
                                    # Обратный путь
                                    reverse_path = {
                                        'pairs': [closing_pair, pair2, pair1],
                                        'path': [stable, base2, base1, stable],
                                        'directions': ['buy', 'sell', 'sell']
                                    }
                                    self.triangular_paths.append(reverse_path)
        
        # Добавляем классические треугольники
        classic_triangles = [
            # BTC треугольники
            {'pairs': ['BTC/USDT', 'ETH/BTC', 'ETH/USDT'], 'directions': ['buy', 'buy', 'sell']},
            {'pairs': ['ETH/USDT', 'ETH/BTC', 'BTC/USDT'], 'directions': ['buy', 'sell', 'sell']},
            
            # BNB треугольники
            {'pairs': ['BNB/USDT', 'ETH/BNB', 'ETH/USDT'], 'directions': ['buy', 'buy', 'sell']},
            {'pairs': ['BNB/USDT', 'BTC/BNB', 'BTC/USDT'], 'directions': ['buy', 'buy', 'sell']},
            
            # Стейблкоин треугольники
            {'pairs': ['USDC/USDT', 'BTC/USDC', 'BTC/USDT'], 'directions': ['buy', 'buy', 'sell']},
            {'pairs': ['BUSD/USDT', 'BTC/BUSD', 'BTC/USDT'], 'directions': ['buy', 'buy', 'sell']},
        ]
        
        for triangle in classic_triangles:
            # Проверяем доступность всех пар
            if all(pair in available_pairs for pair in triangle['pairs']):
                path = triangle.copy()
                currencies = []
                for pair in triangle['pairs']:
                    base, quote = pair.split('/')
                    if not currencies:
                        currencies.append(quote)
                    currencies.append(base)
                path['path'] = currencies
                self.triangular_paths.append(path)
        
        self.initialized = True
        logger.info(f"📐 Инициализировано {len(self.triangular_paths)} треугольных путей")
    
    def calculate_triangular_profit(
        self,
        prices: Dict[str, float],
        path: Dict,
        commission_pct: float = 0.1
    ) -> Optional[float]:
        """
        Рассчитывает прибыль треугольного арбитража
        
        Args:
            prices: Словарь цен {pair: price}
            path: Треугольный путь
            commission_pct: Комиссия в %
        
        Returns:
            Прибыль в % или None если путь неприбыльный
        """
        try:
            # Начинаем с 1 единицы базовой валюты
            amount = 1.0
            
            for i, (pair, direction) in enumerate(zip(path['pairs'], path['directions'])):
                if pair not in prices or prices[pair] <= 0:
                    return None
                    
                price = prices[pair]
                
                if direction == 'buy':
                    # Покупаем base за quote
                    amount = amount / price
                else:
                    # Продаем base за quote
                    amount = amount * price
                
                # Вычитаем комиссию
                amount *= (1 - commission_pct / 100)
            
            # Прибыль в процентах
            profit_pct = (amount - 1) * 100
            
            return profit_pct if profit_pct > self.min_profit_pct else None
            
        except Exception as e:
            logger.error(f"Ошибка расчета треугольной прибыли: {e}")
            return None
    
    def scan_opportunities(
        self,
        exchange: str,
        orderbooks: Dict[str, Dict],
        commission_pct: float = 0.1
    ) -> List[TriangularOpportunity]:
        """
        Сканирует треугольные возможности на бирже
        
        Args:
            exchange: Название биржи
            orderbooks: Словарь ордербуков {pair: orderbook}
            commission_pct: Комиссия биржи
        
        Returns:
            Список найденных возможностей
        """
        if not self.initialized:
            available_pairs = list(orderbooks.keys())
            self.initialize_paths(available_pairs)
        
        opportunities = []
        
        # Извлекаем цены из ордербуков
        prices = {}
        for pair, orderbook in orderbooks.items():
            try:
                bids = orderbook.get('bids', [])
                asks = orderbook.get('asks', [])
                
                if bids and asks:
                    # Берем среднюю цену между лучшим бидом и аском
                    prices[pair] = (bids[0][0] + asks[0][0]) / 2
            except:
                continue
        
        # Проверяем каждый треугольный путь
        for path in self.triangular_paths:
            # Проверяем доступность всех пар
            if not all(pair in prices for pair in path['pairs']):
                continue
            
            profit_pct = self.calculate_triangular_profit(prices, path, commission_pct)
            
            if profit_pct and profit_pct > self.min_profit_pct:
                opportunity = TriangularOpportunity(
                    exchange=exchange,
                    path=path['pairs'],
                    direction=path['directions'],
                    prices=[prices[pair] for pair in path['pairs']],
                    expected_profit_pct=profit_pct,
                    volume_usd=100,  # Начальный объем
                    timestamp=datetime.now()
                )
                opportunities.append(opportunity)
                
                logger.info(f"🔺 Найден треугольный арбитраж: {opportunity}")
        
        return opportunities
    
    def optimize_volume(
        self,
        opportunity: TriangularOpportunity,
        orderbooks: Dict[str, Dict],
        max_volume_usd: float = 1000
    ) -> float:
        """
        Оптимизирует объем для треугольной сделки
        
        Returns:
            Оптимальный объем в USD
        """
        try:
            min_available = max_volume_usd
            
            # Проверяем доступную ликвидность на каждом шаге
            for pair, direction in zip(opportunity.path, opportunity.direction):
                if pair not in orderbooks:
                    return 0
                    
                orderbook = orderbooks[pair]
                
                if direction == 'buy':
                    # Покупаем по аскам
                    orders = orderbook.get('asks', [])
                else:
                    # Продаем по бидам
                    orders = orderbook.get('bids', [])
                
                if not orders:
                    return 0
                
                # Считаем доступный объем на первом уровне
                available_base = orders[0][1] if len(orders[0]) > 1 else 0
                available_usd = available_base * orders[0][0]
                
                min_available = min(min_available, available_usd)
            
            # Ограничиваем объем для безопасности
            return min(min_available * 0.5, max_volume_usd)
            
        except Exception as e:
            logger.error(f"Ошибка оптимизации объема: {e}")
            return 100  # Возвращаем минимальный объем

class TriangularExecutor:
    """Исполнитель треугольного арбитража"""
    
    def __init__(self, trading_engine):
        self.trading_engine = trading_engine
        self.executing = {}  # Активные исполнения
        
    async def execute_triangular(
        self,
        opportunity: TriangularOpportunity
    ) -> bool:
        """
        Исполняет треугольный арбитраж
        
        Returns:
            True если успешно, False если ошибка
        """
        try:
            logger.info(f"🔺 Исполнение треугольного арбитража: {opportunity}")
            
            # Проверяем, не исполняется ли уже
            key = f"{opportunity.exchange}:{':'.join(opportunity.path)}"
            if key in self.executing:
                logger.warning("Треугольник уже исполняется")
                return False
            
            self.executing[key] = True
            
            try:
                # Последовательно исполняем каждую ногу треугольника
                amount = opportunity.volume_usd
                
                for i, (pair, direction, price) in enumerate(
                    zip(opportunity.path, opportunity.direction, opportunity.prices)
                ):
                    logger.info(f"  Шаг {i+1}: {direction} {pair} @ {price}")
                    
                    # В демо режиме просто логируем
                    if self.trading_engine.demo_mode:
                        base, quote = pair.split('/')
                        if direction == 'buy':
                            amount = amount / price * 0.999  # С учетом комиссии
                        else:
                            amount = amount * price * 0.999
                        
                        logger.info(f"    [DEMO] Результат: {amount:.4f} {quote if direction == 'buy' else base}")
                    else:
                        # Реальное исполнение через trading_engine
                        # TODO: Реализовать реальное исполнение
                        pass
                
                # Расчет финальной прибыли
                final_profit_pct = (amount / opportunity.volume_usd - 1) * 100
                logger.info(f"✅ Треугольный арбитраж завершен. Прибыль: {final_profit_pct:.3f}%")
                
                return True
                
            finally:
                del self.executing[key]
                
        except Exception as e:
            logger.error(f"Ошибка исполнения треугольного арбитража: {e}")
            return False
