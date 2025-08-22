#!/usr/bin/env python3
"""
🚀 PRODUCTION CONFIGURATION
Конфигурация для продакшн арбитражного бота
"""

import os
import logging
from dotenv import load_dotenv

# API ключи для бирж
API_KEYS = {
    'mexc': {
        'apiKey': 'mx0vg1FCHvkkdT6A5o',
        'secret': 'fb088b72097f49ab94d8b3e35277e2e2'
    },
    'bybit': {
        'apiKey': 'UXUTxVL5B6GdSGNv3L',
        'secret': '9N8b02qOQd7rxEYPi44Rwx6p8hsmLbdGbyqg'
    },
    'huobi': {
        'apiKey': '26a00c55-aih2kl1v2b-e3e8a09f-2da65',
        'secret': '34e0e93e-e2fb4c2f-29a56f4f-e3e1f'
    },
    'binance': {
        'apiKey': '',
        'secret': ''
    },
    'okx': {
        'apiKey': 'ab4f2fe8-e2c4-4d18-9712-d21c8f2f187c',  # OKX API ключ
        'secret': 'FC63C15B1D2DB5C73632ED5BACE49290',  # OKX секретный ключ
        'passphrase': 'Egor1998!',
        'password': 'Egor1998!',
        'env': 'demo'
    },
    'gate': {
        'apiKey': '',  # Нужен API ключ от Gate.io
        'secret': '',  # Нужен секретный ключ от Gate.io
        'passphrase': 'Egor1998!'
    },
    'bitget': {
        'apiKey': 'bg_e72cdc8606f8a446da2bede94c238c13',
        'secret': '14b48fa1d080f94c5b21a4d33acd25ef18ca8f47281ef6a10a594a192822ba17',
        'passphrase': '0502794579Egor',
        'password': '0502794579Egor',
        'env': 'demo'
    },
    'phemex': {
        'apiKey': '08fc7ba8-be86-4e11-9085-9e5423657c04',
        'secret': '4XGaPGeIq_kQCURYEq85o7j1gQVbP8pwwetnUSP4uN00OTExNjBkNC03Y2Q2LTRhNjktYTQwMy1kMzRlMmYzZTQ1YzQ',
        'env': 'demo'
    }
}

# Прокси для обхода геоблокировок (FPTN VPN)
PROXY_CONFIG = {
    'enabled': True,  # Включаем прокси для Phemex
    # Доступ к локальному Mixed-прокси NekoBox из WSL через IP Windows-хоста
    'fptn_host': {
        'socks5': 'socks5://172.31.128.1:2080',
        'http': 'http://172.31.128.1:2080'
    },
    'fptn_local': {
        'socks5': 'socks5://127.0.0.1:2080',
        'http': 'http://127.0.0.1:2080'
    },
    'japan': {
        'http': 'http://user5965363034:ETZgBYjA@38.180.147.238:443',
        'https': 'https://user5965363034:ETZgBYjA@38.180.147.238:443'
    },
    'usa': {
        'http': 'http://user5965363034:ETZgBYjA@192.3.251.79:443',
        'https': 'https://user5965363034:ETZgBYjA@192.3.251.79:443'
    },
    'netherlands': {
        'http': 'http://user5965363034:ETZgBYjA@147.45.135.67:443',
        'https': 'https://user5965363034:ETZgBYjA@147.45.135.67:443'
    },
    'estonia': {
        'http': 'http://user5965363034:ETZgBYjA@185.215.187.165:443',
        'https': 'https://user5965363034:ETZgBYjA@185.215.187.165:443'
    }
}

