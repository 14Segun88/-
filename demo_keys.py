"""
Demo API Keys for Testing
Демо API ключи для тестирования (НЕ РЕАЛЬНЫЕ!)
"""

import os

def setup_demo_environment():
    """Устанавливает демо переменные окружения для тестирования"""
    
    # ВНИМАНИЕ: Это НЕ реальные ключи, только для демо!
    demo_keys = {
        # Binance demo
        'BINANCE_API_KEY': 'DEMO_BINANCE_KEY_FOR_TESTING_ONLY',
        'BINANCE_API_SECRET': 'DEMO_BINANCE_SECRET_FOR_TESTING_ONLY',
        
        # Bybit demo
        'BYBIT_API_KEY': 'DEMO_BYBIT_KEY_FOR_TESTING_ONLY',
        'BYBIT_API_SECRET': 'DEMO_BYBIT_SECRET_FOR_TESTING_ONLY',
        
        # KuCoin demo
        'KUCOIN_API_KEY': 'DEMO_KUCOIN_KEY_FOR_TESTING_ONLY',
        'KUCOIN_API_SECRET': 'DEMO_KUCOIN_SECRET_FOR_TESTING_ONLY',
        'KUCOIN_API_PASSPHRASE': 'DEMO_PASSPHRASE',
        
        # OKX demo
        'OKX_API_KEY': 'DEMO_OKX_KEY_FOR_TESTING_ONLY',
        'OKX_API_SECRET': 'DEMO_OKX_SECRET_FOR_TESTING_ONLY',
        'OKX_API_PASSPHRASE': 'DEMO_PASSPHRASE',
        
        # MEXC demo
        'MEXC_API_KEY': 'DEMO_MEXC_KEY_FOR_TESTING_ONLY',
        'MEXC_API_SECRET': 'DEMO_MEXC_SECRET_FOR_TESTING_ONLY'
    }
    
    # Устанавливаем переменные окружения
    for key, value in demo_keys.items():
        os.environ[key] = value
    
    print("✅ Демо окружение настроено (используются тестовые ключи)")
    print("⚠️ ВНИМАНИЕ: Это НЕ реальные API ключи, только для демо!")
    
    return demo_keys

# Автоматически настраиваем при импорте
if __name__ != "__main__":
    setup_demo_environment()
