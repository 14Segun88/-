#!/usr/bin/env python3
"""
Скрипт для проверки разницы цен между биржами
"""

import asyncio
import ccxt.pro as ccxt
from datetime import datetime
import os

# Прокси для обхода геоблокировки
PROXY = 'http://172.31.128.1:2080'
os.environ['HTTP_PROXY'] = PROXY
os.environ['HTTPS_PROXY'] = PROXY

async def check_prices():
    # Инициализация бирж
    exchanges = {
        'MEXC': ccxt.mexc({
            'apiKey': 'mx0vglaQQoW2jaFJQm',
            'secret': 'fa7b86db42eb4b22a14373296bc79c20',
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        }),
        'OKX': ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        }),
        'KuCoin': ccxt.kucoin({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        }),
        'Bybit': ccxt.bybit({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
            'proxies': {'http': PROXY, 'https': PROXY}
        }),
        'Gate.io': ccxt.gateio({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'},
            'proxies': {'http': PROXY, 'https': PROXY}
        })
    }
    
    # Проверяемые пары
    symbols = ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT', 'SHIB/USDT', 'PEPE/USDT']
    
    print("\n" + "="*80)
    print(f"🔍 ПРОВЕРКА РАЗНИЦЫ ЦЕН МЕЖДУ БИРЖАМИ")
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    for symbol in symbols:
        print(f"\n📊 {symbol}:")
        print("-" * 50)
        
        prices = {}
        for name, exchange in exchanges.items():
            try:
                ticker = await exchange.fetch_ticker(symbol)
                prices[name] = ticker['last']
                print(f"  {name:10} ${ticker['last']:.6f}")
            except Exception as e:
                print(f"  {name:10} Ошибка: {str(e)[:50]}")
        
        if len(prices) > 1:
            min_exchange = min(prices, key=prices.get)
            max_exchange = max(prices, key=prices.get)
            min_price = prices[min_exchange]
            max_price = prices[max_exchange]
            
            spread_pct = ((max_price - min_price) / min_price) * 100
            
            print(f"\n  💰 Арбитраж: {min_exchange} → {max_exchange}")
            print(f"     Спред: {spread_pct:.4f}%")
            print(f"     Покупка: ${min_price:.6f} на {min_exchange}")
            print(f"     Продажа: ${max_price:.6f} на {max_exchange}")
            
            # Расчет с учетом комиссий
            fees = {
                'MEXC': 0.0,      # 0% maker
                'OKX': 0.1,       # 0.1% taker
                'KuCoin': 0.1,    # 0.1% taker
                'Bybit': 0.06,    # 0.06% taker
                'Gate.io': 0.2    # 0.2% taker
            }
            
            total_fees = fees.get(min_exchange, 0.1) + fees.get(max_exchange, 0.1)
            net_profit = spread_pct - total_fees
            
            if net_profit > 0:
                print(f"     ✅ Чистая прибыль: {net_profit:.4f}% (после комиссий {total_fees:.2f}%)")
            else:
                print(f"     ❌ Убыток: {net_profit:.4f}% (комиссии {total_fees:.2f}%)")
    
    # Закрытие соединений
    for exchange in exchanges.values():
        await exchange.close()
    
    print("\n" + "="*80)

if __name__ == "__main__":
    asyncio.run(check_prices())
