#!/usr/bin/env python3
"""
Диагностический скрипт для проверки REST polling Bitget
Тестирует получение orderbook через ExchangeConnector
"""

import asyncio
import time
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG

async def test_bitget_rest_polling():
    """Тест REST polling для Bitget"""
    
    print("🔧 Инициализация ExchangeConnector...")
    connector = ExchangeConnector(mode=TRADING_CONFIG['mode'])
    
    try:
        # Инициализация
        await connector.initialize()
        print("✅ ExchangeConnector инициализирован")
        
        # Тестируемые пары
        test_pairs = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        
        print(f"\n📡 Тестирование REST polling Bitget для пар: {test_pairs}")
        
        for i in range(10):  # 10 тестовых циклов
            print(f"\n--- Цикл {i+1}/10 ---")
            
            for symbol in test_pairs:
                try:
                    start_time = time.time()
                    
                    # Получаем orderbook через REST
                    orderbook = await connector.fetch_orderbook('bitget', symbol)
                    
                    elapsed_time = (time.time() - start_time) * 1000  # в миллисекундах
                    
                    if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                        best_bid = orderbook['bids'][0][0] if orderbook['bids'] else None
                        best_ask = orderbook['asks'][0][0] if orderbook['asks'] else None
                        
                        print(f"  ✅ {symbol}: bid={best_bid:.6f}, ask={best_ask:.6f} ({elapsed_time:.1f}ms)")
                    else:
                        print(f"  ❌ {symbol}: пустой orderbook")
                        
                except Exception as e:
                    print(f"  ⚠️ {symbol}: ошибка - {e}")
            
            # Пауза между циклами
            await asyncio.sleep(2)
        
        print("\n🎯 Тест завершен")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        
    finally:
        # Закрытие
        await connector.close()
        print("🔌 ExchangeConnector закрыт")

if __name__ == "__main__":
    asyncio.run(test_bitget_rest_polling())
