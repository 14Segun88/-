"""
Risk Management Module for Arbitrage Bot
Модуль управления рисками для арбитражного бота
"""

import asyncio
from typing import Dict, Optional, List
from dataclasses import dataclass
import time

@dataclass
class RiskLimits:
    """Лимиты рисков для торговли"""
    max_position_size_usd: float = 100.0  # Максимальный размер позиции
    max_daily_loss_usd: float = 50.0      # Максимальный дневной убыток
    max_open_positions: int = 3           # Максимум открытых позиций
    min_profit_threshold: float = 0.3     # Минимальный порог прибыли (%)
    max_slippage_pct: float = 0.2        # Максимальное проскальзывание (%)
    position_timeout_seconds: int = 30    # Таймаут для исполнения позиции
    min_exchange_balance_usd: float = 200.0  # Минимальный баланс на бирже

class RiskManager:
    """Менеджер рисков для арбитражного бота"""
    
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.daily_pnl = 0.0
        self.open_positions = {}
        self.daily_reset_time = None
        self.trade_history = []
        self.blocked_pairs = set()  # Заблокированные пары после неудач
        self.exchange_health = {}   # Здоровье бирж
        
    def check_daily_loss_limit(self) -> bool:
        """Проверка дневного лимита убытков"""
        # Сброс счетчика каждый день
        current_day = time.strftime("%Y-%m-%d")
        if self.daily_reset_time != current_day:
            self.daily_pnl = 0.0
            self.daily_reset_time = current_day
            
        if self.daily_pnl <= -self.limits.max_daily_loss_usd:
            return False
        return True
    
    def check_position_size(self, size_usd: float) -> bool:
        """Проверка размера позиции"""
        return size_usd <= self.limits.max_position_size_usd
    
    def check_open_positions_limit(self) -> bool:
        """Проверка лимита открытых позиций"""
        # Очистка старых позиций (старше таймаута)
        current_time = time.time()
        expired_positions = [
            pos_id for pos_id, pos_data in self.open_positions.items()
            if current_time - pos_data['timestamp'] > self.limits.position_timeout_seconds
        ]
        for pos_id in expired_positions:
            del self.open_positions[pos_id]
            
        return len(self.open_positions) < self.limits.max_open_positions
    
    def check_profit_threshold(self, profit_pct: float) -> bool:
        """Проверка минимального порога прибыли"""
        return profit_pct >= self.limits.min_profit_threshold
    
    def check_exchange_balance(self, exchange: str, balance_usd: float) -> bool:
        """Проверка минимального баланса на бирже"""
        return balance_usd >= self.limits.min_exchange_balance_usd
    
    def validate_opportunity(self, opportunity: Dict) -> tuple[bool, str]:
        """
        Комплексная валидация арбитражной возможности
        Возвращает (разрешено, причина_отказа)
        """
        # 1. Проверка дневного лимита убытков
        if not self.check_daily_loss_limit():
            return False, "Достигнут дневной лимит убытков"
        
        # 2. Проверка лимита открытых позиций
        if not self.check_open_positions_limit():
            return False, "Достигнут лимит открытых позиций"
        
        # 3. Проверка размера позиции
        position_size = opportunity.get('position_size_usd', 100)
        if not self.check_position_size(position_size):
            return False, f"Размер позиции {position_size} превышает лимит"
        
        # 4. Проверка минимального профита
        profit_pct = opportunity.get('profit_pct', 0)
        if not self.check_profit_threshold(profit_pct):
            return False, f"Профит {profit_pct:.2f}% ниже минимального порога"
        
        # 5. Проверка заблокированных пар
        symbol = opportunity.get('symbol', '')
        if symbol in self.blocked_pairs:
            return False, f"Пара {symbol} временно заблокирована"
        
        # 6. Проверка здоровья бирж
        buy_exchange = opportunity.get('buy_exchange', '')
        sell_exchange = opportunity.get('sell_exchange', '')
        
        if buy_exchange in self.exchange_health:
            if not self.exchange_health[buy_exchange].get('is_healthy', True):
                return False, f"Биржа {buy_exchange} недоступна"
                
        if sell_exchange in self.exchange_health:
            if not self.exchange_health[sell_exchange].get('is_healthy', True):
                return False, f"Биржа {sell_exchange} недоступна"
        
        return True, "OK"
    
    def register_position(self, position_id: str, opportunity: Dict):
        """Регистрация новой позиции"""
        self.open_positions[position_id] = {
            'opportunity': opportunity,
            'timestamp': time.time(),
            'status': 'open'
        }
    
    def close_position(self, position_id: str, pnl: float):
        """Закрытие позиции с учетом P&L"""
        if position_id in self.open_positions:
            del self.open_positions[position_id]
            self.daily_pnl += pnl
            self.trade_history.append({
                'position_id': position_id,
                'pnl': pnl,
                'timestamp': time.time()
            })
    
    def block_pair(self, symbol: str, duration_seconds: int = 300):
        """Временная блокировка пары после неудачи"""
        self.blocked_pairs.add(symbol)
        # Автоматическая разблокировка через указанное время
        asyncio.create_task(self._unblock_pair_after(symbol, duration_seconds))
    
    async def _unblock_pair_after(self, symbol: str, duration: int):
        """Разблокировка пары после таймаута"""
        await asyncio.sleep(duration)
        self.blocked_pairs.discard(symbol)
    
    def update_exchange_health(self, exchange: str, is_healthy: bool, error_count: int = 0):
        """Обновление состояния здоровья биржи"""
        self.exchange_health[exchange] = {
            'is_healthy': is_healthy,
            'error_count': error_count,
            'last_update': time.time()
        }
    
    def get_risk_metrics(self) -> Dict:
        """Получение текущих метрик рисков"""
        return {
            'daily_pnl': self.daily_pnl,
            'open_positions_count': len(self.open_positions),
            'blocked_pairs_count': len(self.blocked_pairs),
            'daily_loss_limit_remaining': self.limits.max_daily_loss_usd + self.daily_pnl,
            'position_limit_remaining': self.limits.max_open_positions - len(self.open_positions),
            'unhealthy_exchanges': [
                ex for ex, health in self.exchange_health.items() 
                if not health.get('is_healthy', True)
            ]
        }
