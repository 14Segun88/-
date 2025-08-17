"""
Order Execution Module - Simplified Version
Модуль исполнения ордеров для арбитражного бота
"""

import asyncio
from typing import Dict, Optional, Tuple
import time
import logging

class OrderExecutor:
    """Исполнитель ордеров для арбитража"""
    
    def __init__(self, ccxt_clients: Dict):
        self.clients = ccxt_clients
        self.execution_history = []
        self.logger = logging.getLogger(__name__)
        
        # Настройки
        self.use_market_orders = False
        self.ioc_enabled = True
        self.max_slippage_pct = 0.5
        self.retry_attempts = 2
        self.order_timeout_sec = 10
        
    async def execute_arbitrage_pair(
        self, 
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        amount: float,
        buy_price: float,
        sell_price: float
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Исполнение парной арбитражной сделки"""
        
        self.logger.info(f"Исполнение: {symbol} купить на {buy_exchange} @ {buy_price:.4f}, продать на {sell_exchange} @ {sell_price:.4f}")
        
        # Параллельное размещение ордеров
        buy_task = asyncio.create_task(
            self._place_order(buy_exchange, symbol, 'buy', amount, buy_price)
        )
        
        sell_task = asyncio.create_task(
            self._place_order(sell_exchange, symbol, 'sell', amount, sell_price)
        )
        
        try:
            buy_result, sell_result = await asyncio.gather(
                buy_task, sell_task, return_exceptions=True
            )
            
            if isinstance(buy_result, Exception):
                self.logger.error(f"Ошибка покупки: {buy_result}")
                buy_result = None
                
            if isinstance(sell_result, Exception):
                self.logger.error(f"Ошибка продажи: {sell_result}")
                sell_result = None
            
            return buy_result, sell_result
            
        except Exception as e:
            self.logger.error(f"Критическая ошибка: {e}")
            return None, None
    
    async def _place_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        amount: float,
        price: float
    ) -> Dict:
        """Размещение ордера с повторами"""
        
        client = self.clients.get(exchange)
        if not client:
            raise ValueError(f"Клиент {exchange} не найден")
        
        formatted_symbol = self._format_symbol(symbol)
        
        for attempt in range(self.retry_attempts):
            try:
                params = {'timeInForce': 'IOC'} if self.ioc_enabled else {}
                
                if side == 'buy':
                    order = await client.create_limit_buy_order(
                        formatted_symbol, amount, price, params
                    )
                else:
                    order = await client.create_limit_sell_order(
                        formatted_symbol, amount, price, params
                    )
                
                self.execution_history.append({
                    'exchange': exchange,
                    'symbol': symbol,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'order_id': order.get('id'),
                    'timestamp': time.time()
                })
                
                return order
                
            except Exception as e:
                self.logger.warning(f"Попытка {attempt + 1}/{self.retry_attempts}: {e}")
                if attempt == self.retry_attempts - 1:
                    raise
                await asyncio.sleep(0.5)
    
    def _format_symbol(self, symbol: str) -> str:
        """Форматирование символа для CCXT"""
        if '/' not in symbol:
            if symbol.endswith('USDT'):
                return f"{symbol[:-4]}/USDT"
            elif symbol.endswith('BTC'):
                return f"{symbol[:-3]}/BTC"
        return symbol
    
    def get_stats(self) -> Dict:
        """Статистика исполнения"""
        return {
            'total_orders': len(self.execution_history),
            'last_execution': self.execution_history[-1] if self.execution_history else None
        }
