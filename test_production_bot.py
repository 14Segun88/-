#!/usr/bin/env python3
"""
Тестовый запуск production бота
"""

import asyncio
import logging
import sys
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('TestBot')

async def test_websocket_connections():
    """Тест WebSocket подключений"""
    logger.info("=" * 60)
    logger.info("🚀 ТЕСТИРОВАНИЕ PRODUCTION БОТА")
    logger.info("=" * 60)
    
    try:
        # Импортируем после настройки логирования
        from websocket_manager import WebSocketManager
        from trading_engine import TradingEngine
        
        logger.info("✅ Модули успешно импортированы")
        
        # Создаем менеджер WebSocket
        ws_manager = WebSocketManager()
        logger.info("✅ WebSocketManager создан")
        
        # Создаем торговый движок
        trading_engine = TradingEngine()
        logger.info("✅ TradingEngine создан")
        
        # Тестируем получение активных бирж
        from production_config import EXCHANGES_CONFIG
        active_exchanges = [ex for ex, conf in EXCHANGES_CONFIG.items() if conf['enabled']]
        logger.info(f"📊 Активные биржи: {active_exchanges}")
        
        # Тестируем динамический поиск пар
        logger.info("\n🔍 Тестирование динамического поиска пар...")
        
        # Для MEXC
        if 'mexc' in active_exchanges:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    url = "https://api.mexc.com/api/v3/ticker/24hr"
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            usdt_pairs = [t['symbol'] for t in data if t['symbol'].endswith('USDT')][:5]
                            logger.info(f"✅ MEXC: найдено {len(data)} пар, примеры USDT: {usdt_pairs}")
                        else:
                            logger.error(f"❌ MEXC API error: {resp.status}")
                except Exception as e:
                    logger.error(f"❌ MEXC connection error: {e}")
        
        # Для Bybit
        if 'bybit' in active_exchanges:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    url = "https://api.bybit.com/v5/market/tickers"
                    params = {'category': 'spot'}
                    async with session.get(url, params=params, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get('result'):
                                tickers = data['result'].get('list', [])
                                usdt_pairs = [t['symbol'] for t in tickers if t['symbol'].endswith('USDT')][:5]
                                logger.info(f"✅ Bybit: найдено {len(tickers)} пар, примеры USDT: {usdt_pairs}")
                        else:
                            logger.error(f"❌ Bybit API error: {resp.status}")
                except Exception as e:
                    logger.error(f"❌ Bybit connection error: {e}")
        
        # Тестируем WebSocket подключения
        logger.info("\n🌐 Тестирование WebSocket подключений...")
        
        # Подключаемся к биржам
        test_pairs = ['BTC/USDT', 'ETH/USDT']
        logger.info(f"📝 Тестовые пары: {test_pairs}")
        
        # Запускаем WebSocket для тестовых пар
        await ws_manager.start(test_pairs)
        logger.info("✅ WebSocket manager запущен")
        
        # Ждем 5 секунд для получения данных
        logger.info("⏳ Ожидание данных (5 секунд)...")
        await asyncio.sleep(5)
        
        # Проверяем статистику
        stats = ws_manager.get_statistics()
        logger.info("\n📊 СТАТИСТИКА WEBSOCKET:")
        logger.info(f"  Сообщений получено: {stats['messages_received']}")
        logger.info(f"  Ошибок: {stats['errors']}")
        logger.info(f"  Подключено бирж: {stats['connected_exchanges']}")
        
        # Проверяем ордербуки
        logger.info("\n📚 ПОЛУЧЕННЫЕ ОРДЕРБУКИ:")
        for symbol in test_pairs:
            books = ws_manager.get_orderbooks(symbol)
            if books:
                for exchange, book in books.items():
                    if book and book.bids and book.asks:
                        logger.info(f"  {symbol} на {exchange}:")
                        logger.info(f"    Bid: ${book.bids[0][0]:.2f}")
                        logger.info(f"    Ask: ${book.asks[0][0]:.2f}")
                        logger.info(f"    Spread: {(book.asks[0][0] - book.bids[0][0])/book.bids[0][0]*100:.3f}%")
        
        # Останавливаем
        logger.info("\n🛑 Остановка тестового бота...")
        await ws_manager.stop()
        
        logger.info("✅ ТЕСТ ЗАВЕРШЕН УСПЕШНО")
        
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта: {e}")
    except Exception as e:
        logger.error(f"❌ Общая ошибка: {e}", exc_info=True)

async def main():
    """Главная функция"""
    try:
        await test_websocket_connections()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Получен сигнал остановки")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    logger.info(f"🕐 Запуск теста: {datetime.now()}")
    asyncio.run(main())
