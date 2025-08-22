#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки торговых пар Bitget
Проверяет подключение к API и корректность загрузки символов
"""

import asyncio
import ccxt
import json
import sys
from datetime import datetime
from production_config import EXCHANGES_CONFIG

class BitgetPairsTest:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'error': None,
            'total_pairs': 0,
            'usdt_pairs': 0,
            'common_pairs_found': 0,
            'sample_pairs': [],
            'api_response_time': None
        }
        
    async def test_bitget_connection(self):
        """Тестирует подключение к Bitget API и загрузку пар"""
        print("🔄 Тестирование подключения к Bitget API...")
        
        try:
            start_time = datetime.now()
            
            # Инициализируем Bitget CCXT клиент
            bitget_config = EXCHANGES_CONFIG['bitget']
            bitget = ccxt.bitget({
                'apiKey': '',  # Для загрузки пар API ключи не нужны
                'secret': '',
                'password': '',
                'sandbox': False,  # Используем production API для markets
                'enableRateLimit': True,
                'rateLimit': bitget_config['rate_limit'],
                'options': {
                    'defaultType': 'spot'  # Explicitly request spot markets
                }
            })
            
            # Загружаем markets (торговые пары)
            print("📊 Загружаем торговые пары Bitget...")
            markets = bitget.load_markets()
            
            response_time = (datetime.now() - start_time).total_seconds()
            self.results['api_response_time'] = response_time
            
            # Фильтруем только SPOT пары
            spot_pairs = {symbol: market for symbol, market in markets.items() 
                         if market['type'] == 'spot' and market['active']}
            
            # Фильтруем USDT пары
            usdt_pairs = {symbol: market for symbol, market in spot_pairs.items() 
                         if symbol.endswith('/USDT')}
            
            self.results['total_pairs'] = len(spot_pairs)
            self.results['usdt_pairs'] = len(usdt_pairs)
            self.results['sample_pairs'] = list(usdt_pairs.keys())[:20]  # Первые 20 для примера
            
            # Проверяем наличие приоритетных пар из конфига
            from production_config import DYNAMIC_PAIRS_CONFIG
            priority_pairs = DYNAMIC_PAIRS_CONFIG['priority_pairs']
            
            common_found = [pair for pair in priority_pairs if pair in usdt_pairs]
            self.results['common_pairs_found'] = len(common_found)
            
            self.results['success'] = True
            
            print(f"✅ Подключение к Bitget успешно!")
            print(f"📈 Total SPOT pairs: {len(spot_pairs)}")
            print(f"💰 USDT pairs: {len(usdt_pairs)}")
            print(f"⭐ Priority pairs found: {len(common_found)}/{len(priority_pairs)}")
            print(f"⚡ Response time: {response_time:.2f}s")
            
            await bitget.close()
            
        except Exception as e:
            self.results['error'] = str(e)
            self.results['success'] = False
            print(f"❌ Ошибка подключения к Bitget: {e}")
            
    async def load_common_pairs_validation(self):
        """Проверяет что общие пары OKX-Bitget действительно доступны на Bitget"""
        print("\n🔍 Проверка общих пар OKX-Bitget...")
        
        try:
            # Загружаем список общих пар
            with open('common_pairs_okx_bitget.json', 'r') as f:
                common_data = json.load(f)
                common_pairs = common_data.get('common_pairs', [])
                
            print(f"📋 Общих пар в файле: {len(common_pairs)}")
            
            # Проверим первые 10 пар на доступность
            bitget = ccxt.bitget({
                'apiKey': '',
                'secret': '',
                'password': '',
                'sandbox': False,
                'enableRateLimit': True,
                'options': {'defaultType': 'spot'}
            })
            
            markets = bitget.load_markets()
            spot_markets = {symbol for symbol, market in markets.items() 
                           if market['type'] == 'spot' and market['active']}
            
            available_common = [pair for pair in common_pairs[:10] if pair in spot_markets]
            
            print(f"✅ Первые 10 общих пар доступны на Bitget: {len(available_common)}/10")
            print(f"🎯 Примеры: {available_common[:5]}")
            
            await bitget.close()
            
        except Exception as e:
            print(f"⚠️  Ошибка при проверке общих пар: {e}")
    
    def save_results(self):
        """Сохраняет результаты тестирования"""
        with open('bitget_pairs_test_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        print(f"\n📝 Результаты сохранены в bitget_pairs_test_results.json")
        
    def print_summary(self):
        """Выводит итоговую сводку"""
        print("\n" + "="*50)
        print("📊 ИТОГОВАЯ СВОДКА ТЕСТИРОВАНИЯ BITGET")
        print("="*50)
        print(f"🔗 Подключение: {'✅ OK' if self.results['success'] else '❌ FAIL'}")
        print(f"📈 Всего SPOT пар: {self.results['total_pairs']}")
        print(f"💰 USDT пар: {self.results['usdt_pairs']}")
        print(f"⭐ Приоритетных пар найдено: {self.results['common_pairs_found']}")
        if self.results['api_response_time'] is not None:
            print(f"⚡ Время отклика API: {self.results['api_response_time']:.2f}s")
        else:
            print("⚡ Время отклика API: N/A")
        
        if self.results['error']:
            print(f"❌ Ошибка: {self.results['error']}")
            
        if self.results['sample_pairs']:
            print(f"\n🎯 Примеры доступных USDT пар:")
            for i, pair in enumerate(self.results['sample_pairs'][:10], 1):
                print(f"   {i:2d}. {pair}")

async def main():
    print("🚀 Запуск тестирования загрузки пар Bitget...")
    print(f"⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    tester = BitgetPairsTest()
    
    try:
        await tester.test_bitget_connection()
        await tester.load_common_pairs_validation()
        
    except KeyboardInterrupt:
        print("\n⏹️ Тестирование прервано пользователем")
        
    finally:
        tester.save_results()
        tester.print_summary()
        print("\n🏁 Тестирование завершено!")

if __name__ == "__main__":
    asyncio.run(main())
