#!/usr/bin/env python3
"""
Тестирование различных endpoints для получения orderbook Bitget
"""

import aiohttp
import asyncio
import json
from datetime import datetime

async def test_bitget_orderbook_endpoints():
    """Тестирует различные endpoint для orderbook Bitget"""
    print("🔧 ТЕСТИРОВАНИЕ ORDERBOOK ENDPOINTS BITGET")
    print("=" * 50)
    
    # Тестовая пара
    test_symbol = "BTCUSDT"
    
    endpoints = [
        {
            'name': 'V1 Market Depth',
            'url': f'https://api.bitget.com/api/spot/v1/market/depth?symbol={test_symbol}&limit=10'
        },
        {
            'name': 'V2 Market Books',
            'url': f'https://api.bitget.com/api/v2/spot/market/orderbook?symbol={test_symbol}&limit=10'
        },
        {
            'name': 'V1 Public Depth',
            'url': f'https://api.bitget.com/api/spot/v1/public/depth?symbol={test_symbol}&limit=10'
        },
        {
            'name': 'V2 Market Depth',
            'url': f'https://api.bitget.com/api/v2/spot/market/books?symbol={test_symbol}&limit=10'
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint in endpoints:
            print(f"\n📡 Тестируем: {endpoint['name']}")
            print(f"🔗 URL: {endpoint['url']}")
            
            try:
                async with session.get(endpoint['url']) as resp:
                    print(f"   📋 Статус HTTP: {resp.status}")
                    
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"   ✅ Успешный ответ")
                        print(f"   📊 Размер ответа: {len(str(data))} chars")
                        
                        # Пробуем разобрать структуру
                        if isinstance(data, dict):
                            print(f"   🗂️ Ключи ответа: {list(data.keys())}")
                            
                            # Ищем данные orderbook
                            if 'data' in data and isinstance(data['data'], dict):
                                orderbook_data = data['data']
                                print(f"   📈 Структура data: {list(orderbook_data.keys())}")
                                
                                # Проверяем bids/asks
                                if 'bids' in orderbook_data and 'asks' in orderbook_data:
                                    bids = orderbook_data['bids'][:3]  # Первые 3
                                    asks = orderbook_data['asks'][:3]  # Первые 3
                                    
                                    print(f"   💰 Bids ({len(orderbook_data['bids'])}): {bids}")
                                    print(f"   💸 Asks ({len(orderbook_data['asks'])}): {asks}")
                                    
                                    # Проверяем формат данных
                                    if bids and isinstance(bids[0], list) and len(bids[0]) >= 2:
                                        print(f"   ✅ Формат bids корректный: [price, volume]")
                                    if asks and isinstance(asks[0], list) and len(asks[0]) >= 2:
                                        print(f"   ✅ Формат asks корректный: [price, volume]")
                                        
                                        # Тестируем конвертацию
                                        try:
                                            best_bid = float(bids[0][0])
                                            best_ask = float(asks[0][0])
                                            print(f"   🎯 Лучшие цены: bid={best_bid:.6f}, ask={best_ask:.6f}")
                                        except (ValueError, IndexError) as e:
                                            print(f"   ⚠️ Ошибка конвертации цен: {e}")
                            else:
                                print(f"   📄 Сырые данные: {json.dumps(data, indent=2)[:500]}...")
                                
                    else:
                        print(f"   ❌ Ошибка HTTP: {resp.status}")
                        try:
                            error_data = await resp.text()
                            print(f"   📄 Ошибка: {error_data[:200]}...")
                        except:
                            pass
                            
            except Exception as e:
                print(f"   ❌ Исключение: {e}")
    
    print(f"\n🏁 Тестирование завершено: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    asyncio.run(test_bitget_orderbook_endpoints())
