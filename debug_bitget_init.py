#!/usr/bin/env python3
"""
Отладочный скрипт для диагностики инициализации Bitget в основном боте
"""

import asyncio
import sys
import traceback
from datetime import datetime

# Импортируем основные модули бота
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG, EXCHANGES_CONFIG

async def debug_bitget_initialization():
    """Отладка инициализации Bitget"""
    print("🔧 ДИАГНОСТИКА ИНИЦИАЛИЗАЦИИ BITGET")
    print("=" * 50)
    print(f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}")
    
    # 1. Проверяем конфигурацию Bitget
    print("\n📋 1. КОНФИГУРАЦИЯ BITGET:")
    bitget_config = EXCHANGES_CONFIG.get('bitget', {})
    for key, value in bitget_config.items():
        print(f"   {key}: {value}")
    
    # 2. Проверяем режим торговли
    print(f"\n💼 2. РЕЖИМ ТОРГОВЛИ: {TRADING_CONFIG.get('mode', 'demo')}")
    
    # 3. Инициализируем ExchangeConnector
    print("\n🔌 3. ИНИЦИАЛИЗАЦИЯ EXCHANGE CONNECTOR:")
    try:
        connector = ExchangeConnector(mode=TRADING_CONFIG['mode'])
        print("   ✅ ExchangeConnector создан")
        
        # 4. Пытаемся инициализировать только Bitget
        print("\n🎯 4. ИНИЦИАЛИЗАЦИЯ ТОЛЬКО BITGET:")
        await connector.initialize(['bitget'])
        
        # 5. Проверяем статус Bitget
        print("\n📊 5. СТАТУС BITGET:")
        if 'bitget' in connector.exchanges:
            exchange = connector.exchanges['bitget']
            print(f"   ✅ Bitget CCXT объект создан: {type(exchange)}")
            print(f"   📡 Sandbox mode: {getattr(exchange, 'sandbox', 'N/A')}")
            print(f"   🔑 Has API keys: {bool(getattr(exchange, 'apiKey', None))}")
            
            # 6. Тестируем загрузку markets
            print("\n📈 6. ТЕСТИРОВАНИЕ ЗАГРУЗКИ MARKETS:")
            try:
                markets = await exchange.load_markets()
                spot_pairs = {symbol for symbol, market in markets.items() 
                             if market.get('type') == 'spot' and market.get('active')}
                print(f"   ✅ Markets загружены: {len(markets)} total, {len(spot_pairs)} SPOT")
                
                # Проверяем несколько приоритетных пар
                priority_pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
                found_pairs = [pair for pair in priority_pairs if pair in spot_pairs]
                print(f"   🎯 Приоритетные пары найдены: {found_pairs}")
                
                # 7. Тестируем получение orderbook
                print("\n📖 7. ТЕСТИРОВАНИЕ ORDERBOOK:")
                if 'BTC/USDT' in spot_pairs:
                    try:
                        orderbook = await connector.fetch_orderbook('bitget', 'BTC/USDT')
                        if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                            print(f"   ✅ Orderbook получен для BTC/USDT:")
                            print(f"      Лучший bid: {orderbook['bids'][0][0]}")
                            print(f"      Лучший ask: {orderbook['asks'][0][0]}")
                        else:
                            print(f"   ❌ Orderbook пуст для BTC/USDT")
                    except Exception as e:
                        print(f"   ❌ Ошибка получения orderbook: {e}")
                
            except Exception as e:
                print(f"   ❌ Ошибка загрузки markets: {e}")
                traceback.print_exc()
                
        else:
            print("   ❌ Bitget НЕ найден в connector.exchanges")
            print(f"   📋 Доступные биржи: {list(connector.exchanges.keys())}")
            
        await connector.close()
        
    except Exception as e:
        print(f"   ❌ Критическая ошибка инициализации: {e}")
        traceback.print_exc()
    
    print("\n🏁 ДИАГНОСТИКА ЗАВЕРШЕНА")

if __name__ == "__main__":
    asyncio.run(debug_bitget_initialization())
