#!/usr/bin/env python3
"""
🚀 WHITEBIT-PHEMEX АРБИТРАЖНЫЙ БОТ
Конфигурация для реального арбитража между WhiteBit и Phemex (mainnet)
"""

import os
import logging

# API ключи для двух целевых бирж
API_KEYS = {
    'whitebit': {
        'apiKey': '548ae5005460f62d1c587280c39851da',
        'secret': '349ee8428847596a1298c4996ff5b51e',
        'demo_mode': False,  # Реальный режим
        'demo_balance': 1000,  # 1000 DUSDT доступно
        'trading_balance': 100,  # 100 DUSDT на торговом балансе
        'main_currency': 'USDT'
    },
    'phemex': {
        'apiKey': '17ecc3c1-4f21-44a1-b306-703cee649d03',
        'secret': '73VZrCx2JZPv5b2bRi9-aIBT03asrkIOUxVGXQGSWMc1OGY0MWQ4My0yNGYxLTQ1NzgtOGE5YS0yY2YzZjdiNjBlODU',
        'testnet_mode': True,  # Testnet режим (ключи из production конфигурации)
        'base_currency': 'BTC',  # ~1 BTC баланс (testnet)
        'trading_enabled': True,
        # TESTNET URLs для правильной работы
        'testnet_urls': {
            'api': 'https://testnet-api.phemex.com',
            'public': 'https://testnet-api.phemex.com', 
            'private': 'https://testnet-api.phemex.com'
        }
    }
}

# Конфигурация бирж - ТОЛЬКО WhiteBit и Phemex
EXCHANGES_CONFIG = {
    'whitebit': {
        'name': 'WhiteBit',
        'enabled': True,
        'trading_enabled': True,  # ✅ РЕАЛЬНАЯ ТОРГОВЛЯ
        'websocket': False,
        'poll_rest': True,
        'poll_interval': 1,  # Каждую секунду
        'fee': 0.001,  # 0.1% комиссия
        'rate_limit': 100,
        'rest_url': 'https://whitebit.com',
        'demo_mode': False,
        'demo_currencies': ['DUSDT', 'DBTC'],
        'main_currency': 'USDT'
    },
    'phemex': {
        'name': 'Phemex',
        'enabled': True,
        'trading_enabled': True,  # ✅ РЕАЛЬНАЯ ТОРГОВЛЯ  
        'websocket': False,
        'poll_rest': True,
        'poll_interval': 1,  # Каждую секунду
        'fee': 0.001,  # 0.1% комиссия
        'rate_limit': 100,
        'rest_url': 'https://testnet-api.phemex.com',  # Testnet API для REST фоллбэка
        'testnet_mode': True,
        'use_proxy': False,
        'base_currency': 'BTC',
        'quote_currency': 'USDT'
    }
}

# Торговые пары - совместимые для обеих бирж
TRADING_PAIRS = [
    # Основные криптовалюты (высокая ликвидность)
    'BTC/USDT',  # Bitcoin - самая ликвидная пара
    'ETH/USDT',  # Ethereum - вторая по ликвидности
    
    # Топ альткоины
    'BNB/USDT', 'XRP/USDT', 'ADA/USDT', 'SOL/USDT', 
    'DOGE/USDT', 'DOT/USDT', 'AVAX/USDT', 'MATIC/USDT',
    'LINK/USDT', 'UNI/USDT', 'LTC/USDT', 'BCH/USDT',
    'ATOM/USDT', 'FIL/USDT', 'ETC/USDT', 'XLM/USDT',
    # Добавлены более волатильные/спредовые
    'APT/USDT', 'ARB/USDT', 'OP/USDT', 'SUI/USDT', 'LDO/USDT',
    'INJ/USDT', 'RNDR/USDT', 'NEAR/USDT', 'FTM/USDT', 'AXS/USDT',
    'PEPE/USDT', 'SHIB/USDT'
]

# Агрессивные торговые настройки для максимума сделок
TRADING_CONFIG = {
    'mode': 'real',  # ✅ РЕАЛЬНЫЙ РЕЖИМ - не paper trading!
    'min_profit_threshold': 0.30,  # 0.30% минимальная чистая прибыль (с учётом комиссий)
    'slippage_tolerance': 0.02,  # 2% slippage tolerance
    'max_opportunity_age': 30,  # 30 секунд максимум
    'scan_interval': 1,  # Сканировать каждую секунду
    'enable_triangular': False,  # Отключаем треугольный (только межбиржевой)
    'enable_inter_exchange': True,  # ✅ Межбиржевой арбитраж
    'pair_cooldown_seconds': 10,  # 10 секунд между сделками по паре
    'position_size_usd': 50.0,  # $50 на сделку (безопасно)
    'use_websocket': False,  # Используем REST для стабильности
    'max_reasonable_spread_pct': 15.0,  # Фильтр аномальных спредов (например, дисбалансы тестнета)
    'max_concurrent_positions': 3,  # Максимум 3 позиции одновременно
    'use_maker_orders': False,  # Taker ордера для быстрого исполнения
}

