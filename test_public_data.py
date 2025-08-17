#!/usr/bin/env python3
"""Тест получения публичных данных без API ключей."""
import asyncio
import ccxt.async_support as ccxt

async def test_public_data():
    """Тестирует получение данных через публичные API."""
    
    exchanges = {
        'binance': ccxt.binance({'enableRateLimit': True}),
        'bybit': ccxt.bybit({'enableRateLimit': True}),
        'okx': ccxt.okx({'enableRateLimit': True}),
        'kucoin': ccxt.kucoin({'enableRateLimit': True}),
        'mexc': ccxt.mexc({'enableRateLimit': True})
    }
    
    test_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    for name, exchange in exchanges.items():
        print(f"\n📊 Тестирую {name.upper()}...")
        try:
            # Пробуем получить тикеры
            ticker = await exchange.fetch_ticker('BTC/USDT')
            print(f"  ✅ BTC/USDT: bid={ticker['bid']:.2f}, ask={ticker['ask']:.2f}")
            
            # Пробуем получить несколько тикеров
            tickers = await exchange.fetch_tickers(test_symbols)
            print(f"  ✅ Получено {len(tickers)} тикеров")
            
            for symbol in test_symbols:
                if symbol in tickers:
                    t = tickers[symbol]
                    spread = ((t['ask'] - t['bid']) / t['bid'] * 100) if t['bid'] else 0
                    print(f"    {symbol}: bid={t['bid']:.2f}, ask={t['ask']:.2f}, spread={spread:.3f}%")
                    
        except Exception as e:
            print(f"  ❌ Ошибка: {e}")
        finally:
            await exchange.close()
    
    # Проверяем арбитражные возможности
    print("\n🔍 Поиск арбитражных возможностей...")
    
    # Собираем цены по всем биржам
    all_prices = {}
    for name, exchange in exchanges.items():
        try:
            exchange = ccxt.__dict__[name]({'enableRateLimit': True})
            tickers = await exchange.fetch_tickers(test_symbols)
            
            for symbol in test_symbols:
                if symbol in tickers:
                    if symbol not in all_prices:
                        all_prices[symbol] = {}
                    all_prices[symbol][name] = {
                        'bid': tickers[symbol]['bid'],
                        'ask': tickers[symbol]['ask']
                    }
            await exchange.close()
        except:
            pass
    
    # Ищем арбитраж
    for symbol, prices in all_prices.items():
        best_bid = 0
        best_bid_exchange = None
        best_ask = float('inf')
        best_ask_exchange = None
        
        for exchange, price_data in prices.items():
            if price_data['bid'] and price_data['bid'] > best_bid:
                best_bid = price_data['bid']
                best_bid_exchange = exchange
            if price_data['ask'] and price_data['ask'] < best_ask:
                best_ask = price_data['ask']
                best_ask_exchange = exchange
        
        if best_bid > best_ask and best_bid_exchange != best_ask_exchange:
            spread_pct = (best_bid - best_ask) / best_ask * 100
            net_profit = spread_pct - 0.2  # ~0.1% комиссия на каждой бирже
            
            if net_profit > 0:
                print(f"\n⚡ АРБИТРАЖ {symbol}:")
                print(f"  Купить на {best_ask_exchange}: ${best_ask:.2f}")
                print(f"  Продать на {best_bid_exchange}: ${best_bid:.2f}")
                print(f"  Спред: {spread_pct:.3f}%")
                print(f"  Чистая прибыль: {net_profit:.3f}%")

if __name__ == "__main__":
    asyncio.run(test_public_data())
