#!/usr/bin/env python3
"""
Тест REST API Binance через прокси
"""
import asyncio
import os
import sys
sys.path.append('.')

import config
from exchanges.binance import BinanceExchange

async def test_rest_api():
    """Тест REST API подключения к Binance через прокси"""
    print("=== Тест REST API Binance через прокси ===")
    
    # Создаем клиент
    api_config = config.EXCHANGES['binance']['API_CONFIG']
    client = BinanceExchange(api_config)
    
    try:
        # Инициализируем клиент без WebSocket
        print("Создание AsyncClient...")
        from binance import AsyncClient
        
        if config.PROXY_URL:
            print(f"Настройка прокси: {config.PROXY_URL}")
            os.environ['HTTP_PROXY'] = config.PROXY_URL
            os.environ['HTTPS_PROXY'] = config.PROXY_URL
        
        client.client = await AsyncClient.create(
            api_key=client.api_key,
            api_secret=client.api_secret
        )
        
        print("✅ Клиент создан успешно")
        
        # Тест 1: Получение информации о сервере
        print("\n--- Тест 1: Ping сервера ---")
        ping = await client.client.ping()
        print(f"✅ Ping успешен: {ping}")
        
        # Тест 2: Получение времени сервера
        print("\n--- Тест 2: Время сервера ---")
        server_time = await client.client.get_server_time()
        print(f"✅ Время сервера: {server_time}")
        
        # Тест 3: Получение тикера
        print("\n--- Тест 3: Тикер BTC/USDT ---")
        ticker = await client.get_ticker('BTC/USDT')
        print(f"✅ Тикер получен: {ticker}")
        
        # Тест 4: Получение информации об аккаунте
        print("\n--- Тест 4: Информация об аккаунте ---")
        account = await client.client.get_account()
        print(f"✅ Аккаунт: Балансы получены ({len(account['balances'])} валют)")
        
        print("\n🎉 ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
        print("REST API Binance работает через прокси!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    
    finally:
        if client.client:
            await client.client.close_connection()
            print("Соединение закрыто")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_rest_api())
    sys.exit(0 if success else 1)
