#!/usr/bin/env python3
import ccxt
import os
import asyncio

async def test_testnet_connections():
    """Тестируем подключения в testnet/sandbox режимах"""
    print("🧪 ТЕСТИРОВАНИЕ TESTNET/SANDBOX ПОДКЛЮЧЕНИЙ")
    print("=" * 55)
    
    results = {}
    
    # OKX Testnet (demo keys)
    print("🏦 Тестирование OKX (testnet):")
    try:
        okx = ccxt.okx({
            'apiKey': 'ab4f2fe8-e2c4-4d18-9712-d21c8f2f187c',
            'secret': 'FC63C15B1D2DB5C73632ED5BACE49290',
            'password': 'Egor1998!',
            'sandbox': True,  # Testnet режим
            'enableRateLimit': True,
        })
        markets = okx.load_markets()
        print(f"  ✅ Testnet рынки: {len(markets)} пар")
        
        balance = okx.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        print(f"  ✅ Demo баланс: {usdt_balance} USDT")
        results['okx'] = True
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['okx'] = False
    
    # Bitget Testnet
    print("\n🏦 Тестирование Bitget (testnet):")
    try:
        bitget = ccxt.bitget({
            'apiKey': 'bg_1d2ce1e1b74f17527e88d0aaff6609a0',
            'secret': '311ad3c3d52e3caa1af61f27049fc0dcefce16ec94192eb7795698fc1f5ef4da',
            'password': '0502794579Egor',
            'sandbox': True,  # Testnet режим
            'test': True,
            'enableRateLimit': True,
        })
        
        markets = bitget.load_markets()
        print(f"  ✅ Testnet рынки: {len(markets)} пар")
        
        balance = bitget.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        print(f"  ✅ Demo баланс: {usdt_balance} USDT")
        results['bitget'] = True
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['bitget'] = False
    
    # Phemex Testnet (новые ключи)
    print("\n🏦 Тестирование Phemex (testnet с новыми ключами):")
    try:
        phemex = ccxt.phemex({
            'apiKey': '3f9decb6-b6bf-453f-b27e-087ee595812d',
            'secret': 'bohdKr9wmSL_OBtJtP3T9TcJkTADnqCEKvIRC3znTUs5Y2FkYTg2ZS1iNzMxLTQ4NmQtODk0Ni1mZmFhM2JiMWQ5MWI',
            'sandbox': True,  # Testnet режим
            'enableRateLimit': True,
        })
        
        markets = phemex.load_markets()
        print(f"  ✅ Testnet рынки: {len(markets)} пар")
        
        balance = phemex.fetch_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)
        print(f"  ✅ Demo баланс: {usdt_balance} USDT")
        results['phemex'] = True
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['phemex'] = False
    
    # Итоговый отчет
    print("\n📊 РЕЗУЛЬТАТ TESTNET ТЕСТИРОВАНИЯ:")
    working = sum(1 for r in results.values() if r)
    print(f"  Работающих бирж: {working}/3")
    
    for exchange, status in results.items():
        emoji = "✅" if status else "❌"
        print(f"  {emoji} {exchange.upper()}: {'Работает' if status else 'Не работает'}")
    
    if working >= 2:
        print("\n🎉 Готово к запуску testnet арбитражного бота!")
    else:
        print("\n⚠️ Нужны дополнительные настройки")
    
    return results

if __name__ == "__main__":
    asyncio.run(test_testnet_connections())
