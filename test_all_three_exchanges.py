#!/usr/bin/env python3
import ccxt
import os
import asyncio

async def test_complete_setup():
    """Тестируем полную настройку всех 3 бирж"""
    print("🔑 ТЕСТИРОВАНИЕ ПОЛНОЙ НАСТРОЙКИ ВСЕХ 3 БИРЖ")
    print("=" * 60)
    
    results = {}
    
    # OKX с новыми ключами
    print("🏦 Тестирование OKX (новые ключи):")
    try:
        okx = ccxt.okx({
            'apiKey': '352206e1-5463-453f-9a52-18cab50ec146',
            'secret': 'D5C10767153C75D5FCA193D249FB1747',
            'password': 'Egor1998!',
            'sandbox': True,  # Testnet режим
            'enableRateLimit': True,
        })
        
        markets = okx.load_markets()
        print(f"  ✅ Testnet рынки: {len(markets)} пар")
        
        try:
            balance = okx.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            print(f"  ✅ Demo баланс: {usdt_balance} USDT")
            results['okx'] = 'full'
        except Exception as be:
            print(f"  ⚠️ Рынки работают, баланс недоступен: {str(be)[:80]}")
            results['okx'] = 'partial'
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['okx'] = False
    
    # Bitget
    print("\n🏦 Тестирование Bitget:")
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
        
        try:
            balance = bitget.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            print(f"  ✅ Demo баланс: {usdt_balance} USDT")
            results['bitget'] = 'full'
        except Exception as be:
            print(f"  ⚠️ Рынки работают, баланс недоступен: {str(be)[:80]}")
            results['bitget'] = 'partial'
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['bitget'] = False
    
    # Phemex
    print("\n🏦 Тестирование Phemex:")
    try:
        phemex = ccxt.phemex({
            'apiKey': '3f9decb6-b6bf-453f-b27e-087ee595812d',
            'secret': 'bohdKr9wmSL_OBtJtP3T9TcJkTADnqCEKvIRC3znTUs5Y2FkYTg2ZS1iNzMxLTQ4NmQtODk0Ni1mZmFhM2JiMWQ5MWI',
            'sandbox': True,  # Testnet режим
            'enableRateLimit': True,
        })
        
        markets = phemex.load_markets()
        print(f"  ✅ Testnet рынки: {len(markets)} пар")
        
        try:
            balance = phemex.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            print(f"  ✅ Demo баланс: {usdt_balance} USDT")
            results['phemex'] = 'full'
        except Exception as be:
            print(f"  ⚠️ Рынки работают, баланс недоступен: {str(be)[:80]}")
            results['phemex'] = 'partial'
        
    except Exception as e:
        error_str = str(e)[:120]
        print(f"  ❌ Ошибка: {error_str}")
        results['phemex'] = False
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ:")
    
    full_working = sum(1 for r in results.values() if r == 'full')
    partial_working = sum(1 for r in results.values() if r == 'partial')
    total_working = full_working + partial_working
    
    print(f"  ✅ Полностью работающих: {full_working}/3")
    print(f"  ⚠️ Частично работающих: {partial_working}/3") 
    print(f"  🎯 Всего готовых: {total_working}/3")
    
    for exchange, status in results.items():
        if status == 'full':
            emoji = "✅"
            status_text = "Полностью готов"
        elif status == 'partial':
            emoji = "⚠️"
            status_text = "Частично готов"
        else:
            emoji = "❌"
            status_text = "Не готов"
        print(f"  {emoji} {exchange.upper()}: {status_text}")
    
    if total_working >= 2:
        print(f"\n🎉 ГОТОВО! {total_working} бирж готовы к testnet арбитражу!")
        return True
    else:
        print(f"\n⚠️ Недостаточно бирж ({total_working}) для стабильной работы")
        return False

if __name__ == "__main__":
    asyncio.run(test_complete_setup())
