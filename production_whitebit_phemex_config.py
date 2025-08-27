#!/usr/bin/env python3
"""
🚀 WHITEBIT-PHEMEX ПРОИЗВОДСТВЕННАЯ КОНФИГУРАЦИЯ
Оптимизированная конфигурация для прибыльного межбиржевого арбитража
WhiteBit (demo токены, реальные ордера) ↔ Phemex (testnet, реальные сделки)
"""

import logging

# API ключи для целевых бирж
API_KEYS = {
    'whitebit': {
        'apiKey': '548ae5005460f62d1c587280c39851da',
        'secret': '349ee8428847596a1298c4996ff5b51e',
        'passphrase': '',
        'demo_mode': True,  # Demo режим с DUSDT токенами
        'real_orders': True  # НО реальные ордера в истории!
    },
    'phemex': {
        'apiKey': '17ecc3c1-4f21-44a1-b306-703cee649d03',
        'secret': '73VZrCx2JZPv5b2bRi9-aIBT03asrkIOUxVGXQGSWMc1OGY0MWQ4My0yNGYxLTQ1NzgtOGE5YS0yY2YzZjdiNjBlODU',
        'testnet_mode': True,  # Testnet с ~1 BTC балансом
        'real_orders': True,   # Реальные ордера в testnet истории
        # URLs не переопределяем вручную — используем set_sandbox_mode(True)
    }
}

# ТОЛЬКО 2 целевые биржи для арбитража
EXCHANGES_CONFIG = {
    # ОТКЛЮЧАЕМ ВСЕ ЛИШНИЕ БИРЖИ
    'mexc': {'enabled': False},
    'gate': {'enabled': False}, 
    'okx': {'enabled': False},
    'bitget': {'enabled': False},
    'bybit': {'enabled': False},
    'binance': {'enabled': False},
    'huobi': {'enabled': False},
    'kucoin': {'enabled': False},
    'kraken': {'enabled': False},
    'pionex': {'enabled': False},
    
    # АКТИВНЫ ТОЛЬКО ЭТИ ДВЕ БИРЖИ
    'whitebit': {
        'enabled': True,
        'trading_enabled': True,
        'poll_rest': True,
        'poll_interval': 2,  # Каждые 2 секунды для синхронности
        'use_proxy': False,
        'fee': 0.001,  # 0.10% базовая комиссия taker
        'rate_limit': 300,
        'rest_url': 'https://whitebit.com/api/v4',
        'demo_mode': True,  # Демо токены DUSDT
    },
    'phemex': {
        'enabled': True,
        'trading_enabled': True,
        'poll_rest': True,
        'poll_interval': 2,
        'use_proxy': False,
        'fee': 0.001,  # 0.10% базовая комиссия taker
        'rate_limit': 200,
        'testnet_mode': True,  # Testnet режим
    }
}

# ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ ДЛЯ ПРИБЫЛЬНОСТИ
TRADING_CONFIG = {
    'mode': 'real',  # ✅ РЕАЛЬНЫЕ ордера в истории обеих бирж
    
    # 🎯 ПРИБЫЛЬНОСТЬ: агрессивное обнаружение возможностей (даже убыточных для мониторинга)
    'min_profit_threshold': 0.30,   # +0.30% минимальная положительная прибыль
    'slippage_tolerance': 0.0005,  # 0.05% slippage (исправлено: было 5%!)
    'max_opportunity_age': 15,     # 15 секунд максимум
    
    # 📊 СКАНИРОВАНИЕ  
    'scan_interval': 0.8,          # Каждую 0.8 секунды (ускоренное обнаружение)
    'max_reasonable_spread_pct': 15.0,  # Фильтр аномального спреда (например, дисбалансы тестнета)
    'enable_inter_exchange': True, # ✅ ГЛАВНАЯ СТРАТЕГИЯ
    'enable_triangular': False,    # Отключаем треугольный
    'enable_exhaustive_pair_scanning': False,  # Фокусируемся на качестве
    
    # 💰 ПОЗИЦИОНИРОВАНИЕ  
    'position_size_usd': 50.0,     # $50 на сделку (выше минимума WhiteBit $5)
    'pair_cooldown_seconds': 60,   # 60 сек между сделками по паре
    'max_concurrent_positions': 5, # Максимум 5 позиций одновременно
    
    # ⚡ СКОРОСТЬ ИСПОЛНЕНИЯ
    'use_maker_orders': True,      # Maker для нулевых комиссий!
    'use_websocket': True,         # WebSocket для реального времени
    'websocket_enabled': True,     # Принудительное включение WebSocket
    
    # 🔍 АНАЛИЗ ЛИКВИДНОСТИ
    'min_liquidity_usd': 500,       # $500 минимальная ликвидность (50% от позиции)
    'max_price_impact_pct': 2.0,   # 2% максимальное влияние на цену
    'min_depth_levels': 2          # Минимум 2 уровня в стакане
}

