#!/usr/bin/env python3
"""
🔐 Тестирование API подключений к биржам
"""

import asyncio
import ccxt.async_support as ccxt
from production_config import API_KEYS, PROXY_CONFIG, EXCHANGES_CONFIG
import aiohttp
import logging
import os
import hmac
import hashlib
import base64
import time
import json
from datetime import datetime, timezone

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def _okx_demo_balance(config):
    """Приватный тест OKX DEMO через прямой REST (ccxt demo ограничен)."""
    api_key = config.get('apiKey', '')
    secret = (config.get('secret', '') or '').encode()
    passphrase = config.get('password') or config.get('passphrase') or ''
    base = 'https://www.okx.com'
    path = '/api/v5/account/balance'
    method = 'GET'
    qs = 'ccy=USDT'
    # OKX подпись: base64(hmac_sha256(secret, ts + method + path + ("?"+qs|body)))
    ts = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    prehash = f"{ts}{method}{path}?{qs}"
    sign = base64.b64encode(hmac.new(secret, prehash.encode(), hashlib.sha256).digest()).decode()
    headers = {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': sign,
        'OK-ACCESS-TIMESTAMP': ts,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'x-simulated-trading': '1',
        'Content-Type': 'application/json',
    }
    url = f"{base}{path}?{qs}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            txt = await r.text()
            if r.status == 200 and '"code":"0"' in txt:
                logger.info("  ✅ OKX DEMO приватный доступ подтверждён")
                return True
            logger.error(f"  ❌ OKX DEMO ошибка: HTTP {r.status} {txt[:200]}")
            return False

async def _bitget_demo_balance(config):
    """Приватный тест Bitget DEMO через прямой REST с заголовком PAPTRADING: 1."""
    api_key = config.get('apiKey', '')
    secret = config.get('secret', '')
    passphrase = config.get('password') or config.get('passphrase') or ''
    base = 'https://api.bitget.com'
    path = '/api/v2/spot/account/assets'
    method = 'GET'
    # Bitget подпись: base64(hmac_sha256(secret, ts + method + path + body))
    ts = str(int(time.time() * 1000))
    prehash = f"{ts}{method}{path}"
    sign = base64.b64encode(hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()).decode()
    headers = {
        'ACCESS-KEY': api_key,
        'ACCESS-SIGN': sign,
        'ACCESS-TIMESTAMP': ts,
        'ACCESS-PASSPHRASE': passphrase,
        'Content-Type': 'application/json',
        'PAPTRADING': '1',
    }
    url = f"{base}{path}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url, headers=headers) as r:
            txt = await r.text()
            if r.status == 200 and '"code":"00000"' in txt:
                logger.info("  ✅ Bitget DEMO приватный доступ подтверждён")
                return True
            logger.error(f"  ❌ Bitget DEMO ошибка: HTTP {r.status} {txt[:200]}")
            return False

async def test_exchange(exchange_name, config):
    """Тестирование подключения к бирже"""
    exchange = None
    # Управление окружением прокси для конкретной биржи
    prev_env = {}
    cleared_proxies = False
    try:
        logger.info(f"\n{'='*50}")
        logger.info(f"🔍 Тестирование {exchange_name}...")
        env = (config.get('env') or '').lower()
        use_proxy_flag = EXCHANGES_CONFIG.get(exchange_name.lower(), {}).get('use_proxy', True)

        if not use_proxy_flag:
            # Очистить системные прокси-переменные чтобы форсировать прямое соединение
            cleared_proxies = True
            logger.info("  🚫 Прокси отключён per-exchange флагом — очищаем HTTP(S)_PROXY для прямого соединения")
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                if k in os.environ:
                    prev_env[k] = os.environ.pop(k)

        # Спец-обработка DEMO окружений, где ccxt ограничен
        if exchange_name.lower() == 'okx' and env == 'demo':
            logger.info("  🧪 OKX DEMO режим: прямой приватный REST тест")
            return await _okx_demo_balance(config)
        if exchange_name.lower() == 'bitget' and env == 'demo':
            logger.info("  🧪 Bitget DEMO режим: прямой приватный REST тест")
            return await _bitget_demo_balance(config)
        
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
        
        # Настройка прокси для разных бирж (с учётом per-exchange флага)
        if PROXY_CONFIG.get('enabled') and use_proxy_flag:
            # Выбираем прокси в зависимости от биржи
            if exchange_name.upper() in ['HUOBI', 'OKX']:
                # Азиатские биржи - используем Japan прокси
                proxy = PROXY_CONFIG['japan']['https']
                logger.info(f"  📡 Используется Japan прокси для {exchange_name}")
            elif exchange_name.upper() in ['BINANCE', 'BYBIT', 'PHEMEX']:
                # Заблокированные биржи - используем Netherlands прокси
                proxy = PROXY_CONFIG['netherlands']['https']
                logger.info(f"  📡 Используется Netherlands прокси для {exchange_name}")
            else:
                # Остальные - без прокси или Estonia
                proxy = None

            # Для Phemex DEMO принудительно отключаем прокси (часто блокируется testnet)
            if exchange_name.lower() == 'phemex' and env == 'demo':
                proxy = None
                logger.info("  🚫 Прокси отключён для Phemex DEMO (прямое соединение)")

            if proxy:
                exchange_config['proxies'] = {
                    'http': proxy,
                    'https': proxy
                }
                exchange_config['aiohttp_proxy'] = proxy
        
        exchange = exchange_class(exchange_config)

        # Включаем тестовую среду для Phemex при env=='demo'
        if exchange_name.lower() == 'phemex' and env == 'demo':
            try:
                exchange.set_sandbox_mode(True)
                logger.info("  🧪 Phemex DEMO режим: включён sandbox (testnet)")
            except Exception as e:
                logger.warning(f"  ⚠️ Не удалось включить sandbox для Phemex: {str(e)[:120]}")
        
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
        # Восстановить прокси-переменные окружения, если очищали
        if cleared_proxies and prev_env:
            for k, v in prev_env.items():
                os.environ[k] = v

async def test_all_exchanges():
    """Тестирование всех бирж"""
    logger.info("🚀 Начинаем тестирование API подключений...")
    logger.info(f"📡 Прокси {'включен' if PROXY_CONFIG.get('enabled') else 'выключен'}")
    
    results = {}
    
    # Тестирование каждой биржи
    for exchange_name, config in API_KEYS.items():
        # Учитываем включенность биржи в EXCHANGES_CONFIG, чтобы тестировать только активные
        ex_conf = EXCHANGES_CONFIG.get(exchange_name.lower(), {})
        if not ex_conf.get('enabled', False):
            logger.info(f"\n⏭️ Пропускаем {exchange_name} (отключен в EXCHANGES_CONFIG)")
            continue
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
# EOF
