#!/usr/bin/env python3
"""
🚀 PRODUCTION CONFIGURATION
Конфигурация для продакшн арбитражного бота
"""

import os
import logging
from dotenv import load_dotenv

# API Ключи (РЕАЛЬНЫЕ КЛЮЧИ)
API_KEYS = {
    'mexc': {
        'apiKey': 'mx0vglAj5GaknRsyUQ',
        'secret': '83911cc1cd784568832b624fbfb19751'
    },
    'bybit': {
        'apiKey': 'F7FQ86OveT0P2rlVMo',
        'secret': 'yqlGJQmyC0olw5igeJvz6LlHmsVq7bf9E68C'
    },
    'huobi': {
        'apiKey': '685d99fa-frbqhq7rnm-d31ff320-13b69',
        'secret': '69c659d1-3c7b48ef-0794161a-994b3'
    },
    'okx': {
        'apiKey': '945fd20b-6a97-4417-904f-0eb22a41f673',
        'secret': '820A9A462BA696B6E4F0E9080B83DFB6',
        'password': 'Egor1998!'  # OKX API passphrase
    },
    'binance': {
        'apiKey': 'MvV3eNsenTdNinmtt1hXVOjNg1VsmjtNY4iZpqddN6f03DuX1GB8DuuKPOiUSOEy',
        'secret': 'XcDJGf39tlsl4G8qUu86wQqpEoqZgRfrl5yS8j7yiampncgrJ05PxQYUJYdUyPmG'
    },
    'gate': {
        'apiKey': '60182f63c3fb1faabad3c83769a370d7',
        'secret': '703adde41a669c7cdf424a6073c4bee44bbafb5225f494c0963fc28f123f6038'
    },
    'kucoin': {
        'apiKey': '',
        'secret': '',
        'password': ''
    }
}

# Прокси для обхода геоблокировок (FPTN VPN)
PROXY_CONFIG = {
    'enabled': False,  # Отключаем - без прокси работает лучше!
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
        'ws_url': 'wss://wbs.mexc.com/ws',
        'rest_url': 'https://api.mexc.com',
        'fees': {'maker': 0.001, 'taker': 0.001},  # Стандарт 0.1% без VIP
        'enabled': True,
        'poll_rest': True,  # Использовать REST API вместо WebSocket
        'poll_interval': 2  # Интервал опроса в секундах
    },
    'gate': {
        'name': 'Gate.io',
        'ws_url': 'wss://ws.gate.io/v3/',
        'rest_url': 'https://api.gateio.ws',
        'fees': {'maker': 0.0015, 'taker': 0.0025},  # Стандарт Gate.io без VIP
        'enabled': True,  # Включена с новыми ключами
        'poll_rest': True,  # REST API для публичных данных
        'poll_interval': 2
    },
    'bybit': {
        'name': 'Bybit',
        'ws_url': 'wss://stream.bybit.com/v5/public/spot',
        'rest_url': 'https://api.bybit.com',
        'fees': {'maker': 0.001, 'taker': 0.001},  # Стандарт 0.1% без VIP
        'enabled': True,  # Работает без прокси!
        'poll_rest': True,  # Использовать REST API вместо WebSocket
        'poll_interval': 2  # Интервал опроса в секундах
    },
    'huobi': {
        'name': 'Huobi',
        'ws_url': 'wss://api.huobi.pro/ws',
        'rest_url': 'https://api.huobi.pro',
        'fees': {'maker': 0.002, 'taker': 0.002},  # Стандарт Huobi 0.2%
        'enabled': True,  # Включена с новыми ключами
        'poll_rest': True,  # Использовать REST API вместо WebSocket
        'poll_interval': 2  # Интервал опроса в секундах
    },
    'binance': {
        'name': 'Binance',
        'ws_url': 'wss://stream.binance.com:9443/ws',
        'rest_url': 'https://api.binance.com',
        'fees': {'maker': 0.001, 'taker': 0.001},
        'enabled': True  # ✅ Работает без прокси!
    },
    'okx': {
        'name': 'OKX',
        'ws_url': 'wss://ws.okx.com:8443/ws/v5/public',
        'rest_url': 'https://www.okx.com',
        'fees': {'maker': 0.001, 'taker': 0.0015},  # Стандарт OKX без VIP
        'enabled': True  # ✅ Включена с новыми ключами
    },
    'kucoin': {
        'name': 'KUCOIN',
        'ws_url': 'wss://ws-api-spot.kucoin.com/',
        'rest_url': 'https://api.kucoin.com',
        'fees': {'maker': 0.001, 'taker': 0.001},
        'enabled': False  # Отключаем - нет API ключей
    },
    'kraken': {
        'name': 'KRAKEN',
        'ws_url': 'wss://ws.kraken.com',
        'rest_url': 'https://api.kraken.com',
        'fees': {'maker': 0.0016, 'taker': 0.0026},
        'enabled': False  # Отключаем - нет API ключей
    }
}