# ДИНАМИЧЕСКОЕ ОБНАРУЖЕНИЕ ПАР - ФОКУС НА ЛИКВИДНЫХ
DYNAMIC_PAIRS_CONFIG = {
    'enabled': True,
    'update_interval': 3600,  # 1 час
    'min_exchanges': 2,       # Обе наши биржи
    'max_pairs': 50,          # Увеличиваем до 50 пар с WebSocket
    'min_volume_24h': 5000000,  # $5M минимальный объем
    
    # ПРИОРИТЕТНЫЕ ПАРЫ с высокой ликвидностью и волатильностью
    'priority_pairs': [
        # Топ криптовалюты с высокой ликвидностью (приоритет)
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'MATIC/USDT', 'DOT/USDT', 'AVAX/USDT',
        'DOGE/USDT', 'XRP/USDT', 'ADA/USDT', 'LTC/USDT', 'LINK/USDT', 'UNI/USDT',
        
        # Высоковолатильные пары (больше арбитражных возможностей)
        'ATOM/USDT', 'XLM/USDT', 'VET/USDT', 'FIL/USDT', 'TRX/USDT', 'ETC/USDT',
        'ALGO/USDT', 'MANA/USDT', 'SAND/USDT', 'CRV/USDT', 'COMP/USDT', 'YFI/USDT',
        
        # Активные DeFi токены
        'SUSHI/USDT', '1INCH/USDT', 'BAT/USDT', 'ENJ/USDT', 'ZRX/USDT', 'NEAR/USDT',
        'FTM/USDT', 'RUNE/USDT', 'CAKE/USDT', 'ALPHA/USDT', 'BNT/USDT', 'KSM/USDT',
        
        # Новые трендовые пары
        'OCEAN/USDT', 'REN/USDT', 'XMR/USDT', 'EOS/USDT', 'XTZ/USDT', 'FLOW/USDT',
        
        # Дополнительные высоколиквидные пары для увеличения возможностей
        'BNB/USDT', 'TON/USDT', 'ICP/USDT', 'APT/USDT', 'OP/USDT', 'ARB/USDT',
        'SUI/USDT', 'SEI/USDT', 'WLD/USDT', 'TIA/USDT', 'STRK/USDT', 'ORDI/USDT'
    ]
}

# КОНСЕРВАТИВНЫЙ РИСК-МЕНЕДЖМЕНТ
RISK_MANAGEMENT = {
    'max_daily_loss': 25.0,        # $25 максимальный дневной убыток
    'max_concurrent_positions': 2,  # 2 позиции максимум
    'max_portfolio_risk': 0.03,    # 3% риск портфеля
    'max_position_risk': 0.01,     # 1% риск на позицию
    'stop_loss': 75.0,             # $75 стоп-лосс
    'take_profit': 150.0,          # $150 тейк-профит
    'blacklist_after_losses': 3,   # Блок пары после 3 убытков
    'cooldown_period_minutes': 30  # 30 минут охлаждения
}

# ЛОГИРОВАНИЕ И МОНИТОРИНГ
LOGGING_CONFIG = {
    'level': logging.INFO,
    'format': '%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
    'date_format': '%H:%M:%S',
    'file': 'whitebit_phemex_arbitrage.log',
    'trades_file': 'whitebit_phemex_trades.csv',
    'opportunities_file': 'whitebit_phemex_opportunities.csv'
}

