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
        'passphrase': ''
    },
    'phemex': {
        'apiKey': '17ecc3c1-4f21-44a1-b306-703cee649d03',
        'secret': '73VZrCx2JZPv5b2bRi9-aIBT03asrkIOUxVGXQGSWMc1OGY0MWQ4My0yNGYxLTQ1NzgtOGE5YS0yY2YzZjdiNjBlODU',
        'passphrase': ''
    },
    'okx': {
        'apiKey': 'f1616dbb-3b63-41bb-9353-8ac82e17d0cf',
        'secret': '0F51527F526AB5DFBACDF8658FF395A5',
        'passphrase': 'Egor1998!',
        'demo_mode': True
    }
}

# Конфигурация бирж - ТОЛЬКО WhiteBit и Phemex
EXCHANGES_CONFIG = {
    'whitebit': {
        'name': 'WhiteBit',
        'enabled': True,
        'api_key': '9b8e9e69-b44f-402e-a0e8-aa5ef42a76f9',  # API ключ из production_whitebit_phemex_config.py
        'api_secret': 'a1b3be00-f09b-42d3-a13f-20bc27bb5d03',  # API секрет
        'trading_enabled': True,  # Торговля через DEMO токены
        'websocket': False,
        'poll_rest': True,
        'poll_interval': 1,  # Каждую секунду
        'fee': 0.0005,  # 0.05% комиссия (maker ордера)
        'rate_limit': 100,
        'rest_url': 'https://whitebit.com',
        'demo_mode': True,  # ✅ DEMO режим включён
        'demo_currencies': ['DUSDT', 'DBTC'],
        'main_currency': 'DUSDT'  # Используем демо-токены
    },
    'phemex': {
        'name': 'Phemex',
        'enabled': True,
        'api_key': '27b1dc9f-d7e3-4094-a70d-d0a0e1cb6741',  # Testnet API ключ
        'api_secret': 'tKLJGBw6CRv6R2pis2P0a9Y3pLEnWLnrY3nJFUizOGU2YWY0MmQ3NS01MTA2LTQ4YjEtOTdmNi0zOTVkNzBmMzI5YjI',
        'trading_enabled': True,
        'websocket': False,
        'poll_rest': True,
        'poll_interval': 1,
        'fee': 0.0005,  # 0.05% комиссия
        'rate_limit': 100,
        'rest_url': 'https://testnet-api.phemex.com',  # ✅ TESTNET API
        'testnet_mode': True,  # ✅ TESTNET режим включён
        'use_proxy': False,
        'base_currency': 'USDT',  # Используем USDT для совместимости
        'quote_currency': 'USDT',  # USDT как котировочная валюта
        'use_btc_pairs': False,  # Используем USDT пары (BTC пар нет на тестнете)
        'default_type': 'spot'  # Спотовая торговля
    },
    'okx': {
        'name': 'OKX',
        'enabled': False,  # ❌ OKX временно отключен (проблема с API ключами)
        'api_key': 'OKX_DEMO_API_KEY',
        'api_secret': 'OKX_DEMO_API_SECRET',
        'password': 'OKX_DEMO_PASSPHRASE',
        'testnet': False,
        'demo': True,  # Demo торговля на OKX
        'websocket': False,
        'poll_rest': True,
        'poll_interval': 1,
        'fee': 0.001,
        'rate_limit': 100,
        'rest_url': 'https://www.okx.com',
        'use_proxy': False
    }
}

# Торговые пары для мониторинга
# ВАЖНО: На WhiteBit с DUSDT работает только DBTC/DUSDT пара!
TRADING_PAIRS = [
    'BTC/USDT',   # Bitcoin - будет маппиться на DBTC/DUSDT на WhiteBit
    'ETH/USDT',
    'XRP/USDT',
    'SOL/USDT',
    'DOGE/USDT',
]

# Альтернативный вариант: конвертировать BTC в USDT на Phemex
# У нас 0.98 BTC * ~$108,000 = ~$106,000 эквивалент
PHEMEX_BTC_TO_USDT_CONVERSION = {
    'enabled': True,  # Включить автоконвертацию BTC→USDT при необходимости
    'btc_balance': 0.98,  # Доступный BTC баланс
    'convert_amount': 0.01,  # Конвертировать 0.01 BTC (~$1080) в USDT для торговли
}

# Торговые настройки для TESTNET
TRADING_CONFIG = {
    'mode': 'real',  # ✅ REAL режим для исполнения ордеров
    'dry_run': False,  # Режим симуляции (без размещения ордеров); может быть переопределён через --dry-run
    'min_profit_threshold': 0.30,  # 0.30% минимальная прибыль (комиссии 0.10% + профит 0.20%)
    'slippage_tolerance': 0.01,  # 1% slippage tolerance (снижено)
    'max_opportunity_age': 30,  # 30 секунд максимум
    'scan_interval': 1,  # Сканировать каждую секунду
    'enable_triangular': False,  # Отключаем треугольный (только межбиржевой)
    'enable_inter_exchange': True,  # Межбиржевой арбитраж
    'pair_cooldown_seconds': 30,  # 30 секунд между сделками по паре (защита от частых сделок)
    'position_size_usd': 10.0,  # Размер позиции $10 (у нас есть $109 USDT)
    'use_websocket': False,  # Используем REST для стабильности
    'max_reasonable_spread_pct': 50.0,  # Фильтр аномальных спредов (расширено для тестнета)
    'max_concurrent_positions': 5,  # Максимум 5 позиций одновременно
    'use_maker_orders': False,  # Отключаем мейкер-ордера для повышения вероятности исполнения
    # Настройка для WhiteBit: автоопределение USDT/DUSDT
    'force_whitebit_usdt': True,  # True = использовать USDT (автоматически заменится на DUSDT если нет USDT)
    # Стратегия для малого USDT баланса
    'phemex_low_usdt_mode': True,  # Режим малого USDT баланса
    'phemex_usdt_balance': 0.72,  # Текущий USDT баланс
    'phemex_btc_balance': 0.98,  # BTC баланс (можно конвертировать при необходимости)
    # Автодокупка базового актива на стороне продажи для активных пар (prewarm)
    # Покупает базу под одну целевую позицию (position_size_usd) на бирже-продаже.
    'prewarm_sell_inventory': True,  # Включено - автопокупка базовых активов
    'prewarm_exchanges': ['whitebit', 'phemex'],  # Биржи для прогреваем prewarm для WhiteBit!
    'prewarm_max_usd_per_asset': 30.0,  # $30 на актив (у нас есть 945 DUSDT)
    'prewarm_max_pairs': 5,  # Покупаем активы только для 5 выбранных пар
    # Вывод балансов в реальном времени в терминал
    'realtime_balances': True,
    'realtime_balances_interval': 5,   # сек
    'realtime_balances_max_pairs': 6,  # показывать до 6 активных пар
}

# Динамическая подгрузка пар на основе волатильности
DYNAMIC_PAIRS_CONFIG = {
    'enabled': True,  # Включаем динамическую подгрузку
    'max_pairs': 20,  # Максимальное количество пар для отслеживания
    'update_interval': 300,  # Обновляем список каждые 5 минут
    'min_volume_usd': 10000,  # Минимальный объем (снижен для тестнета)
    'priority_pairs': [  # Приоритетные пары, всегда в списке
        'BTC/USDT',
        'ETH/USDT',
        'XRP/USDT',
        'SOL/USDT',
        'DOGE/USDT',
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