# Конфигурация бирж
EXCHANGES_CONFIG = {
    'mexc': {
        'name': 'MEXC',
        'enabled': False,  # Отключено для демо OKX↔Bitget
        'rate_limit': 100,
        'fee': 0.001,  # 0.10% taker (реалистично без скидок)
        'websocket': True,  # Включаем WebSocket для MEXC (REST останется как backup)
        'poll_rest': True,  # Использовать REST API для MEXC
        'poll_interval': 2,  # Интервал опроса REST API (секунды)
        'rest_url': 'https://api.mexc.com',
        'ws_url': 'wss://wbs.mexc.com/ws'  # Добавляем ws_url
    },
    'gate': {
        'name': 'Gate.io',
        'enabled': False,  # Временно отключен
        'rate_limit': 100,
        'fee': 0.002,  # 0.20% taker без скидок
        'websocket': True,
        'poll_rest': True,
        'poll_interval': 1,
        'rest_url': 'https://api.gateio.ws',
        'ws_url': 'wss://api.gateio.ws/ws/v4/'
    },
    'bybit': {
        'name': 'Bybit',
        'enabled': True,
        'rate_limit': 100,
        'fee': 0.001,  # 0.10% taker без скидок
        'websocket': True,
        'poll_rest': True,
        'poll_interval': 1,
        'rest_url': 'https://api.bybit.com',
        'ws_url': 'wss://stream.bybit.com/v5/public/spot'  # Исправлен URL для spot торговли
    },
    'huobi': {
        'name': 'Huobi',
        'enabled': False,
        'rate_limit': 100,
        'fee': 0.002,  # 0.20% taker без скидок
        'websocket': True,
        'poll_rest': True,
        'poll_interval': 1,
        'rest_url': 'https://api.huobi.pro',
        'ws_url': 'wss://api.huobi.pro/ws'
    },
    'binance': {
        'name': 'Binance',
        'enabled': True,
        'rate_limit': 1200,
        'fee': 0.001,
        'websocket': True,
        'poll_rest': True,
        'poll_interval': 1,
        'rest_url': 'https://api.binance.com',
        'ws_url': 'wss://stream.binance.com:9443/ws'
    },
    'okx': {
        'name': 'OKX',
        'enabled': True,
        'websocket': True,
        'poll_rest': True,
        'poll_interval': 1,
        'use_proxy': False,
        'rest_url': 'https://www.okx.com',
        'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
        'demo_ws_url': 'wss://wspap.okx.com:8443/ws/v5/public'  # Демо WebSocket эндпоинт
    },
    'bitget': {
        'name': 'Bitget',
        'enabled': True,  # ВКЛЮЧЕНО для межарбитража OKX-Bitget
        'rate_limit': 100,
        'fee': 0.001,  # 0.1% стандартная комиссия
        'websocket': False,  # Отключаем WebSocket, используем REST polling
        'poll_rest': True,
        'poll_interval': 1,
        'use_proxy': False,
        'rest_url': 'https://api.bitget.com',
        # Demo trading WS endpoints per Bitget docs:
        # Public:  wss://wspap.bitget.com/v2/ws/public
        # Private: wss://wspap.bitget.com/v2/ws/private
        # Use public endpoint for market data subscriptions (tickers)
        'ws_url': 'wss://wspap.bitget.com/v2/ws/public'
    },
    'phemex': {
        'name': 'Phemex',
        'enabled': True,  # Включен для увеличения количества возможностей
        'rate_limit': 100,
        'fee': 0.001,  # 0.1% стандартная комиссия
        'websocket': False,  # Отключаем WS (нет прокси), используем REST-поллинг
        'poll_rest': True,
        'poll_interval': 1,
        'use_proxy': False,
        'rest_url': 'https://api.phemex.com'
    },
    'kucoin': {
        'name': 'KuCoin',
        'enabled': False,  # Временно отключен
        'rate_limit': 100,
        'fee': 0.001,
        'websocket': True,
        'poll_rest': False,
        'poll_interval': 1,
        'rest_url': 'https://api.kucoin.com'
    },
    'kraken': {
        'name': 'Kraken',
        'enabled': False,  # Временно отключен
        'rate_limit': 60,
        'fee': 0.0026,  # 0.26% taker без скидок
        'websocket': True,
        'poll_rest': False,
        'poll_interval': 1,
        'rest_url': 'https://api.kraken.com'
    }
}

