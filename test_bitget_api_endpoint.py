#!/usr/bin/env python3
"""
Тестирование API endpoint для получения пар Bitget
"""

import aiohttp
import asyncio
import json
from datetime import datetime

async def test_bitget_api_endpoints():
    """Тестирует различные API endpoints Bitget"""
    print("🔧 ТЕСТИРОВАНИЕ API ENDPOINTS BITGET")
    print("=" * 50)
    
    endpoints = [
        {
            'name': 'Старый API (используется в боте)',
            'url': 'https://api.bitget.com/api/spot/v1/market/tickers'
        },
        {
            'name': 'Новый API V2 (рекомендуемый)',
            'url': 'https://api.bitget.com/api/v2/spot/market/tickers'
        },
        {
            'name': 'Public Products API',
            'url': 'https://api.bitget.com/api/spot/v1/public/products'
        }
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint in endpoints:
            print(f"\n📡 Тестируем: {endpoint['name']}")
            print(f"🔗 URL: {endpoint['url']}")
            
            try:
                async with session.get(endpoint['url']) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"   ✅ Статус: {resp.status}")
                        print(f"   📊 Размер ответа: {len(str(data))} chars")
                        
                        # Пробуем разобрать данные
                        if 'data' in data and isinstance(data['data'], list):
                            items = data['data'][:3]  # Первые 3 элемента
                            print(f"   📈 Элементов в data: {len(data['data'])}")
                            print(f"   🔍 Пример данных: {json.dumps(items, indent=2)}")
                            
                            # Тестируем логику парсинга как в боте
                            pairs = []
                            for ticker in data.get('data', []):
                                sym_raw = str(ticker.get('symbol', '')).upper()
                                if not sym_raw:
                                    continue
                                # Убираем суффиксы канала спота Bitget
                                basequote = sym_raw.split('_')[0]
                                if basequote.endswith('USDT') and len(basequote) > 4:
                                    base = basequote[:-4]
                                    pairs.append(f"{base}/USDT")
                            
                            print(f"   🎯 Распознано USDT пар: {len(pairs)}")
                            if pairs:
                                print(f"   📋 Примеры пар: {pairs[:10]}")
                        else:
                            print(f"   📄 Структура ответа: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                            
                    else:
                        print(f"   ❌ Ошибка HTTP: {resp.status}")
                        try:
                            error_data = await resp.text()
                            print(f"   📄 Ответ: {error_data[:200]}...")
                        except:
                            pass
                            
            except Exception as e:
                print(f"   ❌ Исключение: {e}")
    
    print(f"\n🏁 Тестирование завершено: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    asyncio.run(test_bitget_api_endpoints())
