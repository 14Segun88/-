#!/usr/bin/env python3
"""
Тест CCXT интеграции для создания ордеров на OKX, Bitget, Phemex
Проверяет подключения и создание demo-ордеров
"""

import asyncio
import logging
from exchange_connector import ExchangeConnector
from production_config import TRADING_CONFIG

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('CCXT_Test')

async def test_ccxt_integration():
    """Тестирование CCXT интеграции для создания ордеров"""
    logger.info("🚀 Тестирование CCXT интеграции для создания ордеров")
    
    # Инициализация коннектора в demo режиме
    connector = ExchangeConnector(mode='demo')
    
    # Тестируемые биржи и пары
    test_exchanges = ['okx', 'bitget', 'phemex']
    test_pairs = ['BTC/USDT', 'ETH/USDT']
    
    try:
        # Инициализация бирж
        await connector.initialize(test_exchanges)
        
        # Проверка подключений
        connected_exchanges = []
        for exchange_id in test_exchanges:
            if connector.is_connected.get(exchange_id, False):
                connected_exchanges.append(exchange_id)
                logger.info(f"✅ {exchange_id.upper()}: Подключение активно")
            else:
                logger.warning(f"⚠️ {exchange_id.upper()}: Подключение неактивно")
        
        if not connected_exchanges:
            logger.error("❌ Ни одна биржа не подключена. Тест прерван.")
            return
        
        # Тест получения балансов
        logger.info("\n📊 Проверка балансов:")
        for exchange_id in connected_exchanges:
            try:
                balance = await connector.fetch_balance(exchange_id)
                if balance:
                    usdt_balance = balance.get('USDT', {})
                    logger.info(f"💰 {exchange_id.upper()} USDT: {usdt_balance.get('free', 0):.2f}")
                else:
                    logger.warning(f"⚠️ {exchange_id.upper()}: Не удалось получить баланс")
            except Exception as e:
                logger.error(f"❌ {exchange_id.upper()} баланс ошибка: {e}")
        
        # Тест получения orderbook
        logger.info("\n📈 Проверка orderbook:")
        orderbook_data = {}
        for exchange_id in connected_exchanges:
            orderbook_data[exchange_id] = {}
            for pair in test_pairs:
                try:
                    orderbook = await connector.fetch_orderbook(exchange_id, pair)
                    if orderbook and orderbook.get('bids') and orderbook.get('asks'):
                        best_bid = orderbook['bids'][0][0]
                        best_ask = orderbook['asks'][0][0]
                        spread = ((best_ask - best_bid) / best_ask) * 100
                        orderbook_data[exchange_id][pair] = {'bid': best_bid, 'ask': best_ask, 'spread': spread}
                        logger.info(f"📊 {exchange_id.upper()} {pair}: bid={best_bid:.6f}, ask={best_ask:.6f}, spread={spread:.3f}%")
                    else:
                        logger.warning(f"⚠️ {exchange_id.upper()} {pair}: Пустой orderbook")
                except Exception as e:
                    logger.error(f"❌ {exchange_id.upper()} {pair} orderbook: {e}")
        
        # Тест создания maker ордеров
        logger.info("\n💡 Проверка расчёта maker цен:")
        for exchange_id in connected_exchanges:
            for pair in test_pairs:
                if pair in orderbook_data.get(exchange_id, {}):
                    try:
                        # Тест расчёта maker цены для покупки
                        buy_price = await connector.calculate_maker_price(exchange_id, pair, 'buy')
                        if buy_price:
                            logger.info(f"💡 {exchange_id.upper()} {pair} BUY maker price: {buy_price:.6f}")
                        
                        # Тест расчёта maker цены для продажи
                        sell_price = await connector.calculate_maker_price(exchange_id, pair, 'sell')
                        if sell_price:
                            logger.info(f"💡 {exchange_id.upper()} {pair} SELL maker price: {sell_price:.6f}")
                    except Exception as e:
                        logger.error(f"❌ {exchange_id.upper()} {pair} maker price: {e}")
        
        # Тест создания demo ордеров (небольшие суммы)
        logger.info("\n📝 Тестирование создания demo ордеров:")
        test_amount = 0.001  # Очень маленькая сумма для теста
        
        for exchange_id in connected_exchanges[:1]:  # Тестируем только на первой доступной бирже
            for pair in test_pairs[:1]:  # Только первую пару
                if pair in orderbook_data.get(exchange_id, {}):
                    try:
                        # Тест market ордера
                        logger.info(f"🔄 Создание MARKET buy ордера: {exchange_id.upper()} {pair}")
                        market_order = await connector.create_order(
                            exchange_id=exchange_id,
                            symbol=pair,
                            side='buy',
                            amount=test_amount,
                            order_type='market',
                            use_maker=False
                        )
                        
                        if market_order:
                            logger.info(f"✅ Market ордер создан: {market_order['id']}")
                            if 'fee' in market_order:
                                fee_info = market_order['fee']
                                logger.info(f"💸 Комиссия: {fee_info.get('cost', 0):.6f} {fee_info.get('currency', 'USDT')} ({fee_info.get('type', 'taker')})")
                        else:
                            logger.warning(f"⚠️ Market ордер не создан")
                        
                        # Тест maker ордера
                        logger.info(f"🔄 Создание LIMIT maker ордера: {exchange_id.upper()} {pair}")
                        limit_order = await connector.create_order(
                            exchange_id=exchange_id,
                            symbol=pair,
                            side='buy',
                            amount=test_amount,
                            order_type='limit',
                            use_maker=True
                        )
                        
                        if limit_order:
                            logger.info(f"✅ Limit ордер создан: {limit_order['id']} по цене {limit_order.get('price', 'N/A')}")
                            if 'fee' in limit_order:
                                fee_info = limit_order['fee']
                                logger.info(f"💸 Комиссия: {fee_info.get('cost', 0):.6f} {fee_info.get('currency', 'USDT')} ({fee_info.get('type', 'maker')})")
                                if 'maker_savings' in limit_order:
                                    logger.info(f"💰 Экономия maker: {limit_order['maker_savings']:.4f}%")
                        else:
                            logger.warning(f"⚠️ Limit ордер не создан")
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка создания ордера {exchange_id.upper()} {pair}: {e}")
        
        logger.info("\n✅ Тест CCXT интеграции завершён")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка теста: {e}")
    finally:
        # Закрытие подключений
        for exchange in connector.exchanges.values():
            try:
                await exchange.close()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(test_ccxt_integration())