# Торговые параметры
TRADING_CONFIG = {
    'mode': 'demo',  # 'demo' для активации demo-заголовков (PAPTRADING=1, x-simulated-trading=1)
    'min_profit_threshold': 0.01,  # Минимальный порог 0.01% для максимального поиска
    'slippage_tolerance': 0.0,  # Не штрафуем дважды: реальный slippage учитывается в анализе ликвидности
    'max_opportunity_age': 8,  # Увеличено TTL до 8 секунд (устраняет 1977 случаев отбрасывания)
    'scan_interval': 0.05,  # Увеличена частота сканирования до 20/сек (50ms)
    'enable_triangular': True,  # Треугольный арбитраж ВКЛЮЧЕН
    'enable_inter_exchange': True,  # Межбиржевой арбитраж
    'enable_exhaustive_pair_scanning': False,  # Полный перебор пар бирж на символ
    'max_buy_candidates_per_symbol': 3,  # Максимум кандидатов-покупок на символ
    'max_sell_candidates_per_symbol': 3,  # Максимум кандидатов-продаж на символ
    'pair_cooldown_seconds': 5,  # Кулдаун расслаблен для paper
    'position_size_usd': 100,  # Размер позиции в USD
    # Параметры анализатора ликвидности (используются для переопределения в боте)
    'min_liquidity_usd': 100,      # Требуемая ликвидность ~= размер позиции
    'max_price_impact_pct': 2.0,   # Допустимое влияние на цену в %
    'min_depth_levels': 1,         # Минимум уровней стакана
    'initial_capital': 10000,  # Начальный капитал в USD
    'max_open_positions': 5,  # Максимум открытых позиций
    # Demo/testnet режим
    'demo_supported_exchanges': ['okx', 'bitget', 'phemex'],
    'demo_initial_usdt': 100,
}

# Динамический поиск пар
DYNAMIC_PAIRS_CONFIG = {
    'enabled': True,
    'update_interval': 1800,  # Обновление каждые 30 минут
    'min_volume_24h': 1000000,  # Минимальный объем за 24ч в USD
    'min_exchanges': 2,  # Минимум бирж для пары (например, OKX и Bitget)
    'max_pairs': 300,  # Лимит активных пар увеличен до 300
    'per_exchange_discovery_limit': 300,  # Сколько пар брать с каждой биржи при discovery
    'priority_pairs': [
        # ВЫСОКОПРИОРИТЕТНЫЕ популярные пары (OKX-Bitget общие)
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
        'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT',
        'UNI/USDT', 'LTC/USDT', 'BCH/USDT', 'NEAR/USDT', 'ATOM/USDT',
        'AAVE/USDT', 'MKR/USDT', 'CRV/USDT', 'SNX/USDT', 'SUSHI/USDT',
        
        # Мем-коины высокой волатильности
        'PEPE/USDT', 'SHIB/USDT', 'WIF/USDT', 'BONK/USDT', 'BOME/USDT',
        'NEIRO/USDT', 'PNUT/USDT', 'TURBO/USDT', 'NOT/USDT', 'FLOKI/USDT',
        
        # Layer 2 и новые токены
        'OP/USDT', 'ARB/USDT', 'SUI/USDT', 'APT/USDT', 'INJ/USDT',
        'TIA/USDT', 'JUP/USDT', 'STRK/USDT', 'PYTH/USDT', 'RENDER/USDT',
        
        # DeFi токены с активной торговлей
        'PENDLE/USDT', 'GMX/USDT', 'LDO/USDT', 'BLUR/USDT', 'DYDX/USDT',
        'ENS/USDT', '1INCH/USDT', 'COMP/USDT', 'YFI/USDT', 'ONDO/USDT'
    ]
}

