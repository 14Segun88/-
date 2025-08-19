#!/usr/bin/env python3
"""
🔐 Тестирование API подключений к биржам
"""

import asyncio
import ccxt.async_support as ccxt
from production_config import API_KEYS, PROXY_CONFIG
import aiohttp
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_exchange(exchange_name, config):
    """Тестирование подключения к бирже"""
    exchange = None
    try:
        logger.info(f"\n{'='*50}")
        logger.info(f"🔍 Тестирование {exchange_name}...")
        
        # Создание экземпляра биржи
        exchange_class = getattr(ccxt, exchange_name.lower())
        
        # Настройки для биржи
        exchange_config = {
            'apiKey': config.get('apiKey', ''),
            'secret': config.get('secret', ''),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            }
        }
        
        # Добавляем пароль для бирж, которые его требуют
        if 'password' in config and config['password']:
            exchange_config['password'] = config['password']
        
        # Настройка прокси для разных бирж
        if PROXY_CONFIG.get('enabled'):
            # Выбираем прокси в зависимости от биржи
            if exchange_name.upper() in ['HUOBI', 'OKX']:
                # Азиатские биржи - используем Japan прокси
                proxy = PROXY_CONFIG['japan']['https']
                logger.info(f"  📡 Используется Japan прокси для {exchange_name}")
            elif exchange_name.upper() in ['BINANCE', 'BYBIT']:
                # Заблокированные биржи - используем Netherlands прокси
                proxy = PROXY_CONFIG['netherlands']['https']
                logger.info(f"  📡 Используется Netherlands прокси для {exchange_name}")
            else:
                # Остальные - без прокси или Estonia
                proxy = None
            
            if proxy:
                exchange_config['proxies'] = {
                    'http': proxy,
                    'https': proxy
                }
                exchange_config['aiohttp_proxy'] = proxy
        
        exchange = exchange_class(exchange_config)
        
        # Проверка публичного API
        logger.info(f"  📊 Проверка публичного API...")
        markets = await exchange.load_markets()
        logger.info(f"  ✅ Загружено {len(markets)} рынков")
        
        # Получение тикера для популярной пары
        test_symbol = 'BTC/USDT'
        if test_symbol in markets:
            ticker = await exchange.fetch_ticker(test_symbol)
            logger.info(f"  💹 {test_symbol}: ${ticker['last']:.2f}")
        
        # Проверка приватного API если есть ключи
        if config.get('apiKey'):
            logger.info(f"  🔐 Проверка приватного API...")
            try:
                balance = await exchange.fetch_balance()
                usdt_balance = balance.get('USDT', {}).get('free', 0)
                logger.info(f"  💰 Баланс USDT: ${usdt_balance:.2f}")
                logger.info(f"  ✅ Приватный API работает!")
            except Exception as e:
                if 'Invalid API' in str(e) or 'signature' in str(e).lower():
                    logger.error(f"  ❌ Неверные API ключи: {str(e)[:100]}")
                elif 'Permission' in str(e) or 'unauthorized' in str(e).lower():
                    logger.warning(f"  ⚠️ Недостаточно прав API ключа: {str(e)[:100]}")
                else:
                    logger.error(f"  ❌ Ошибка приватного API: {str(e)[:100]}")
        else:
            logger.info(f"  ℹ️ API ключи не предоставлены")
        
        return True
        
    except Exception as e:
        logger.error(f"  ❌ Ошибка подключения к {exchange_name}: {str(e)[:200]}")
        return False
    finally:
        try:
            if exchange is not None:
                await exchange.close()
        except Exception:
            pass

async def test_all_exchanges():
    """Тестирование всех бирж"""
    logger.info("🚀 Начинаем тестирование API подключений...")
    logger.info(f"📡 Прокси {'включен' if PROXY_CONFIG.get('enabled') else 'выключен'}")
    
    results = {}
    
    # Тестирование каждой биржи
    for exchange_name, config in API_KEYS.items():
        if not config.get('apiKey'):  # Пропускаем биржи без ключей
            logger.info(f"\n⏭️ Пропускаем {exchange_name} (нет API ключей)")
            continue
            
        result = await test_exchange(exchange_name, config)
        results[exchange_name] = result
        await asyncio.sleep(1)  # Пауза между биржами
    
    # Итоговый отчет
    logger.info(f"\n{'='*50}")
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ:")
    logger.info(f"{'='*50}")
    
    success_count = sum(1 for r in results.values() if r)
    total_count = len(results)
    
    for exchange, success in results.items():
        status = "✅ Работает" if success else "❌ Не работает"
        logger.info(f"  {exchange}: {status}")
    
    logger.info(f"\n📈 Успешно подключено: {success_count}/{total_count} бирж")
    
    if success_count < total_count:
        logger.info("\n💡 Рекомендации:")
        logger.info("  1. Проверьте правильность API ключей")
        logger.info("  2. Убедитесь, что API ключи имеют необходимые права")
        logger.info("  3. Проверьте, что IP адрес добавлен в whitelist (если требуется)")
        logger.info("  4. Попробуйте использовать VPN или прокси для заблокированных бирж")

async def main():
    """Главная функция"""
    try:
        await test_all_exchanges()
    except KeyboardInterrupt:
        logger.info("\n⚠️ Тестирование прервано пользователем")
    except Exception as e:
        logger.error(f"\n❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
