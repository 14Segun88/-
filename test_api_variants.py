#!/usr/bin/env python3
import ccxt
import os
import asyncio

async def test_okx_variants():
    """Тестируем разные варианты подключения OKX"""
    print("🔍 Тестирование OKX с разными паспрофразами...")
    
    passphrases = ["Egor1998!", "Egor1998", "0502794579Egor"]
    
    for i, passphrase in enumerate(passphrases):
        print(f"  Вариант {i+1}: passphrase = '{passphrase}'")
        try:
            okx = ccxt.okx({
                'apiKey': 'ab4f2fe8-e2c4-4d18-9712-d21c8f2f187c',
                'secret': 'FC63C15B1D2DB5C73632ED5BACE49290',
                'password': passphrase,
                'sandbox': False,
                'enableRateLimit': True,
            })
            markets = okx.load_markets()
            print(f"  ✅ Успех! Загружено {len(markets)} рынков")
            
            # Проверяем баланс
            balance = okx.fetch_balance()
            print(f"  💰 Баланс получен")
            return True
            
        except Exception as e:
            error_str = str(e)[:120]
            print(f"  ❌ Ошибка: {error_str}")
    
    return False

async def test_bitget_environments():
    """Тестируем разные среды Bitget"""
    print("🔍 Тестирование Bitget...")
    
    configs = [
        {'sandbox': False, 'test': False, 'name': 'Production'},
        {'sandbox': True, 'test': True, 'name': 'Testnet'},
    ]
    
    for config in configs:
        print(f"  Среда: {config['name']}")
        try:
            bitget = ccxt.bitget({
                'apiKey': 'bg_1d2ce1e1b74f17527e88d0aaff6609a0',
                'secret': '311ad3c3d52e3caa1af61f27049fc0dcefce16ec94192eb7795698fc1f5ef4da',
                'password': '0502794579Egor',
                'sandbox': config['sandbox'],
                'test': config['test'],
                'enableRateLimit': True,
            })
            
            markets = bitget.load_markets()
            print(f"  ✅ Рынки загружены: {len(markets)}")
            
            balance = bitget.fetch_balance()
            print(f"  ✅ Баланс получен")
            return True
            
        except Exception as e:
            error_str = str(e)[:120]
            print(f"  ❌ Ошибка: {error_str}")
    
    return False

async def test_phemex_environments():
    """Тестируем разные среды Phemex"""
    print("🔍 Тестирование Phemex...")
    
    configs = [
        {'sandbox': False, 'name': 'Production'},
        {'sandbox': True, 'name': 'Testnet'},
    ]
    
    for config in configs:
        print(f"  Среда: {config['name']}")
        try:
            phemex = ccxt.phemex({
                'apiKey': 'f78a12fd-2582-4e76-95dc-19eef5d37971',
                'secret': 'KE-YNJayBvL9Zpde-k0u68iuUiDEy13NJDBzxv82JPBkMWU2ODZiMS1mYmQyLTQ2MGMtYjA3Ny1hYWQ0NmFlOGYxNjk',
                'sandbox': config['sandbox'],
                'enableRateLimit': True,
            })
            
            markets = phemex.load_markets()
            print(f"  ✅ Рынки загружены: {len(markets)}")
            
            balance = phemex.fetch_balance()
            print(f"  ✅ Баланс получен")
            return True
            
        except Exception as e:
            error_str = str(e)[:120]
            print(f"  ❌ Ошибка: {error_str}")
    
    return False

async def main():
    print("🔑 ДИАГНОСТИКА API КЛЮЧЕЙ")
    print("=" * 50)
    
    okx_ok = await test_okx_variants()
    bitget_ok = await test_bitget_environments() 
    phemex_ok = await test_phemex_environments()
    
    print("\n📊 РЕЗУЛЬТАТ ДИАГНОСТИКИ:")
    print(f"  OKX: {'✅ Работает' if okx_ok else '❌ Не работает'}")
    print(f"  Bitget: {'✅ Работает' if bitget_ok else '❌ Не работает'}")
    print(f"  Phemex: {'✅ Работает' if phemex_ok else '❌ Не работает'}")
    
    working = sum([okx_ok, bitget_ok, phemex_ok])
    print(f"\n🎯 Готовых бирж: {working}/3")
    
    if working >= 2:
        print("✅ Достаточно для запуска арбитражного бота!")
    else:
        print("⚠️ Нужны дополнительные настройки")

if __name__ == "__main__":
    asyncio.run(main())