# Старое название для совместимости
SYMBOL_DISCOVERY_CONFIG = {
        'enabled': True,
        'update_interval_minutes': 30,  # Обновлять список каждые 30 минут
        'min_exchanges': 3,  # Минимум бирж для торговли парой
        'top_symbols_limit': 200,  # Топ 200 пар по объему для большего покрытия
        'base_currencies': ['USDT', 'USDC', 'BUSD'],  # Базовые валюты
        'exclude_symbols': ['LUNA', 'UST', 'FTT', 'USTC'],  # Исключить проблемные токены
        'volume_weight': 0.4,  # Вес объема при ранжировании
        'volatility_weight': 0.3,  # Вес волатильности
        'spread_weight': 0.3,  # Вес спреда
        'min_market_cap': 10000000,  # Минимальная капитализация $10M
        'prefer_symbols': [  # Расширенный список символов (100+)
            # Основные
            'BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'DOGE', 'AVAX', 'DOT', 'MATIC',
            'LINK', 'LTC', 'BCH', 'ATOM', 'UNI', 'ETC', 'XLM', 'ALGO', 'NEAR', 'FIL',
            'VET', 'HBAR', 'EGLD', 'XTZ', 'MANA', 'SAND', 'AXS', 'THETA', 'FTM', 'RUNE',
            
            # DeFi
            'AAVE', 'SUSHI', 'COMP', 'YFI', 'CRV', 'MKR', 'SNX', '1INCH', 'BAL', 'LDO',
            'UMA', 'BAND', 'REN', 'KNC', 'ALPHA', 'BADGER', 'CREAM', 'PERP', 'DYDX',
            
            # Мем-коины
            'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF', 'MEME', 'BABYDOGE', 'ELON', 'AKITA',
            'KISHU', 'PIG', 'SAFEMOON', 'SHIBA', 'DOGELON', 'SAMO', 'HOGE',
            
            # Layer 2
            'ARB', 'OP', 'IMX', 'LRC', 'SKL', 'CELR', 'OMG', 'BOBA', 'METIS',
            
            # Новые проекты 2023-2024
            'APT', 'SUI', 'SEI', 'TIA', 'INJ', 'BLUR', 'WLD', 'ARKM', 'CYBER', 'PENDLE',
            'RDNT', 'MAGIC', 'GMX', 'GNS', 'VELO', 'STG', 'JOE', 'GRAIL',
            
            # Gaming
            'GALA', 'ENJ', 'CHZ', 'FLOW', 'ICP', 'GMT', 'GST', 'STEPN', 'ALICE', 'SLP',
            'TLM', 'MOBOX', 'SKILL', 'MBOX', 'YGG', 'ULTRA', 'WEMIX', 'PYR', 'GODS',
            
            # AI токены
            'FET', 'AGIX', 'OCEAN', 'NMR', 'RNDR', 'TAO', 'GLM', 'CTXC', 'MDT'
        ]
}

# Торговые пары для OKX-Bitget межарбитража (248 общих пар)
TRADING_PAIRS = [
    # Топ-20 высоколиквидных пар для межарбитража OKX-Bitget  
    'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
    'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'LINK/USDT', 'DOT/USDT',
    'UNI/USDT', 'LTC/USDT', 'BCH/USDT', 'NEAR/USDT', 'ATOM/USDT',
    'AAVE/USDT', 'MKR/USDT', 'CRV/USDT', 'SNX/USDT', 'SUSHI/USDT',
    
    # Мем-коины высокой волатильности
    'PEPE/USDT', 'SHIB/USDT', 'WIF/USDT', 'BONK/USDT', 'BOME/USDT',
    'NEIRO/USDT', 'PNUT/USDT', 'TURBO/USDT', 'NOT/USDT', 'FLOKI/USDT',
    
    # Layer 2 и новые токены
    'OP/USDT', 'ARB/USDT', 'SUI/USDT', 'APT/USDT', 'INJ/USDT',
    'TIA/USDT', 'JUP/USDT', 'STRK/USDT', 'PYTH/USDT', 'RENDER/USDT',
    
    # DeFi токены с активной торговлей
    'PENDLE/USDT', 'GMX/USDT', 'LDO/USDT', 'BLUR/USDT', 'DYDX/USDT',
    'ENS/USDT', '1INCH/USDT', 'COMP/USDT', 'YFI/USDT', 'ONDO/USDT'
]

