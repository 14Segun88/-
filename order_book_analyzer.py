"""
📊 Анализатор глубины ордербуков
Проверяет ликвидность перед исполнением сделок
"""

import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class LiquidityAnalysis:
    """Результат анализа ликвидности"""
    symbol: str
    exchange: str
    side: str  # 'buy' или 'sell'
    available_volume: float
    avg_price: float
    price_impact: float  # Влияние на цену в %
    depth_levels: int  # Количество уровней в стакане
    can_execute: bool
    reason: str = ""

class OrderBookAnalyzer:
    """Анализатор глубины ордербуков"""
    
    def __init__(self):
        self.min_liquidity_usd = 5  # 🔥 УЛЬТРА-АГРЕССИВНО: снижено до $5 (в 2 раза меньше размера позиции $10)
        self.max_price_impact = 25.0  # 🔥 ЭКСТРЕМАЛЬНО увеличено до 25% - принимаем любой slippage
        self.min_depth_levels = 1  # 🔥 Минимум 1 уровень
        
    def analyze_liquidity(
        self, 
        orderbook: Dict,
        side: str,
        volume_usd: float,
        exchange: str,
        symbol: str
    ) -> LiquidityAnalysis:
        """
        Анализирует ликвидность в ордербуке
        
        Args:
            orderbook: Стакан заявок {'bids': [], 'asks': []}
            side: 'buy' или 'sell'
            volume_usd: Объем сделки в USD
            exchange: Название биржи
            symbol: Торговая пара
        """
        try:
            # Выбираем нужную сторону стакана
            if side == 'buy':
                orders = orderbook.get('asks', [])  # Покупаем по аскам
                best_price = orders[0][0] if orders else 0
            else:
                orders = orderbook.get('bids', [])  # Продаем по бидам
                best_price = orders[0][0] if orders else 0
            
            if not orders or len(orders) < self.min_depth_levels:
                return LiquidityAnalysis(
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    available_volume=0,
                    avg_price=0,
                    price_impact=100,
                    depth_levels=len(orders) if orders else 0,
                    can_execute=False,
                    reason=f"Недостаточная глубина стакана: {len(orders)} уровней"
                )
            
            # Рассчитываем доступный объем и среднюю цену
            total_volume = 0
            total_cost = 0
            levels_used = 0
            
            volume_needed = volume_usd / best_price if best_price > 0 else 0
            
            for price, amount in orders[:20]:  # Берем максимум 20 уровней
                if total_volume >= volume_needed:
                    break
                    
                level_volume = min(amount, volume_needed - total_volume)
                total_volume += level_volume
                total_cost += level_volume * price
                levels_used += 1
            
            if total_volume < volume_needed * 0.50:  # 🔥 СНИЖЕНО: достаточно 50% объема от требуемого
                return LiquidityAnalysis(
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    available_volume=total_volume * best_price,
                    avg_price=total_cost / total_volume if total_volume > 0 else 0,
                    price_impact=100,
                    depth_levels=len(orders),
                    can_execute=False,
                    reason=f"Недостаточный объем: доступно ${total_volume * best_price:.2f} из ${volume_usd:.2f}"
                )
            
            # Рассчитываем среднюю цену и влияние на рынок
            avg_price = total_cost / total_volume if total_volume > 0 else 0
            price_impact = abs((avg_price - best_price) / best_price * 100) if best_price > 0 else 100
            
            # Проверяем критерии
            can_execute = (
                price_impact <= self.max_price_impact and
                total_volume * best_price >= self.min_liquidity_usd and
                levels_used >= self.min_depth_levels
            )
            
            reason = ""
            if not can_execute:
                if price_impact > self.max_price_impact:
                    reason = f"Слишком большое влияние на цену: {price_impact:.2f}%"
                elif total_volume * best_price < self.min_liquidity_usd:
                    reason = f"Недостаточная ликвидность: ${total_volume * best_price:.2f}"
                else:
                    reason = f"Использовано мало уровней: {levels_used}"
            
            return LiquidityAnalysis(
                symbol=symbol,
                exchange=exchange,
                side=side,
                available_volume=total_volume * best_price,
                avg_price=avg_price,
                price_impact=price_impact,
                depth_levels=levels_used,
                can_execute=can_execute,
                reason=reason
            )
            
        except Exception as e:
            logger.error(f"Ошибка анализа ликвидности: {e}")
            return LiquidityAnalysis(
                symbol=symbol,
                exchange=exchange,
                side=side,
                available_volume=0,
                avg_price=0,
                price_impact=100,
                depth_levels=0,
                can_execute=False,
                reason=f"Ошибка анализа: {str(e)}"
            )
    
    def check_slippage_risk(
        self,
        buy_orderbook: Dict,
        sell_orderbook: Dict,
        volume_usd: float
    ) -> Tuple[float, bool]:
        """
        Проверяет риск проскальзывания для арбитражной сделки
        
        Returns:
            (expected_slippage_pct, is_acceptable)
        """
        try:
            # Анализируем обе стороны
            buy_analysis = self.analyze_liquidity(
                buy_orderbook, 'buy', volume_usd, '', ''
            )
            sell_analysis = self.analyze_liquidity(
                sell_orderbook, 'sell', volume_usd, '', ''
            )
            
            # Суммарное проскальзывание
            total_slippage = buy_analysis.price_impact + sell_analysis.price_impact
            
            # Приемлемо если обе стороны проходят и общий slippage < 1%
            is_acceptable = (
                buy_analysis.can_execute and 
                sell_analysis.can_execute and
                total_slippage < 5.0  # 🔥 УВЕЛИЧЕН допустимый slippage до 5%
            )
            
            return total_slippage, is_acceptable
            
        except Exception as e:
            logger.error(f"Ошибка проверки slippage: {e}")
            return 100, False
    
    def find_optimal_volume(
        self,
        orderbook: Dict,
        side: str,
        max_volume_usd: float
    ) -> float:
        """
        Находит оптимальный объем для минимального влияния на цену
        
        Returns:
            Оптимальный объем в USD
        """
        try:
            # Тестируем разные объемы
            test_volumes = [
                max_volume_usd * 0.25,
                max_volume_usd * 0.5,
                max_volume_usd * 0.75,
                max_volume_usd
            ]
            
            optimal_volume = 0
            
            for volume in test_volumes:
                analysis = self.analyze_liquidity(
                    orderbook, side, volume, '', ''
                )
                
                if analysis.can_execute:
                    optimal_volume = volume
                else:
                    break  # Если текущий объем не проходит, больший тоже не пройдет
            
            return optimal_volume
            
        except Exception as e:
            logger.error(f"Ошибка поиска оптимального объема: {e}")
            return 0
