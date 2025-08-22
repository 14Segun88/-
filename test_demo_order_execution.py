#!/usr/bin/env python3
"""
Тест исполнения demo-ордеров на реальных брокерских demo-счетах
Проверяет OKX и Bitget в demo режиме
"""

import asyncio
import time
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG, API_KEYS

async def test_demo_order_execution():
    """Тест создания и отслеживания demo-ордеров"""
    
    print("🧪 ТЕСТ DEMO-ОРДЕРОВ НА РЕАЛЬНЫХ БРОКЕРСКИХ СЧЕТАХ")
    print("=" * 60)
    
    # Инициализация в demo режиме
    connector = ExchangeConnector(mode='demo')
    
    try:
        # Инициализация
        await connector.initialize()
        print("✅ ExchangeConnector инициализирован в demo режиме")
        
        # Тестовые параметры
        test_symbol = 'BTC/USDT'
        test_volume = 0.001  # Минимальный объем для теста
        
        # Биржи для тестирования (только с demo API ключами)
        test_exchanges = []
        if API_KEYS.get('okx', {}).get('apiKey'):
            test_exchanges.append('okx')
        if API_KEYS.get('bitget', {}).get('apiKey'):
            test_exchanges.append('bitget')
            
        if not test_exchanges:
            print("❌ Нет API ключей для demo тестирования")
            return
            
        print(f"🎯 Тестируемые биржи: {test_exchanges}")
        print(f"🔸 Символ: {test_symbol}")
        print(f"🔸 Объем: {test_volume} BTC")
        
        # Проверка балансов
        print(f"\n📊 Проверка demo-балансов:")
        for exchange_id in test_exchanges:
            try:
                balance = await connector.fetch_balance(exchange_id)
                if balance:
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    btc_balance = balance.get('BTC', {}).get('free', 0)
                    print(f"  💰 {exchange_id.upper()}: {usdt_balance:.2f} USDT, {btc_balance:.6f} BTC")
                else:
                    print(f"  ⚠️ {exchange_id.upper()}: баланс недоступен")
            except Exception as e:
                print(f"  ❌ {exchange_id.upper()}: ошибка баланса - {e}")
        
        # Получение текущих цен
        print(f"\n📈 Получение текущих цен:")
        current_prices = {}
        for exchange_id in test_exchanges:
            try:
                orderbook = await connector.fetch_orderbook(exchange_id, test_symbol)
                if orderbook and orderbook.get('asks'):
                    current_price = orderbook['asks'][0][0]
                    current_prices[exchange_id] = current_price
                    print(f"  💸 {exchange_id.upper()}: {current_price:.2f} USDT")
                else:
                    print(f"  ⚠️ {exchange_id.upper()}: цена недоступна")
            except Exception as e:
                print(f"  ❌ {exchange_id.upper()}: ошибка цены - {e}")
        
        if not current_prices:
            print("❌ Не удалось получить цены для тестирования")
            return
        
        # Тест создания market BUY ордеров
        print(f"\n🛒 Тест создания DEMO BUY ордеров:")
        created_orders = {}
        
        for exchange_id in test_exchanges:
            if exchange_id not in current_prices:
                continue
                
            try:
                print(f"  📝 Создание BUY ордера на {exchange_id.upper()}...")
                
                # Создаем market buy ордер
                result = await connector.create_order(
                    exchange_id=exchange_id,
                    symbol=test_symbol,
                    order_type='market',
                    side='buy',
                    amount=test_volume,
                    price=None  # Market ордер
                )
                
                if result and result.get('id'):
                    order_id = result['id']
                    created_orders[exchange_id] = order_id
                    print(f"  ✅ {exchange_id.upper()}: ордер создан - {order_id}")
                    print(f"     📋 Детали: {result}")
                else:
                    print(f"  ❌ {exchange_id.upper()}: ордер не создан - {result}")
                    
            except Exception as e:
                print(f"  ❌ {exchange_id.upper()}: ошибка создания ордера - {e}")
        
        # Проверка статуса ордеров
        if created_orders:
            print(f"\n🔍 Проверка статуса demo-ордеров:")
            await asyncio.sleep(2)  # Пауза для исполнения
            
            for exchange_id, order_id in created_orders.items():
                try:
                    status = await connector.fetch_order_status(exchange_id, order_id, test_symbol)
                    if status:
                        order_status = status.get('status', 'unknown')
                        filled = status.get('filled', 0)
                        print(f"  📊 {exchange_id.upper()}: статус={order_status}, исполнено={filled}")
                        print(f"     📋 Полная информация: {status}")
                    else:
                        print(f"  ⚠️ {exchange_id.upper()}: статус недоступен")
                except Exception as e:
                    print(f"  ❌ {exchange_id.upper()}: ошибка статуса - {e}")
        
        # Финальная проверка балансов
        print(f"\n📊 Финальная проверка demo-балансов:")
        for exchange_id in test_exchanges:
            try:
                balance = await connector.fetch_balance(exchange_id)
                if balance:
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    btc_balance = balance.get('BTC', {}).get('free', 0)
                    print(f"  💰 {exchange_id.upper()}: {usdt_balance:.2f} USDT, {btc_balance:.6f} BTC")
                else:
                    print(f"  ⚠️ {exchange_id.upper()}: баланс недоступен")
            except Exception as e:
                print(f"  ❌ {exchange_id.upper()}: ошибка баланса - {e}")
        
        print(f"\n✅ Тест demo-ордеров завершен")
        
    except Exception as e:
        print(f"❌ Критическая ошибка теста: {e}")
        
    finally:
        # Закрытие
        await connector.close()
        print("🔌 ExchangeConnector закрыт")

if __name__ == "__main__":
    asyncio.run(test_demo_order_execution())