# ============================================
# 💼 РАЗМЕР ПОЗИЦИЙ
# ============================================
POSITION_SIZING = {
    'min_position_usd': 50,  # Минимальный размер позиции
    'default_position_usd': 100,  # Размер позиции по умолчанию
    'max_position_usd': 1000,  # Максимальный размер позиции
    'use_percentage': False,  # Использовать % от баланса
    'balance_percentage': 10,  # % от баланса если use_percentage=True
}

# ============================================
# 🌐 WEBSOCKET КОНФИГУРАЦИЯ
# ============================================
WEBSOCKET_CONFIG = {
    'ping_interval': 20,  # Интервал ping в секундах
    'ping_timeout': 10,  # Таймаут ping/pong
    'reconnect_delay': 5,  # Задержка переподключения
    'max_reconnect_delay': 60,  # Максимальная задержка
    'max_reconnect_attempts': 0,  # 0 = бесконечно
    'message_queue_size': 1000,  # Размер очереди сообщений
}

# ============================================
# 📝 ЛОГИРОВАНИЕ
# ============================================
LOGGING_CONFIG = {
    'level': logging.INFO,
    'format': '%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    'date_format': '%H:%M:%S',
    'file': 'production_bot.log',
    'max_file_size': 10485760,  # 10 MB
    'backup_count': 5,
}

# Риск-менеджмент
RISK_MANAGEMENT = {
    'stop_loss': 500.0,  # Стоп-лосс в USD - критично для мониторинга
    'take_profit': 1000.0,  # Тейк-профит в USD
    'max_daily_loss': 100.0,  # Максимальный дневной убыток в USD
    'max_concurrent_positions': 5,  # Максимум одновременных позиций
    'max_portfolio_risk': 0.02,  # Максимальный риск портфеля 2%
    'max_position_risk': 0.01,  # Максимальный риск позиции 1%
    'correlation_threshold': 0.7,  # Порог корреляции для диверсификации
    'max_leverage': 1.0,  # Без плеча
    'margin_call_level': 0.3,  # Уровень маржин-колла 30%
    'auto_deleverage': True,  # Автоматическое снижение плеча
    'blacklist_after_losses': 3,  # Блокировать пару после N убытков подряд
    'cooldown_period_minutes': 30  # Период охлаждения после убытка
}

# Уведомления (будущая функция)
NOTIFICATIONS = {
    'telegram': {
        'enabled': False,
        'bot_token': '',
        'chat_id': '',
        'send_trades': True,
        'send_errors': True,
        'send_daily_report': True
    },
    'email': {
        'enabled': False,
        'smtp_server': '',
        'smtp_port': 587,
        'email': '',
        'password': ''
    }
}

# Логирование
LOGGING_CONFIG = {
    'level': 'INFO',
    'file': 'production_bot.log',
    'max_file_size_mb': 100,
    'backup_count': 5,
    'format': '%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    'trades_file': 'trades_history.csv',
    'opportunities_file': 'opportunities.csv',
    'performance_file': 'performance_report.json'
}

# WebSocket настройки
WEBSOCKET_CONFIG = {
    'ping_interval': 20,  # Интервал пинга в секундах
    'ping_timeout': 10,  # Таймаут пинга
    'close_timeout': 10,  # Таймаут закрытия
    'max_reconnect_attempts': 10,  # Максимум попыток переподключения
    'reconnect_delay': 1,  # Начальная задержка переподключения
    'max_reconnect_delay': 60,  # Максимальная задержка
    'message_queue_size': 10000,  # Размер очереди сообщений
    'compression': 'deflate'  # Сжатие
}

