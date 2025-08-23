#!/usr/bin/env python3
"""
Тест обнаружения арбитража с реальными данными
Проверка почему бот не видит явные различия цен
"""

import asyncio
import sys
import time
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG
from trading_engine import TradingEngine

class ArbitrageChecker:
    def __init__(self):
        self.exchanges = {}
        
    def calculate_arbitrage_profit(self, buy_price, sell_price, amount=1.0):
        """Расчет арбитражной прибыли"""
        if not buy_price or not sell_price or buy_price >= sell_price:
            return 0.0
            
        # Учитываем комиссии (0.1% на каждую сторону)
        buy_cost = buy_price * amount * 1.001
        sell_revenue = sell_price * amount * 0.999
        
        profit = sell_revenue - buy_cost
        profit_pct = (profit / buy_cost) * 100 if buy_cost > 0 else 0
        
        return profit_pct
        
    async def test_current_prices(self):
        """Тест с текущими ценами"""
        print("🔥 ТЕСТ ОБНАРУЖЕНИЯ АРБИТРАЖА")
        print("=" * 50)
        
        connector = ExchangeConnector(mode='testnet')
        await connector.initialize(['bitget', 'phemex'])
        
        # Получаем данные
        symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT']
        
        for symbol in symbols:
            print(f"\n📊 {symbol}:")
            
            # Получаем orderbook с обеих бирж
            bitget_ob = await connector.fetch_orderbook('bitget', symbol)
            phemex_ob = await connector.fetch_orderbook('phemex', symbol)
            
            if not bitget_ob or not phemex_ob:
                print(f"  ❌ Нет данных для {symbol}")
                continue
                
            if not bitget_ob.get('bids') or not bitget_ob.get('asks'):
                print(f"  ❌ Bitget: нет bid/ask для {symbol}")
                continue
                
            if not phemex_ob.get('bids') or not phemex_ob.get('asks'):
                print(f"  ❌ Phemex: нет bid/ask для {symbol}")
                continue
            
            # Извлекаем цены
            bitget_bid = bitget_ob['bids'][0][0] if bitget_ob['bids'] else 0
            bitget_ask = bitget_ob['asks'][0][0] if bitget_ob['asks'] else 0
            phemex_bid = phemex_ob['bids'][0][0] if phemex_ob['bids'] else 0  
            phemex_ask = phemex_ob['asks'][0][0] if phemex_ob['asks'] else 0
            
            print(f"  Bitget: {bitget_bid:.4f}/{bitget_ask:.4f}")
            print(f"  Phemex: {phemex_bid:.4f}/{phemex_ask:.4f}")
            
            # Проверяем арбитражные возможности в обе стороны
            
            # Покупаем на Bitget, продаем на Phemex
            profit1 = self.calculate_arbitrage_profit(bitget_ask, phemex_bid)
            if profit1 > 0:
                print(f"  🟢 Bitget→Phemex: {profit1:.4f}% прибыль")
            
            # Покупаем на Phemex, продаем на Bitget  
            profit2 = self.calculate_arbitrage_profit(phemex_ask, bitget_bid)
            if profit2 > 0:
                print(f"  🟢 Phemex→Bitget: {profit2:.4f}% прибыль")
                
            # Проверяем пороги
            min_threshold = TRADING_CONFIG['min_profit_threshold']
            
            if profit1 > min_threshold:
                print(f"  ✅ ВОЗМОЖНОСТЬ 1: {profit1:.4f}% > {min_threshold}%")
            elif profit1 > 0:
                print(f"  ⚠️  Слишком мало 1: {profit1:.4f}% < {min_threshold}%")
                
            if profit2 > min_threshold:
                print(f"  ✅ ВОЗМОЖНОСТЬ 2: {profit2:.4f}% > {min_threshold}%")  
            elif profit2 > 0:
                print(f"  ⚠️  Слишком мало 2: {profit2:.4f}% < {min_threshold}%")
                
            if profit1 <= 0 and profit2 <= 0:
                print(f"  ❌ Нет арбитража")
        
        await connector.close()
        print("\n🔥 ТЕСТ ЗАВЕРШЕН")

async def main():
    checker = ArbitrageChecker()
    await checker.test_current_prices()

if __name__ == "__main__":
    asyncio.run(main())