# WEBSOCKET ОТКЛЮЧЕН
WEBSOCKET_CONFIG = {
    'enabled': True,  # Включаем WebSocket для реального времени
    'ping_interval': 20,
    'ping_timeout': 10,
    'max_reconnect_attempts': 3
}

# ПРОИЗВОДИТЕЛЬНОСТЬ
PERFORMANCE_CONFIG = {
    'use_uvloop': True,
    'parallel_requests': True,
    'batch_size': 10,
    'price_cache_ttl': 3  # 3 секунды TTL
}

def validate_whitebit_phemex_config():
    """Валидация специализированной конфигурации"""
    errors = []
    warnings = []
    
    # Проверка API ключей
    if not API_KEYS['whitebit']['apiKey'] or not API_KEYS['whitebit']['secret']:
        errors.append("❌ WhiteBit API ключи отсутствуют")
        
    if not API_KEYS['phemex']['apiKey'] or not API_KEYS['phemex']['secret']:
        errors.append("❌ Phemex API ключи отсутствуют")
    
    # Проверка активности бирж
    if not EXCHANGES_CONFIG['whitebit']['enabled']:
        errors.append("❌ WhiteBit отключен")
    if not EXCHANGES_CONFIG['phemex']['enabled']:
        errors.append("❌ Phemex отключен")
    
    # Проверка прибыльности
    total_fees = EXCHANGES_CONFIG['whitebit']['fee'] + EXCHANGES_CONFIG['phemex']['fee']
    total_fees_pct = total_fees * 100
    min_profit_pct = float(TRADING_CONFIG['min_profit_threshold'])
    
    if min_profit_pct <= total_fees_pct:
        warnings.append(f"⚠️ Минимальная прибыль {min_profit_pct:.2f}% <= комиссии {total_fees_pct:.2f}% — убыточно")
    
    # Проверка размера позиции vs ликвидности
    if TRADING_CONFIG['position_size_usd'] > TRADING_CONFIG['min_liquidity_usd']:
        warnings.append("⚠️ Размер позиции больше минимальной ликвидности")
    
    return errors, warnings

def print_config_summary():
    """Печать краткого обзора конфигурации"""
    print("\n" + "="*60)
    print("🚀 WHITEBIT-PHEMEX АРБИТРАЖНАЯ КОНФИГУРАЦИЯ")
    print("="*60)
    
    # Биржи
    print(f"📊 Биржи: WhiteBit (demo) ↔ Phemex (testnet)")
    
    # Комиссии
    wb_fee = EXCHANGES_CONFIG['whitebit']['fee'] * 100
    ph_fee = EXCHANGES_CONFIG['phemex']['fee'] * 100
    total_fee = wb_fee + ph_fee
    print(f"💸 Комиссии: WhiteBit {wb_fee:.2f}% + Phemex {ph_fee:.2f}% = {total_fee:.2f}%")
    
    # Прибыльность
    min_profit = TRADING_CONFIG['min_profit_threshold']
    print(f"💰 Минимальная прибыль: {min_profit:.2f}%")
    
    # Позиционирование
    pos_size = TRADING_CONFIG['position_size_usd']
    print(f"🎯 Размер позиции: ${pos_size:.0f}")
    
    # Частота
    scan_interval = TRADING_CONFIG['scan_interval']
    print(f"⏱️ Частота сканирования: {scan_interval:.2f} сек")
    print(f"🔎 Фильтр спреда (max): {TRADING_CONFIG['max_reasonable_spread_pct']:.2f}%")
    
    # Пары
    num_pairs = len(DYNAMIC_PAIRS_CONFIG['priority_pairs'])
    print(f"📈 Приоритетных пар: {num_pairs}")
    
    print("="*60)

if __name__ == "__main__":
    errors, warnings = validate_whitebit_phemex_config()
    
    if errors:
        print("❌ ОШИБКИ КОНФИГУРАЦИИ:")
        for error in errors:
            print(f"  {error}")
    
    if warnings:
        print("⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"  {warning}")
    
    if not errors:
        print_config_summary()
        print("✅ Конфигурация валидна и готова к использованию!")