# Оптимизация производительности
PERFORMANCE_CONFIG = {
    'use_uvloop': True,  # Использовать uvloop для ускорения
    'orderbook_cache_size': 1000,  # Размер кэша стаканов
    'price_cache_ttl': 5,  # TTL кэша цен в секундах
    'parallel_requests': True,  # Параллельные запросы
    'batch_size': 50,  # Размер батча для обработки
    'gc_interval': 300,  # Интервал сборки мусора
    'profile_enabled': False  # Профилирование производительности
}

# База данных (будущая функция)
DATABASE_CONFIG = {
    'enabled': False,
    'type': 'sqlite',  # sqlite | postgresql | mongodb
    'connection_string': 'sqlite:///trading_bot.db',
    'pool_size': 10,
    'echo': False
}

# Машинное обучение (будущая функция)
ML_CONFIG = {
    'enabled': False,
    'model_type': 'lstm',  # lstm | xgboost | random_forest
    'prediction_horizon': 5,  # Минут
    'features': ['price', 'volume', 'spread', 'volatility'],
    'retrain_interval_hours': 24,
    'min_accuracy': 0.6
}

# Backtesting
BACKTEST_CONFIG = {
    'enabled': False,
    'start_date': '2024-01-01',
    'end_date': '2024-12-31',
    'initial_balance': 10000,
    'commission': 0.001,
    'slippage': 0.001
}

def validate_config():
    """Валидация конфигурации"""
    errors = []
    warnings = []
    
    # Проверка ключей API
    active_exchanges = 0
    public_ws_exchanges = {
        'binance', 'okx', 'kraken', 'kucoin', 'gate', 'huobi', 'bybit', 'mexc', 'phemex'
    }
    for exchange_id, config in EXCHANGES_CONFIG.items():
        if config.get('enabled', False):
            keys = API_KEYS.get(exchange_id, {})
            has_keys = bool(keys.get('apiKey')) and bool(keys.get('secret'))

            # Bitget: принудительно отключаем WebSocket (используем только REST)
            if exchange_id == 'bitget':
                EXCHANGES_CONFIG[exchange_id]['websocket'] = False
                EXCHANGES_CONFIG[exchange_id]['poll_rest'] = True
                warnings.append(f"⚠️ {config['name']}: WebSocket отключён, используем только REST polling")
                if not has_keys:
                    warnings.append(f"⚠️ {config['name']}: API ключи отсутствуют для demo торговли")

            # Для публичных WS бирж не отключаем из-за отсутствия ключей
            if exchange_id in public_ws_exchanges and not has_keys:
                warnings.append(f"⚠️ {config['name']}: API ключи отсутствуют — продолжаем для публичного WebSocket")

            # Считаем все включенные биржи активными для данных
            active_exchanges += 1
    
    if active_exchanges < 2:
        errors.append("❌ Недостаточно активных бирж (минимум 2)")
    
    # Проверка торговых параметров
    if TRADING_CONFIG['min_profit_threshold'] < 0.1:
        warnings.append("⚠️ Слишком низкий порог прибыли (<0.1%)")
    
    if TRADING_CONFIG['position_size_usd'] > TRADING_CONFIG['initial_capital'] * 0.1:
        warnings.append("⚠️ Размер позиции >10% от капитала")
    
    # Проверка прокси при необходимости
    if any(c.get('use_proxy', False) and c['enabled'] for c in EXCHANGES_CONFIG.values()):
        if not PROXY_CONFIG['enabled']:
            errors.append("❌ Прокси требуется но не включен")
    
    return errors, warnings

# Экспорт всех конфигураций
__all__ = [
    'API_KEYS',
    'PROXY_CONFIG',
    'EXCHANGES_CONFIG',
    'TRADING_CONFIG',
    'SYMBOL_DISCOVERY_CONFIG',
    'RISK_MANAGEMENT',
    'NOTIFICATIONS',
    'LOGGING_CONFIG',
    'WEBSOCKET_CONFIG',
    'PERFORMANCE_CONFIG',
    'DATABASE_CONFIG',
    'ML_CONFIG',
    'BACKTEST_CONFIG',
    'validate_config'
]