# Динамическое обнаружение пар - фокус на высоколиквидных
DYNAMIC_PAIRS_CONFIG = {
    'enabled': True,
    'update_interval': 1800,  # 30 минут
    'min_volume_24h': 1000000,  # $1M минимальный объем
    'min_exchanges': 2,  # Обе наши биржи
    'max_pairs': 50,  # Ограничиваем до 50 пар
    'priority_pairs': [
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT',
        'ADA/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT',
        # Волатильные кандидаты для приоритета отбора
        'APT/USDT', 'ARB/USDT', 'OP/USDT', 'SUI/USDT', 'LDO/USDT',
        'INJ/USDT', 'RNDR/USDT', 'NEAR/USDT', 'FTM/USDT', 'AXS/USDT',
        'PEPE/USDT', 'SHIB/USDT'
    ]
}

# Риск-менеджмент (консервативный для реальных средств)
RISK_MANAGEMENT = {
    'stop_loss': 100.0,  # $100 стоп-лосс
    'take_profit': 200.0,  # $200 тейк-профит
    'max_daily_loss': 50.0,  # $50 максимальный дневной убыток
    'max_concurrent_positions': 3,  # 3 позиции максимум
    'max_portfolio_risk': 0.05,  # 5% риск портфеля
    'max_position_risk': 0.02,  # 2% риск позиции
    'blacklist_after_losses': 2,  # Блок после 2 убытков
    'cooldown_period_minutes': 15  # 15 минут охлаждения
}

# Логирование
LOGGING_CONFIG = {
    'level': logging.INFO,
    'format': '%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s',
    'date_format': '%H:%M:%S',
    'file': 'whitebit_phemex_bot.log',  # Отдельный лог файл
    'trades_file': 'whitebit_phemex_trades.csv',
    'opportunities_file': 'whitebit_phemex_opportunities.csv'
}

# WebSocket отключен для стабильности
WEBSOCKET_CONFIG = {
    'enabled': False,  # Используем только REST API
    'ping_interval': 20,
    'ping_timeout': 10,
    'max_reconnect_attempts': 5
}

# Производительность
PERFORMANCE_CONFIG = {
    'use_uvloop': True,  # Ускорение asyncio
    'parallel_requests': True,
    'batch_size': 20,
    'price_cache_ttl': 2  # 2 секунды TTL для цен
}

def validate_config():
    """Валидация конфигурации WhiteBit-Phemex"""
    errors = []
    warnings = []
    
    # Проверка API ключей
    wb_keys = API_KEYS.get('whitebit', {})
    if not (wb_keys.get('apiKey') and wb_keys.get('secret')):
        errors.append("❌ WhiteBit API ключи отсутствуют")
        
    ph_keys = API_KEYS.get('phemex', {})  
    if not (ph_keys.get('apiKey') and ph_keys.get('secret')):
        errors.append("❌ Phemex API ключи отсутствуют")
    
    # Проверка активности бирж
    if not EXCHANGES_CONFIG['whitebit']['enabled']:
        errors.append("❌ WhiteBit не активен")
    if not EXCHANGES_CONFIG['phemex']['enabled']:  
        errors.append("❌ Phemex не активен")
    
    # Проверка торговых настроек
    if TRADING_CONFIG['mode'] != 'real':
        warnings.append("⚠️ Режим не 'real' - сделки не будут видны в истории")
        
    if TRADING_CONFIG['position_size_usd'] > 100:
        warnings.append("⚠️ Размер позиции >$100 может быть рискованным")

    # Проверка прибыльности против суммарных комиссий
    try:
        total_fees = EXCHANGES_CONFIG['whitebit']['fee'] + EXCHANGES_CONFIG['phemex']['fee']
        total_fees_pct = total_fees * 100
        min_profit_pct = float(TRADING_CONFIG.get('min_profit_threshold', 0.0))
        if min_profit_pct <= total_fees_pct:
            warnings.append(
                f"⚠️ Минимальная прибыль {min_profit_pct:.2f}% <= комиссии {total_fees_pct:.2f}% — убыточно"
            )
    except Exception:
        # Безопасный фоллбек, если какие-то ключи отсутствуют
        pass
    
    return errors, warnings

# Экспорт всех конфигураций
__all__ = [
    'API_KEYS',
    'EXCHANGES_CONFIG', 
    'TRADING_PAIRS',
    'TRADING_CONFIG',
    'DYNAMIC_PAIRS_CONFIG',
    'RISK_MANAGEMENT',
    'LOGGING_CONFIG',
    'WEBSOCKET_CONFIG',
    'PERFORMANCE_CONFIG',
    'validate_config'
]
