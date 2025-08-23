#!/usr/bin/env python3
import ccxt
import json
import time

def test_okx_comprehensive():
    """Комплексное тестирование OKX с различными подходами"""
    print("🔬 КОМПЛЕКСНАЯ ДИАГНОСТИКА OKX API")
    print("=" * 50)
    
    # Доступные API ключи
    api_variants = [
        {
            'name': 'Новые ключи',
            'api_key': '352206e1-5463-453f-9a52-18cab50ec146',
            'secret': 'D5C10767153C75D5FCA193D249FB1747',
            'passphrase': 'Egor1998!'
        }
    ]
    
    # Различные паспрофразы для тестирования
    passphrase_variants = ['Egor1998!', 'Egor1998', '0502794579Egor']
    
    # Различные конфигурации среды
    env_configs = [
        {'sandbox': True, 'name': 'Testnet'},
        {'sandbox': False, 'name': 'Production'},
    ]
    
    # Дополнительные настройки
    additional_configs = [
        {'timeout': 30000, 'rateLimit': 1000},
        {'timeout': 60000, 'rateLimit': 2000},
        {'enableRateLimit': False, 'timeout': 20000},
    ]
    
    print(f"💡 Версия CCXT: {ccxt.__version__}")
    print()
    
    success_count = 0
    test_count = 0
    
    for api_data in api_variants:
        print(f"🔑 Тестирование: {api_data['name']}")
        
        for passphrase in passphrase_variants:
            for env_config in env_configs:
                for additional in additional_configs:
                    test_count += 1
                    print(f"\n  Тест {test_count}: {env_config['name']} | Passphrase: '{passphrase}' | Config: {list(additional.keys())}")
                    
                    try:
                        # Создаем конфигурацию
                        config = {
                            'apiKey': api_data['api_key'],
                            'secret': api_data['secret'], 
                            'password': passphrase,
                            'sandbox': env_config['sandbox'],
                            **additional
                        }
                        
                        # Создаем экземпляр OKX
                        okx = ccxt.okx(config)
                        
                        # Тестируем загрузку рынков
                        print(f"    📊 Загрузка рынков...")
                        start_time = time.time()
                        markets = okx.load_markets()
                        load_time = time.time() - start_time
                        
                        print(f"    ✅ УСПЕХ! Рынки: {len(markets)} | Время: {load_time:.2f}с")
                        
                        # Пытаемся получить баланс
                        try:
                            balance = okx.fetch_balance()
                            total_usdt = sum([bal.get('total', 0) for bal in balance.values() if isinstance(bal, dict)])
                            print(f"    💰 Баланс получен: {total_usdt:.2f} USDT")
                            success_count += 1
                            print(f"    🎉 ПОЛНЫЙ УСПЕХ! Конфигурация работает!")
                            
                            # Сохраняем рабочую конфигурацию
                            working_config = {
                                'api_key': api_data['api_key'],
                                'secret': api_data['secret'],
                                'passphrase': passphrase,
                                'sandbox': env_config['sandbox'],
                                'additional': additional
                            }
                            
                            print(f"\n🎯 РАБОЧАЯ КОНФИГУРАЦИЯ НАЙДЕНА:")
                            print(f"   Среда: {env_config['name']}")
                            print(f"   Passphrase: '{passphrase}'")
                            print(f"   Дополнительно: {additional}")
                            return working_config
                            
                        except Exception as balance_error:
                            print(f"    ⚠️ Рынки OK, баланс недоступен: {str(balance_error)[:80]}")
                            print(f"    ✅ Частичный успех - можно использовать для котировок")
                            
                    except Exception as e:
                        error_msg = str(e)[:100]
                        print(f"    ❌ Ошибка: {error_msg}")
                        
                        # Анализируем тип ошибки
                        if "50101" in error_msg:
                            print(f"    🔍 Код 50101: API ключ не соответствует среде")
                        elif "50105" in error_msg:
                            print(f"    🔍 Код 50105: Неверная passphrase")
                        elif "50104" in error_msg:
                            print(f"    🔍 Код 50104: Неверная подпись")
                        elif "50103" in error_msg:
                            print(f"    🔍 Код 50103: Неверный timestamp")
    
    print(f"\n📊 ИТОГИ ТЕСТИРОВАНИЯ:")
    print(f"   Всего тестов: {test_count}")
    print(f"   Успешных: {success_count}")
    print(f"   Успех: {(success_count/test_count)*100:.1f}%")
    
    if success_count == 0:
        print(f"\n❌ НИ ОДНА КОНФИГУРАЦИЯ НЕ РАБОТАЕТ")
        print(f"💡 Рекомендации:")
        print(f"   1. Проверить права API ключа в OKX личном кабинете")
        print(f"   2. Убедиться что IP добавлен в whitelist")
        print(f"   3. Проверить что ключи активны")
        print(f"   4. Попробовать создать новый API ключ")
        return None
    
    return None

def test_ccxt_okx_info():
    """Информация о поддержке OKX в CCXT"""
    print("\n🔍 ИНФОРМАЦИЯ О ПОДДЕРЖКЕ OKX:")
    print("=" * 40)
    
    try:
        # Создаем временный экземпляр без ключей
        okx = ccxt.okx()
        
        print(f"✅ Версия CCXT: {ccxt.__version__}")
        print(f"✅ OKX поддерживается: {hasattr(ccxt, 'okx')}")
        print(f"✅ OKX sandbox поддержка: {hasattr(okx, 'set_sandbox_mode')}")
        print(f"✅ Доступные методы: {len([m for m in dir(okx) if not m.startswith('_')])}")
        
        # Проверяем доступность публичных API
        try:
            ticker = okx.fetch_ticker('BTC/USDT')
            print(f"✅ Публичные API работают: BTC/USDT = ${ticker['last']:.2f}")
        except Exception as e:
            print(f"⚠️ Публичные API недоступны: {str(e)[:60]}")
            
    except Exception as e:
        print(f"❌ Ошибка создания OKX экземпляра: {e}")

if __name__ == "__main__":
    test_ccxt_okx_info()
    working_config = test_okx_comprehensive()
    
    if working_config:
        print(f"\n🎉 КОНФИГУРАЦИЯ СОХРАНЕНА И ГОТОВА К ИСПОЛЬЗОВАНИЮ!")
    else:
        print(f"\n⚠️ ТРЕБУЕТСЯ ДОПОЛНИТЕЛЬНАЯ ДИАГНОСТИКА")
