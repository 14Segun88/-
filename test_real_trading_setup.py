#!/usr/bin/env python3
"""
🚀 ТЕСТ НАСТРОЙКИ РЕАЛЬНОЙ ТОРГОВЛИ
Проверка подключения к реальным счетам OKX, Bitget, Phemex
"""

import asyncio
import ccxt
import os
from production_config import API_KEYS, TRADING_CONFIG

async def test_real_trading_setup():
    """Тестирование настройки реальной торговли на всех 3 биржах"""
    
    print("🚀 ТЕСТИРОВАНИЕ НАСТРОЙКИ РЕАЛЬНОЙ ТОРГОВЛИ")
    print(f"Режим торговли: {TRADING_CONFIG['mode']}")
    print("=" * 60)
    
    exchanges_to_test = ['okx', 'bitget', 'phemex']
    results = {}
    
    for exchange_name in exchanges_to_test:
        print(f"\n🏦 Тестирование {exchange_name.upper()}:")
        
        try:
            # Получаем API ключи
            api_config = API_KEYS.get(exchange_name, {})
            if not api_config.get('apiKey'):
                print(f"  ❌ API ключи не найдены для {exchange_name}")
                results[exchange_name] = False
                continue
                
            # Создаем экземпляр биржи
            exchange_class = getattr(ccxt, exchange_name)
            exchange = exchange_class({
                'apiKey': api_config.get('apiKey', ''),
                'secret': api_config.get('secret', ''),
                'password': api_config.get('passphrase', ''),
                'sandbox': False,  # Реальный режим
                'enableRateLimit': True,
            })
            
            # Убираем все demo заголовки
            if not hasattr(exchange, 'headers') or exchange.headers is None:
                exchange.headers = {}
                
            if exchange_name == 'okx':
                exchange.headers.pop('x-simulated-trading', None)
                print("  ✅ OKX: demo заголовки убраны")
            elif exchange_name == 'bitget':
                exchange.headers.pop('PAPTRADING', None)
                exchange.headers.pop('paptrading', None)
                print("  ✅ Bitget: demo заголовки убраны")
            elif exchange_name == 'phemex':
                exchange.set_sandbox_mode(False)
                print("  ✅ Phemex: sandbox отключен")
            
            # Загружаем рынки для проверки подключения
            print("  📊 Загрузка рынков...")
            markets = exchange.load_markets()
            usdt_pairs = [s for s in markets.keys() if s.endswith('/USDT')]
            print(f"  ✅ Рынки загружены: {len(usdt_pairs)} USDT пар")
            
            # Проверяем баланс (только чтение)
            print("  💰 Проверка баланса...")
            try:
                balance = exchange.fetch_balance()
                total_balance_usd = 0
                active_assets = 0
                
                for currency, info in balance.items():
                    if isinstance(info, dict) and info.get('total', 0) > 0:
                        active_assets += 1
                        if currency == 'USDT':
                            total_balance_usd += info['total']
                
                print(f"  ✅ Баланс получен: {active_assets} активных активов")
                if total_balance_usd > 0:
                    print(f"  💵 USDT баланс: {total_balance_usd:.2f}")
                
                results[exchange_name] = True
                
            except Exception as be:
                print(f"  ⚠️ Ошибка получения баланса: {str(be)[:100]}")
                results[exchange_name] = 'partial'  # Рынки работают, баланс проблема
                
            # await exchange.close()  # Не все биржи поддерживают async close
            
        except Exception as e:
            print(f"  ❌ Ошибка подключения: {str(e)[:150]}")
            results[exchange_name] = False
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ:")
    
    successful = sum(1 for r in results.values() if r is True)
    partial = sum(1 for r in results.values() if r == 'partial')  
    failed = sum(1 for r in results.values() if r is False)
    
    print(f"  ✅ Полностью готовы: {successful}/3")
    print(f"  ⚠️ Частично готовы: {partial}/3") 
    print(f"  ❌ Не готовы: {failed}/3")
    
    for exchange_name, status in results.items():
        status_emoji = "✅" if status is True else "⚠️" if status == 'partial' else "❌"
        print(f"  {status_emoji} {exchange_name.upper()}: {'Готов' if status is True else 'Частично готов' if status == 'partial' else 'Не готов'}")
    
    if successful >= 2:
        print("\n🎉 СИСТЕМА ГОТОВА К РЕАЛЬНОЙ ТОРГОВЛЕ!")
        print("⚠️ ВНИМАНИЕ: Это будут РЕАЛЬНЫЕ сделки с вашими деньгами")
        print("💡 Рекомендация: начните с малых сумм для тестирования")
    else:
        print("\n⚠️ НЕОБХОДИМЫ ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ")
        print("❌ Система не готова к реальной торговле")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_real_trading_setup())