# Торговые параметры
TRADING_CONFIG = {
    'mode': 'demo',  # 'real', 'paper', 'demo'
    'min_profit_threshold': 0.05,  # Минимальная прибыль 0.05%
    'slippage_tolerance': 0.0005,  # Слиппедж 0.05% (было 5% - ошибка!)
    'max_opportunity_age': 2,  # Максимальный возраст возможности в секундах
    'scan_interval': 1,  # Интервал сканирования в секундах
    'enable_triangular': False,  # Треугольный арбитраж (пока отключен)
    'enable_inter_exchange': True,  # Межбиржевой арбитраж
    'position_size_usd': 100,  # Размер позиции в USD
    'initial_capital': 10000,  # Начальный капитал в USD
    'max_open_positions': 5,  # Максимум открытых позиций
}

# Динамический поиск пар
DYNAMIC_PAIRS_CONFIG = {
    'enabled': True,
    'update_interval': 1800,  # Обновление каждые 30 минут
    'min_volume_24h': 1000000,  # Минимальный объем за 24ч в USD
    'min_exchanges': 2,  # Минимум бирж для пары
    'max_pairs': 50,  # Максимум активных пар
    'priority_pairs': [  # Приоритетные пары
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
        'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT'
    ]
}

# Старое название для совместимости
SYMBOL_DISCOVERY_CONFIG = {
    'enabled': True,
    'update_interval_minutes': 30,  # Обновлять список каждые 30 минут
    'min_exchanges': 2,  # Минимум бирж где торгуется пара
    'top_symbols_limit': 100,  # Топ 100 пар по объему
    'base_currencies': ['USDT', 'USDC', 'BUSD'],  # Базовые валюты
    'exclude_symbols': ['LUNA', 'UST', 'FTT', 'USTC'],  # Исключить проблемные токены
    'volume_weight': 0.4,  # Вес объема при ранжировании
    'volatility_weight': 0.3,  # Вес волатильности
    'spread_weight': 0.3,  # Вес спреда
    'min_market_cap': 10000000,  # Минимальная капитализация $10M
    'prefer_symbols': [  # Приоритетные символы
        'BTC', 'ETH', 'BNB', 'XRP', 'SOL', 'ADA', 'DOGE', 
        'AVAX', 'MATIC', 'DOT', 'SHIB', 'TRX', 'LINK', 'UNI',
        'ATOM', 'LTC', 'ETC', 'APT', 'ARB', 'OP', 'PEPE',
        'WLD', 'SUI', 'SEI', 'INJ', 'TIA'
    ]
}

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
    for exchange_id, config in EXCHANGES_CONFIG.items():
        if config['enabled']:
            # API_KEYS теперь хранит биржи в нижнем регистре
            keys = API_KEYS.get(exchange_id, {})
            if not keys.get('apiKey') or not keys.get('secret'):
                warnings.append(f"⚠️ {config['name']}: API ключи отсутствуют")
                EXCHANGES_CONFIG[exchange_id]['enabled'] = False
            else:
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
