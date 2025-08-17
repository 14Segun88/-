#!/usr/bin/env python3
"""
🚀 MEGA ARBITRAGE BOT v2.0
Межбиржевой + Треугольный арбитраж
50 монет | Минимальные комиссии | Автосохранение каждые 10 минут
"""

# -*- coding: utf-8 -*-
import asyncio
import json
import aiohttp
import aiohttp_socks
import pandas as pd
import sys
import numpy as np
import ccxt.async_support as ccxt
import json
import time
import websockets
from typing import Dict, List, Optional, Set, Any
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import os
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# Импорт новых модулей
try:
    from demo_config import *
    print("✅ Конфигурация демо торговли загружена успешно")
    DEMO_MODE = (TRADING_MODE == "DEMO") if 'TRADING_MODE' in locals() else True
except ImportError:
    print("⚠️ Конфигурация демо не найдена, используются стандартные настройки")
    DEMO_MODE = True

try:
    from risk_manager import RiskManager, RiskLimits
    from order_executor import OrderExecutor
    print("✅ Модули управления загружены")
except ImportError as e:
    print(f"⚠️ Модули управления не найдены: {e}")
    RiskManager = None
    OrderExecutor = None

import math
import traceback
import argparse

# Опционально ускоряем event loop при наличии uvloop
try:
    import uvloop  # type: ignore
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    UVLOOP_ENABLED = True
except Exception:
    UVLOOP_ENABLED = False

# ==================== КОНФИГУРАЦИЯ ====================

# URL для прокси, например 'socks5://user:pass@host:port' или 'http://host:port'. Оставить пустым, чтобы не использовать прокси.
PROXY_URL = ""  # <-- ВСТАВЬТЕ ВАШ URL ПРОКСИ СЮДА

# ==================== ТОРГОВЫЕ НАСТРОЙКИ ====================
TRADING_ENABLED = os.getenv('TRADING_ENABLED', 'false').lower() == 'true'
PAPER_TRADING = True

# --- Финансовые параметры для симуляции ---
INITIAL_CAPITAL = 10000  # Начальный капитал для симуляции
POSITION_SIZE_PCT = 1.0  # Размер позиции как % от капитала (1.0 = 1%)
INTER_MIN_PROFIT_PCT = 0.15  # Минимальная чистая прибыль для межбиржевой сделки
STALE_MS = 1500  # Максимальный возраст цены в мс для учета в арбитраже

# Размеры позиций
DEFAULT_POSITION_SIZE_USD = float(os.getenv('POSITION_SIZE_USD', '100'))  # $100 по умолчанию
MAX_POSITION_SIZE_USD = float(os.getenv('MAX_POSITION_SIZE_USD', '1000'))
MIN_POSITION_SIZE_USD = float(os.getenv('MIN_POSITION_SIZE_USD', '20'))

# Риск-менеджмент
MAX_DAILY_LOSS_USD = float(os.getenv('MAX_DAILY_LOSS_USD', '200'))
MAX_HOURLY_LOSS_USD = float(os.getenv('MAX_HOURLY_LOSS_USD', '50'))
MAX_CONCURRENT_TRADES = int(os.getenv('MAX_CONCURRENT_TRADES', '5'))
MIN_ACCOUNT_BALANCE_USD = float(os.getenv('MIN_ACCOUNT_BALANCE_USD', '500'))
# Бумажный стартовый депозит (для счётчика PnL)
PAPER_START_BALANCE_USD = float(os.getenv('PAPER_START_BALANCE_USD', '10000'))

# Дополнительные параметры риск-менеджмента
STOP_LOSS_PERCENT = float(os.getenv('STOP_LOSS_PERCENT', '2.0'))  # Stop-loss в процентах
TAKE_PROFIT_PERCENT = float(os.getenv('TAKE_PROFIT_PERCENT', '1.0'))  # Take-profit в процентах
MAX_SLIPPAGE_PERCENT = float(os.getenv('MAX_SLIPPAGE_PERCENT', '0.5'))  # Максимальный слиппедж

# Исполнение ордеров
ORDER_TIMEOUT_MS = int(os.getenv('ORDER_TIMEOUT_MS', '3000'))  # 3 секунды
FILL_TIMEOUT_MS = int(os.getenv('FILL_TIMEOUT_MS', '5000'))  # 5 секунд
CSV_SAVE_INTERVAL = int(os.getenv('CSV_SAVE_INTERVAL', '600'))  # 10 минут
MAX_SLIPPAGE_PCT = float(os.getenv('MAX_SLIPPAGE_PCT', '0.1'))  # 0.1% максимальный слиппедж
EXECUTION_LATENCY_THRESHOLD_MS = int(os.getenv('EXECUTION_LATENCY_MS', '200'))  # 200мс порог

# Порог исполнения межбиржевого (для реальных/бумажных сделок)
EXEC_INTER_MIN_NET = float(os.getenv('EXECUTE_INTER_MIN_NET', '0.5'))  # % чистой прибыли для запуска сделки
# Интервал сканирования в секундах
SCAN_INTERVAL_SECONDS = int(os.getenv('SCAN_INTERVAL_SECONDS', '2'))

# Кулдаун между повторными сделками по одному и тому же маршруту (символ + buy/sell биржи)
EXEC_ROUTE_COOLDOWN_MS = int(os.getenv('EXEC_ROUTE_COOLDOWN_MS', '2000'))
# Слиппедж для моделирования исполнения межбиржи (как доля, 0.0002 = 0.02%)
INTER_SLIPPAGE_PCT = float(os.getenv('INTER_SLIPPAGE_PCT', '0.0002'))
# L2 данные
ORDERBOOK_DEPTH = int(os.getenv('ORDERBOOK_DEPTH', '20'))  # Глубина стакана
MIN_LIQUIDITY_USD = float(os.getenv('MIN_LIQUIDITY_USD', '1000'))  # Минимальная ликвидность
ORDERBOOK_STALE_MS = int(os.getenv('ORDERBOOK_STALE_MS', '1500'))  # Максимальная «свежесть» L2
USE_L2_ON_PAPER = os.getenv('USE_L2_ON_PAPER', 'true').lower() == 'true'  # Использовать L2/VWAP в бумажном исполнении
# Дополнительный буфер к порогу при L2-предфильтре (в процентах, абсолютные п.п.)
L2_EXEC_BUFFER_PCT = float(os.getenv('L2_EXEC_BUFFER_PCT', '0.15'))
# Глубина стакана для анализа ликвидности
ORDERBOOK_DEPTH = int(os.getenv('ORDERBOOK_DEPTH', '20'))
# Минимальная доля позиции, которая должна быть исполнена по L2 анализу
MIN_FILL_RATIO = float(os.getenv('MIN_FILL_RATIO', '0.8'))
# Минимальный размер сделки в USD, чтобы избежать пыли
MIN_TRADE_SIZE_USD = float(os.getenv('MIN_TRADE_SIZE_USD', '10.0'))
# Как часто можно обновлять стакан для одной пары (в мс)
ORDERBOOK_MIN_REFRESH_MS = int(os.getenv('ORDERBOOK_MIN_REFRESH_MS', '1000'))
# Как долго считать стакан актуальным (в мс)
ORDERBOOK_STALE_MS = int(os.getenv('ORDERBOOK_STALE_MS', '5000'))

# API ключи будут читаться в __init__ для корректного получения переменных окружения

# САМЫЕ ДЕШЕВЫЕ БИРЖИ ПО КОМИССИЯМ
EXCHANGES = {
    'mexc': {
        'ticker_url': 'https://api.mexc.com/api/v3/ticker/bookTicker',
        'orderbook_url': 'https://api.mexc.com/api/v3/depth?symbol={symbol}&limit=10',
        'fee_maker': 0.0,  # 0% maker fee!
        'fee_taker': 0.001,  # 0.10% taker (со скидками/промо)
        'name': 'MEXC'
    },
    'binance': {
        'ticker_url': 'https://api.binance.com/api/v3/ticker/bookTicker',
        'orderbook_url': 'https://api.binance.com/api/v3/depth?symbol={symbol}&limit=10',
        'fee_maker': 0.00075,  # 0.075% с BNB
        'fee_taker': 0.00075,
        'name': 'Binance'
    },
    'okx': {
        'ticker_url': 'https://www.okx.com/api/v5/market/tickers?instType=SPOT',
        'orderbook_url': 'https://www.okx.com/api/v5/market/books?instId={symbol}&sz=10',
        'fee_maker': 0.0008,  # 0.08%
        'fee_taker': 0.001,   # 0.1%
        'name': 'OKX'
    },
    'bybit': {
        'ticker_url': 'https://api.bybit.com/v5/market/tickers?category=spot',
        'orderbook_url': 'https://api.bybit.com/v5/market/depth?category=spot&symbol={symbol}&limit=10',
        'fee_maker': 0.0008,  # 0.08% со скидкой/уровнем
        'fee_taker': 0.0008,  # 0.08% со скидкой/уровнем
        'name': 'Bybit'
    },
    'kucoin': {
        'ticker_url': 'https://api.kucoin.com/api/v1/market/allTickers',
        'orderbook_url': 'https://api.kucoin.com/api/v1/market/orderbook/level2_20?symbol={symbol}',
        'fee_maker': 0.0008,  # 0.08% с KCS-скидкой/уровнем
        'fee_taker': 0.0008,  # 0.08% с KCS-скидкой/уровнем
        'name': 'KuCoin'
    }
}

# ТОП-100+ МОНЕТ ДЛЯ МЕЖБИРЖЕВОГО АРБИТРАЖА
INTER_EXCHANGE_SYMBOLS = [
    # Основные (топ-20)
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
    'ADAUSDT', 'AVAXUSDT', 'DOGEUSDT', 'DOTUSDT', 'MATICUSDT',
    'LTCUSDT', 'BCHUSDT', 'ETCUSDT', 'XLMUSDT', 'ATOMUSDT',
    'FILUSDT', 'VETUSDT', 'NEARUSDT', 'ALGOUSDT', 'FTMUSDT',
    
    # DeFi & Layer 2 (20)
    'UNIUSDT', 'LINKUSDT', 'AAVEUSDT', 'OPUSDT', 'ARBUSDT',
    'INJUSDT', 'SEIUSDT', 'SUIUSDT', 'APTUSDT', 'STXUSDT',
    'MKRUSDT', 'SNXUSDT', 'COMPUSDT', 'CRVUSDT', 'SUSHIUSDT',
    'YFIUSDT', 'LDOUSDT', 'RPLUSUSDT', '1INCHUSDT', 'BALUSDT',
    
    # Meme coins (20)
    'PEPEUSDT', 'SHIBUSDT', 'FLOKIUSDT', 'WIFUSDT', 'BONKUSDT',
    'MEMEUSDT', 'BABYDOGEUSDT', 'ELONUSDT', 'SAITAMAUSDT', 'KISHUUSDT',
    'AKITAUSDT', 'PITUSDT', 'SHIBADOGEUSDT', 'DOGELONUSDT', 'SAMUSDT',
    'CATECOINUSDT', 'BABYSHIBUSDT', 'METAMONUSDT', 'PONKEUSDT', 'MYRIUSDT',
    
    # Gaming & Metaverse (20)
    'AXSUSDT', 'SANDUSDT', 'MANAUSDT', 'GALAUSDT', 'ENJUSDT',
    'IMXUSDT', 'GMTUSDT', 'APEUSDT', 'ROSEUSDT', 'ALICEUSDT',
    'ILVUSDT', 'TLMUSDT', 'EPIKUSDT', 'MOBOXUSDT', 'DARUSDT',
    'SLPUSDT', 'GHSTUSDT', 'SUPERUSDT', 'UOSUSDT', 'PYRUSDT',
    
    # AI & новые проекты (20)
    'FETUSDT', 'AGIXUSDT', 'OCEANUSDT', 'RNDRUSDT', 'GRTUSDT',
    'ARKMUSDT', 'WLDUSDT', 'JASMYUSDT', 'CELOUSDT', 'PENDLEUSDT',
    'CTXCUSDT', 'PHBUSDT', 'NMRUSDT', 'IOTXUSDT', 'MDTUSDT',
    'AIUSDT', 'IQUSDT', 'VAIOTUSDT', 'OASUSDT', 'SINGUSDT',
    
    # Дополнительные волатильные (20)
    'TRBUSDT', 'GASUSDT', 'BLURUSDT', 'EDUUSDT', 'IDUSDT',
    'ARBUSDT', 'MAGICUSDT', 'JOEUSDT', 'HOOKUSDT', 'HIGHUSDT',
    'ASTRUSDT', 'GMXUSDT', 'CFXUSDT', 'STGUSDT', 'MASKUSDT',
    'LQTYUSDT', 'PERPUSDT', 'ACHUSDT', 'SSVUSDT', 'RADUSDT'
]

# ТОП-50 МОНЕТ ДЛЯ ТРЕУГОЛЬНОГО АРБИТРАЖА НА КАЖДОЙ БИРЖЕ
TRIANGULAR_SYMBOLS = {
    'binance': [
        # Основные пары Binance
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT',
        'SHIBUSDT', 'LTCUSDT', 'UNIUSDT', 'LINKUSDT', 'BCHUSDT',
        'XLMUSDT', 'ATOMUSDT', 'ETCUSDT', 'VETUSDT', 'FILUSDT',
        'TRXUSDT', 'NEARUSDT', 'AAVEUSDT', 'SANDUSDT', 'MANAUSDT',
        'ALGOUSDT', 'ICPUSDT', 'QNTUSDT', 'FTMUSDT', 'EOSUSDT',
        'EGLDUSDT', 'THETAUSDT', 'AXSUSDT', 'HBARUSDT', 'XTZUSDT',
        'CHZUSDT', 'MKRUSDT', 'ENJUSDT', 'RUNEUSDT', 'ZILUSDT',
        'SNXUSDT', 'BATUSDT', 'DASHUSDT', 'ZECUSDT', 'COMPUSDT',
        'CRVUSDT', 'KSMUSDT', 'WAVESUSDT', 'ONEUSDT', 'HOTUSDT'
    ],
    'okx': [
        # Основные пары OKX
        'BTCUSDT', 'ETHUSDT', 'OKBUSDT', 'SOLUSDT', 'XRPUSDT',
        'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'MATICUSDT',
        'SHIBUSDT', 'LTCUSDT', 'UNIUSDT', 'LINKUSDT', 'BCHUSDT',
        'ATOMUSDT', 'ETCUSDT', 'NEARUSDT', 'FILUSDT', 'VETUSDT',
        'ICPUSDT', 'APTUSDT', 'OPUSDT', 'ARBUSDT', 'INJUSDT',
        'SUIUSDT', 'SEIUSDT', 'STXUSDT', 'TRXUSDT', 'XLMUSDT',
        'EOSUSDT', 'AAVEUSDT', 'ALGOUSDT', 'SANDUSDT', 'FTMUSDT',
        'GALAUSDT', 'GMTUSDT', 'MASKUSDT', 'WLDUSDT', 'ORDIUSDT',
        'BLURUSDT', 'JOEUSDT', 'MAGICUSDT', 'TRBUSDT', 'PERPUSDT',
        'SSVUSDT', 'PENUSDT', 'CYBERUSDT', 'ARKMUSDT', 'WIFUSDT'
    ],
    'mexc': [
        # Основные пары MEXC (включая новые листинги)
        'BTCUSDT', 'ETHUSDT', 'MXUSDT', 'SOLUSDT', 'XRPUSDT',
        'PEPEUSDT', 'SHIBUSDT', 'DOGEUSDT', 'FLOKIUSDT', 'BONKUSDT',
        'WIFUSDT', 'MEMEUSDT', 'BOBUSDT', 'TURBOUSDT', 'LADYSUSDT',
        'BABYDOGEUSDT', 'ELONUSDT', 'KISHUUSDT', 'SAMOUSDT', 'WOJAKUSDT',
        'PEPECOINUSDT', 'ARBUSDT', 'OPUSDT', 'INJUSDT', 'SUIUSDT',
        'APTUSDT', 'SEIUSDT', 'KASUSDT', 'TOMIUSDT', 'GPTUSDT',
        'BNXUSDT', 'IDUSDT', 'EDUUSDT', 'SPACEIDUSDT', 'MAVUSDT',
        'PENUSDT', 'PENDLEUSDT', 'JOEUSDT', 'RDNTUSDT', 'AIUSDT',
        'FETUSDT', 'AGIXUSDT', 'OCEANUSDT', 'RNDRUSDT', 'PHBUSDT',
        'ARKMUSDT', 'WLDUSDT', 'CTXCUSDT', 'IQUSDT', 'NMRUSDT'
    ],
    'bybit': [
        # Основные пары Bybit (USDT)
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
        'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'DOTUSDT', 'SHIBUSDT',
        'TRXUSDT', 'LINKUSDT', 'LTCUSDT', 'OPUSDT', 'ARBUSDT',
        'APTUSDT', 'SUIUSDT', 'SEIUSDT', 'NEARUSDT', 'ATOMUSDT',
        'FILUSDT', 'AAVEUSDT', 'INJUSDT', 'MASKUSDT', 'LDOUSDT',
        'MAGICUSDT', 'SNXUSDT', 'GMXUSDT', 'PEPEUSDT', 'WLDUSDT'
    ],
    'kucoin': [
        # Основные пары KuCoin (USDT)
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
        'DOGEUSDT', 'AVAXUSDT', 'MATICUSDT', 'DOTUSDT', 'SHIBUSDT',
        'TRXUSDT', 'LINKUSDT', 'LTCUSDT', 'OPUSDT', 'ARBUSDT',
        'APTUSDT', 'SUIUSDT', 'SEIUSDT', 'NEARUSDT', 'ATOMUSDT',
        'FILUSDT', 'AAVEUSDT', 'INJUSDT', 'MASKUSDT', 'LDOUSDT',
        'MAGICUSDT', 'SNXUSDT', 'GMXUSDT', 'PEPEUSDT', 'WLDUSDT'
    ]
}

# Набор необходимых пар для треугольников по каждой бирже
# Строим AUSDT, BUSDT и кроссы AB/BA из списков TRIANGULAR_SYMBOLS
NEEDED_TRI_PAIRS_PER_EXCHANGE = {ex: set() for ex in EXCHANGES.keys()}
for ex, usdt_symbols in TRIANGULAR_SYMBOLS.items():
    coins = [s[:-4] for s in usdt_symbols if s.endswith('USDT') and len(s) > 4]
    for i, a in enumerate(coins):
        for b in coins[i+1:]:
            NEEDED_TRI_PAIRS_PER_EXCHANGE[ex].update({
                f"{a}USDT", f"{b}USDT", f"{a}{b}", f"{b}{a}"
            })

# Параметры
MIN_PROFIT_INTER = -0.01  # -0.01% (фиксируем даже убыток для анализа)
MIN_PROFIT_TRI = -0.01    # -0.01% для треугольного
MIN_PROFIT_THRESHOLD = 0.25  # Минимальная прибыль 0.25% (снижено для большего количества сделок)
MIN_PROFIT_THRESHOLD_TRI = 0.20  # Для треугольного арбитража 0.20%

# Адаптивные пороги в зависимости от волатильности
ADAPTIVE_THRESHOLD_ENABLED = True
VOLATILITY_MULTIPLIER = 0.8  # Коэффициент для адаптации порога считаем прибылью
SCAN_INTERVAL = 1         # секунд между сканами (чаще для большего покрытия)
SAVE_INTERVAL = 300       # 300 секунд = 5 минут
TRI_SLIPPAGE_PER_STEP = 0.0003  # 0.03% слиппедж на шаг

# Низкозадержательная событийная обработка межбиржевого (вместо батч-скана)
EVENT_INTER_ENABLED = True
EVENT_DEBOUNCE_MS = 50     # не чаще одного анализа на символ каждые N мс
EVENT_COALESCE_MS = 20     # сглаживаем бурст, собираем символы N мс
STALE_MS = 1500            # игнорируем котировки старше N мс
EVENT_INTER_PRINT_MIN = 0.10  # печатать события только если net_profit ≥ 0.10%
MAX_PROFIT_THRESHOLD_PCT = 25.0 # Не печатать события с аномально высокой прибылью ( > 25%)

# РЕЖИМ WS ДЛЯ НИЗКОЙ ЗАДЕРЖКИ
# На первом шаге включаем WS только для Bybit (остальные оставляем на REST, подключим последовательно)
USE_WS = True
WS_EXCHANGES = {
    'bybit': True,
    'okx': False,  # Используем REST API для стабильности
    'kucoin': False,  # Используем REST API для стабильности
    'mexc': False,  # Используем REST API для стабильности
    'binance': True,   # Включаем WS через прокси
}

# ==================== АРБИТРАЖНЫЙ БОТ ====================

class MegaArbitrageBot:
    def __init__(self, mode: str = 'both'):
        # Инициализация HTTP сессий
        timeout = aiohttp.ClientTimeout(total=10)

        # Прямая сессия для бирж без прокси
        self.direct_session = aiohttp.ClientSession(timeout=timeout)

        # Сессия с прокси для Binance
        proxy_connector = None
        if PROXY_URL:
            proxy_connector = aiohttp_socks.ProxyConnector.from_url(PROXY_URL)
            print(f"🔌 Для Binance будет использоваться прокси: {PROXY_URL}")
        self.proxy_session = aiohttp.ClientSession(timeout=timeout, connector=proxy_connector)

        # self.session будет указывать на сессию с прокси для совместимости с ccxt
        self.session = self.proxy_session
        self.prices = {}
        # WS
        self.ws_tasks: List[asyncio.Task] = []
        self.ws_connected = {ex: False for ex in EXCHANGES.keys()}
        self.ws_exchanges = [ex for ex, enabled in WS_EXCHANGES.items() if enabled]
        # Флаг работы фоновых циклов
        self.is_running = True
        # Режим работы: inter | tri | both
        self.mode = mode
        self.api_keys_valid = {}
        self.statistics = {
            'start_time': datetime.now(),
            'total_scans': 0,
            'inter_exchange_opportunities': [],
            'triangular_opportunities': [],
            'best_inter_exchange': None,
            'best_triangular': None,
            'total_inter_found': 0,
            'total_tri_found': 0,
            'inter_exchange_trades': 0,
            'tri_exchange_trades': 0,
            'breakeven_count': 0,
            'profit_count': 0,
            'loss_count': 0,
            'exchange_stats': {ex: {'success': 0, 'errors': 0} for ex in EXCHANGES},
            'pair_stats': {},
            'hourly_stats': []
        }
        self.last_save_time = time.time()
        # Лимитер для диагностических сообщений по треугольнику
        self._tri_diag_left = 10
        
        # Уникальные межбиржевые возможности (с момента запуска)
        # Ключ: (symbol, buy_exchange, sell_exchange)
        self.unique_inter_seen = set()
        self.unique_inter_count = 0
        self.unique_inter_profit_sum = 0.0  # Σ только положительных net_profit по уникальным маршрутам
        self.last_save_time = time.time()
        # Событийная обработка межбиржевого арбитража
        self._event_symbols = set()
        self._event_trigger = asyncio.Event()
        self._debounce = {}
        self._event_task: Optional[asyncio.Task] = None
        self._stop: Optional[bool] = None
        # Уникальные возможности
        self.unique_inter_routes = set()
        self.unique_inter_count = 0
        self.unique_inter_profit_sum = 0.0
        self.unique_tri_routes = set()
        self.unique_tri_count = 0
        self.unique_tri_profit_sum = 0.0
        
        # ==================== ТОРГОВАЯ ИНФРАСТРУКТУРА ====================
        # L2 Order Books
        self.orderbooks = {}  # {symbol: {exchange: {'bids': [[price, size], ...], 'asks': [...], 'ts': ts}}}
        self.ob_subscribed = set()  # Отслеживание подписок на L2
        self._ob_last_fetch_ms: Dict[Tuple[str, str], int] = {}
        self._ob_inflight: set = set()
        
        # Управление позициями и ордерами
        self.active_trades = {}  # {trade_id: trade_info}
        self.pending_orders = {}  # {order_id: order_info}
        # Для тестирования WS без API ключей, задаем пары вручную
        self.trading_pairs = []  # Список всех доступных торговых пар
        self.markets = {}  # Маркет инфо по биржам
        self.API_KEYS = list(EXCHANGES.keys())  # Список доступных бирж
        self.balances = {}  # {exchange: {asset: {'free': amount, 'locked': amount}}}
        
        # Риск-менеджмент
        self.daily_pnl = 0.0
        self.hourly_pnl = 0.0
        self.last_hour_reset = time.time()
        self.last_day_reset = time.time()
        self.risk_limits_hit = False
        
        # Метрики исполнения
        self.execution_stats = {
            'orders_placed': 0,
            'orders_filled': 0,
            'orders_cancelled': 0,
            'avg_latency_ms': 0.0,
            'fill_ratio': 0.0,
            'total_slippage': 0.0
        }
        
        # Счетчики для генерации уникальных ID
        self.trade_counter = 0
        self.order_counter = 0
        # Кулдаун по маршрутам (symbol, buy_ex, sell_ex) -> last_exec_ms
        self._last_route_exec_ms: Dict[Tuple[str, str, str], int] = {}
        # Журнал завершённых сделок (бумажных)
        self.completed_trades: List[Dict] = []
        self.symbols: Dict[str, List[str]] = {}
        self.symbol_meta: Dict[str, Dict[str, Dict]] = {} # {exchange: {symbol: {meta...}}}

        # Бумажный депозит и баланс
        self.paper_start_balance: float = 1000.0
        self.paper_balance: float = 1000.0
        self.paper_total_pnl: float = 0.0
        
        # ==================== НОВЫЕ МОДУЛИ УПРАВЛЕНИЯ ====================
        # Инициализация риск-менеджера
        if RiskManager:
            risk_limits = RiskLimits(
                max_position_size_usd=DEMO_SETTINGS.get('max_position_size', 100.0),
                max_daily_loss_usd=DEMO_SETTINGS.get('max_daily_loss', 50.0),
                max_open_positions=DEMO_SETTINGS.get('max_open_positions', 3),
                min_profit_threshold=DEMO_SETTINGS.get('min_profit_threshold', 0.3)
            )
            self.risk_manager = RiskManager(risk_limits)
            print("✅ Риск-менеджер инициализирован")
        else:
            self.risk_manager = None
            print("⚠️ Риск-менеджер не доступен")
        
        # Инициализация исполнителя ордеров (будет инициализирован после создания CCXT клиентов)
        self.order_executor = None
        
        # ==================== ЧТЕНИЕ И ИНИЦИАЛИЗАЦИЯ CCXT ====================
        API_KEYS = {
            'mexc': {'apiKey': os.getenv('MEXC_API_KEY'), 'secret': os.getenv('MEXC_API_SECRET')},
            'binance': {'apiKey': os.getenv('BINANCE_API_KEY'), 'secret': os.getenv('BINANCE_API_SECRET')},
            'okx': {'apiKey': os.getenv('OKX_API_KEY'), 'secret': os.getenv('OKX_API_SECRET'), 'password': os.getenv('OKX_API_PASSWORD')},
            'bybit': {'apiKey': os.getenv('BYBIT_API_KEY'), 'secret': os.getenv('BYBIT_API_SECRET')},
            'kucoin': {'apiKey': os.getenv('KUCOIN_API_KEY'), 'secret': os.getenv('KUCOIN_API_SECRET'), 'password': os.getenv('KUCOIN_API_PASSWORD')},
        }

        print("📔 Инициализация подключений к биржам через CCXT...")
        self.clients = {}
        for exchange_id in EXCHANGES.keys():
            self.api_keys_valid[exchange_id] = False
            keys = API_KEYS.get(exchange_id, {})
            
            if keys.get('apiKey') and keys.get('secret'):
                try:
                    config = {
                        'apiKey': keys['apiKey'],
                        'secret': keys['secret'],
                        'options': {'defaultType': 'spot'},
                        'enableRateLimit': True,
                        'session': self.proxy_session if exchange_id == 'binance' else self.direct_session
                    }
                    if 'password' in keys and keys.get('password'):
                        config['password'] = keys['password']

                    exchange_class = getattr(ccxt, exchange_id)
                    client = exchange_class(config)
                    self.clients[exchange_id] = client
                    setattr(self, exchange_id, client)
                    self.api_keys_valid[exchange_id] = True
                except Exception as e:
                    print(f"  🔴 Ошибка при инициализации {exchange_id.upper()}: {e}")
            else:
                print(f"  ⚠️  {EXCHANGES[exchange_id]['name'].upper()}: API ключи отсутствуют, подключение не создается.")

        # Сессионные счетчики прибыли (с момента запуска)
        self.session_start_time = time.time()
        self.session_profit_usd: float = 0.0
        self.session_profit_pct: float = 0.0
        self.session_trades: int = 0
        
        # Счетчики ошибок и retry логика
        self.error_counts = {ex: 0 for ex in EXCHANGES.keys()}
        
        # ==================== СТАТУС СКАНЕРА ДЛЯ ТЕРМИНАЛА ====================
        self.scanner_status = {
            'prices_updated': 0,
            'scans_performed': 0,
            'opportunities_found': 0,
            'last_price_update_ts': None,
            'last_scan_ts': None
        }
        
        # Статус трейдера для мониторинга
        self.trader_status = {
            'validator': {'active': False, 'checks_passed': 0, 'checks_failed': 0},
            'risk_manager': {'active': False, 'positions_approved': 0, 'positions_rejected': 0},
            'executor': {'active': False, 'orders_placed': 0, 'orders_filled': 0, 'orders_failed': 0},
            'tracker': {'active': False, 'trades_monitored': 0, 'trades_completed': 0}
        }
        
        # Инициализация исполнителя ордеров после создания CCXT клиентов
        # Соберем активные CCXT клиенты
        active_ccxt_clients = {}
        for exchange_id in EXCHANGES.keys():
            if hasattr(self, exchange_id):
                active_ccxt_clients[exchange_id] = getattr(self, exchange_id)
        
        if OrderExecutor and active_ccxt_clients:
            self.order_executor = OrderExecutor(active_ccxt_clients)
            print("✅ Исполнитель ордеров инициализирован")
        else:
            self.order_executor = None
            if not OrderExecutor:
                print("⚠️ Модуль OrderExecutor не доступен")
            else:
                print("⚠️ Нет активных CCXT клиентов для исполнителя ордеров")

    async def load_all_markets(self):
        """Загружает рынки (торговые пары и их метаданные) со всех активных бирж."""
        self.symbols = {}
        self.symbol_meta = {}
        active_exchanges = [ex for ex in self.API_KEYS if hasattr(self, ex)]
        tasks = [self.load_markets(ex_name) for ex_name in active_exchanges]
        await asyncio.gather(*tasks)
        
        # Создаем единый список уникальных символов, доступных на всех биржах
        all_symbols_original_format = set()
        for ex_symbols in self.symbols.values():
            all_symbols_original_format.update(ex_symbols)

        # Нормализуем символы с бирж (например, 'BTC/USDT' -> 'BTCUSDT') для сравнения
        # и сохраняем маппинг обратно в оригинальный формат
        normalized_exchange_symbols = {s.replace('/', ''): s for s in all_symbols_original_format}

        # Находим пересечение с нашим списком отслеживаемых символов
        target_symbols_set = set(INTER_EXCHANGE_SYMBOLS)
        common_normalized_symbols = target_symbols_set.intersection(normalized_exchange_symbols.keys())

        # Возвращаемся к оригинальному формату символов ('BTC/USDT'), который использует ccxt
        filtered_symbols = sorted([normalized_exchange_symbols[s] for s in common_normalized_symbols])

        # Сохраняем отфильтрованный список для дальнейшей работы
        self.common_symbols = filtered_symbols

    async def load_markets(self, exchange_name: str):
        """Загружает и обрабатывает рынки для одной биржи."""
        try:
            exchange = getattr(self, exchange_name)
            markets = await exchange.load_markets()
            self.symbols[exchange_name] = list(markets.keys())
            self.symbol_meta[exchange_name] = markets
            print(f"  ✅ {exchange_name.upper()}: загружено {len(self.symbols[exchange_name])} символов.")
        except Exception as e:
            print(f"  ⚠️  Не удалось загрузить рынки для {exchange_name.upper()}: {e}")
            self.symbols[exchange_name] = []
        self.max_errors_before_cooldown = 5
        self.cooldown_duration_ms = 60000  # 1 минута
        self.exchange_cooldowns = {}  # {exchange: cooldown_until_ms}
        
        # Валидация API ключей при старте
        self.api_keys_valid = self._validate_api_keys()
        
        # Rate limiting для каждой биржи
        self.rate_limiters = {
            'binance': {'requests': 0, 'reset_time': time.time(), 'limit': 1200, 'window': 60},
            'bybit': {'requests': 0, 'reset_time': time.time(), 'limit': 100, 'window': 60},
            'okx': {'requests': 0, 'reset_time': time.time(), 'limit': 60, 'window': 2},
            'kucoin': {'requests': 0, 'reset_time': time.time(), 'limit': 30, 'window': 1},
            'mexc': {'requests': 0, 'reset_time': time.time(), 'limit': 10, 'window': 1}
        }
        
        # Приватные WebSocket соединения
        self.private_ws_connected = {ex: False for ex in EXCHANGES.keys()}
        self.private_ws_tasks = []
        
        # Очередь исполнения ордеров
        self.order_queue = asyncio.Queue()
        self.order_processor_task = None
        
        # Реальные балансы с бирж
        self.real_balances = {}  # {exchange: {asset: amount}}
        self.balance_last_update = {}
        
        # Трекинг активных ордеров для реального режима
        self.active_orders = {}  # {order_id: {exchange, symbol, side, status, filled, remaining}}
        
    async def init_session(self):
        """Инициализация HTTP сессии"""
        timeout = aiohttp.ClientTimeout(total=10)
        connector = None
        if PROXY_URL:
            connector = aiohttp_socks.ProxyConnector.from_url(PROXY_URL)
            print(f"🔌 Сессия будет использовать прокси: {PROXY_URL}")
        # Включаем trust_env, чтобы aiohttp использовал HTTP_PROXY/HTTPS_PROXY
        self.session = aiohttp.ClientSession(timeout=timeout, trust_env=True, connector=connector)
        
    def _validate_api_keys(self) -> Dict[str, bool]:
        """Проверяет наличие API ключей для каждой биржи."""
        valid_keys = {}
        for exchange in EXCHANGES.keys():
            # В демо режиме считаем все ключи валидными
            if DEMO_MODE or PAPER_TRADING:
                valid_keys[exchange] = True
            else:
                # Проверяем наличие ключей в переменных окружения
                import os
                if exchange.upper() == 'BINANCE':
                    valid_keys[exchange] = bool(os.getenv('BINANCE_API_KEY'))
                elif exchange.upper() == 'BYBIT':
                    valid_keys[exchange] = bool(os.getenv('BYBIT_API_KEY'))
                elif exchange.upper() == 'KUCOIN':
                    valid_keys[exchange] = bool(os.getenv('KUCOIN_API_KEY') and os.getenv('KUCOIN_API_PASSPHRASE'))
                elif exchange.upper() == 'OKX':
                    valid_keys[exchange] = bool(os.getenv('OKX_API_KEY') and os.getenv('OKX_API_PASSPHRASE'))
                elif exchange.upper() == 'MEXC':
                    valid_keys[exchange] = bool(os.getenv('MEXC_API_KEY'))
                else:
                    valid_keys[exchange] = False
        
        return valid_keys
        
    def _quantize(self, value: float, precision: float) -> float:
        """Квантует значение до заданной точности (stepSize или tickSize).
        
        Args:
            value: Исходное значение для квантования
            precision: Шаг квантования (например, 0.001 для 3 знаков после запятой)
        
        Returns:
            Квантованное значение
        """
        if precision <= 0:
            return value
        
        # Определяем количество знаков после запятой
        decimals = max(0, -int(math.log10(precision)))
        
        # Округляем вниз до нужной точности
        quantized = math.floor(value / precision) * precision
        
        # Округляем до нужного количества знаков для избежания float ошибок
        return round(quantized, decimals)
    
    async def _check_exchange_health(self, exchange: str) -> bool:
        """Проверяет доступность биржи и сбрасывает счетчик ошибок при необходимости."""
        now_ms = self._now_ms()
        
        # Проверяем cooldown
        if exchange in self.exchange_cooldowns:
            if now_ms < self.exchange_cooldowns[exchange]:
                return False  # Биржа все еще в cooldown
            else:
                # Cooldown истек, сбрасываем счетчики
                del self.exchange_cooldowns[exchange]
                self.error_counts[exchange] = 0
                print(f"✅ {exchange} вышла из cooldown, возобновляем работу")
        
        # Проверяем количество ошибок
        if self.error_counts[exchange] >= self.max_errors_before_cooldown:
            # Ставим биржу в cooldown
            self.exchange_cooldowns[exchange] = now_ms + self.cooldown_duration_ms
            print(f"⚠️ {exchange} слишком много ошибок ({self.error_counts[exchange]}), cooldown на 1 минуту")
            return False
        
        return True
    
    async def _handle_api_error(self, exchange: str, error: Exception):
        """Обрабатывает ошибки API и увеличивает счетчики."""
        self.error_counts[exchange] += 1
        error_msg = str(error)
        
        # Определяем тип ошибки
        if 'rate limit' in error_msg.lower() or '429' in error_msg:
            print(f"⚠️ {exchange}: превышен rate limit, замедляем запросы")
            await asyncio.sleep(5)  # Ждем 5 секунд при rate limit
        elif 'timeout' in error_msg.lower():
            print(f"⚠️ {exchange}: timeout, повторим позже")
        elif '403' in error_msg or 'forbidden' in error_msg.lower():
            print(f"❌ {exchange}: доступ запрещен, проверьте API ключи")
            self.error_counts[exchange] = self.max_errors_before_cooldown  # Сразу в cooldown
        else:
            print(f"❌ {exchange}: ошибка API: {error_msg[:100]}")
    
    async def close(self):
        self.is_running = False
        """Закрытие сессии"""
        if self.session:
            await self.session.close()
            self.session = None
            try:
                if getattr(self, '_event_task', None):
                    self._event_task.cancel()
                    await self._event_task
            except Exception:
                pass
            # Мягко отменяем WS задачи, если есть
            for t in getattr(self, 'ws_tasks', []) or []:
                try:
                    t.cancel()
                except Exception:
                    pass
            
    # ==================== WS HELPERS ====================
    async def seed_ws_prices(self):
        """Первичный сбор цен через WS для инициализации."""
        # Для Bybit собираем начальные цены
        if WS_EXCHANGES.get('bybit', False):
            try:
                await self._fetch_bybit_prices()
            except Exception as e:
                await self._handle_api_error('bybit', e)
                
    async def start_ws(self):
        """Запуск WebSocket клиентов для поддерживаемых бирж."""
        tasks = []
        if WS_EXCHANGES.get('bybit', False):
            print("debug: Создание задачи для _ws_bybit")
            tasks.append(asyncio.create_task(self._ws_bybit()))
        if WS_EXCHANGES.get('kucoin', False):
            print("debug: Создание задачи для _ws_kucoin")
            tasks.append(asyncio.create_task(self._ws_kucoin()))
        if WS_EXCHANGES.get('binance', False):
            print("debug: Создание задачи для _ws_binance")
            tasks.append(asyncio.create_task(self._ws_binance()))
        if WS_EXCHANGES.get('mexc', False):
            print("debug: Создание задачи для _ws_mexc")
            tasks.append(asyncio.create_task(self._ws_mexc()))
        self.ws_tasks = tasks
            
    async def _ws_kucoin(self):
        """WebSocket клиент для KuCoin."""
        client = self.clients.get('kucoin')
        if not client:
            print("🔴 KuCoin клиент не инициализирован, WebSocket не запускается.")
            return
        
        try:
            # 1. Получаем публичный эндпоинт для WebSocket
            async with self.direct_session.post('https://api.kucoin.com/api/v1/bullet-public') as response:
                if response.status != 200:
                    print(f"⚠️ Не удалось получить эндпоинт для KuCoin WebSocket: {response.status}")
                    return
                resp_json = await response.json()
                token = resp_json['data']['token']
                ws_endpoint = resp_json['data']['instanceServers'][0]['endpoint']
                ws_url = f"{ws_endpoint}?token={token}"

            # 2. Подключаемся к WebSocket
            print("🔌 Подключение к KuCoin WebSocket (прямое соединение)...")
            async with self.direct_session.ws_connect(ws_url, heartbeat=20) as ws:
                # 3. Подписываемся на все тикеры
                subscribe_msg = {
                    "id": int(time.time() * 1000),
                    "type": "subscribe",
                    "topic": "/market/ticker:all",
                    "privateChannel": False,
                    "response": True
                }
                await ws.send_json(subscribe_msg)

                # 4. Обрабатываем входящие сообщения
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get('topic') == '/market/ticker:all' and data.get('subject'):
                            symbol = data['data']['symbol'].replace('-', '')
                            if symbol in self.symbols_to_trade:
                                best_bid = float(data['data']['bestBid'])
                                best_ask = float(data['data']['bestAsk'])
                                
                                self._update_price('kucoin', symbol, best_bid, best_ask)

                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        print("🚪 Соединение с KuCoin WebSocket закрыто.")
                        break
        except Exception as e:
            print(f"⚠️ Ошибка WebSocket KuCoin: {e}")

    async def _ws_binance(self):
        """WebSocket клиент для Binance."""
        print("⚙️  Запуск WebSocket для Binance...")
        client = self.clients.get('binance')
        if not client:
            print("🔴 Binance клиент не инициализирован.")
            return

        bm = BinanceSocketManager(client)
        # Binance требует подписки на каждый стрим индивидуально
        # Формат: <symbol>@ticker
        streams = [f"{pair.replace('/', '').lower()}@ticker" for pair in self.trading_pairs]
        
        try:
            async with bm.multiplex_socket(streams) as stream:
                print("✅ WebSocket для Binance успешно запущен.")
                self.ws_connected['binance'] = True
                while self.is_running:
                    msg = await stream.recv()
                    if msg and 'data' in msg:
                        data = msg['data']
                        if data.get('e') == 'error':
                            print(f"🔴 Ошибка Binance WS: {data['m']}")
                            break
                        
                        symbol = self._normalize_symbol(data['s'])
                        if symbol in self.trading_pairs:
                            self._update_price('binance', symbol, float(data['b']), float(data['a']))

        except Exception as e:
            print(f"🔴 КРИТИЧЕСКАЯ ОШИБКА в WebSocket Binance: {e}")
        finally:
            self.ws_connected['binance'] = False
            print("⚪️ WebSocket для Binance остановлен.")

    async def _ws_mexc(self):
        """WebSocket клиент для MEXC с декодированием Protobuf."""
        print("⚙️  Запуск WebSocket для MEXC...")
        client = self.clients.get('mexc')
        if not client:
            print("🔴 MEXC клиент не инициализирован, WebSocket не запускается.")
            return

        ws_url = "wss://wbs.mexc.com/ws"
        
        # Подписка на тикеры для всех пар
        # MEXC позволяет подписаться на несколько тикеров в одном сообщении
        subscribe_msg = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.bookTicker.v3.api@{pair.replace('/', '')}" for pair in self.trading_pairs]
        }

        try:
            async with self.direct_session.ws_connect(ws_url, heartbeat=20) as ws:
                await ws.send_json(subscribe_msg)
                print("✅ WebSocket для MEXC успешно запущен и подписан на тикеры.")
                self.ws_connected['mexc'] = True
                
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        # Декодируем сообщение из Protobuf
                        ticker_data = mexc_ticker_pb2.BookTicker()
                        try:
                            ticker_data.ParseFromString(msg.data)
                            symbol = self._normalize_symbol(ticker_data.s)
                            if symbol in self.trading_pairs:
                                self._update_price('mexc', symbol, ticker_data.b, ticker_data.a)
                        except Exception as e:
                            print(f"🔴 Ошибка декодирования Protobuf от MEXC: {e}")

                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        print(f"🔴 Соединение WebSocket MEXC закрыто/ошибка: {msg.data}")
                        break
        except Exception as e:
            print(f"🔴 КРИТИЧЕСКАЯ ОШИБКА в WebSocket MEXC: {e}")
        finally:
            self.ws_connected['mexc'] = False
            print("⚪️ WebSocket для MEXC остановлен.")

    async def _ws_bybit(self):
        """WebSocket клиент для Bybit."""
        url = 'wss://stream.bybit.com/v5/public/spot'
        symbols = [f"tickers.{pair.replace('/', '')}" for pair in self.trading_pairs]
        subscribe_msg = {
            "op": "subscribe",
            "args": symbols
        }

        while self.is_running:
            try:
                async with self.direct_session.ws_connect(url, heartbeat=20) as ws:
                    print("🔌 Подключено к Bybit WebSocket (прямое соединение).")
                    await ws.send_json(subscribe_msg)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if 'topic' in data and 'tickers' in data['topic']:
                                ticker_data = data['data']
                                symbol = self._normalize_symbol(ticker_data['symbol'])
                                if symbol in self.trading_pairs:
                                    self._update_price('bybit', symbol, float(ticker_data['bid1Price']), float(ticker_data['ask1Price']))
                            elif data.get('op') == 'subscribe':
                                if data.get('success'):
                                    print(f"✅ Успешная подписка на Bybit: {data.get('ret_msg')}")
                                else:
                                    print(f"❌ Ошибка подписки на Bybit: {data.get('ret_msg')}")
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            print("🔌 WebSocket соединение с Bybit закрыто. Переподключение...")
                            break
            except Exception as e:
                print(f"⚠️ Ошибка WebSocket Bybit: {e}")
                await asyncio.sleep(5)
                
    async def collect_non_ws_prices_loop(self):
        """Цикл сбора цен для бирж без WebSocket."""
        while self.is_running:
            try:
                non_ws_exchanges = [ex for ex, use_ws in WS_EXCHANGES.items() if not use_ws]
                tasks = [self.fetch_prices(exchange) for exchange in non_ws_exchanges]
                if tasks:
                    await asyncio.gather(*tasks)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"⚠️ Ошибка в collect_non_ws_prices_loop: {e}")
                await asyncio.sleep(5)

    async def fetch_prices(self, exchange: str):
        """Получает текущие цены для всех символов с биржи."""
        try:
            client = self.clients.get(exchange)
            if not client:
                return
            
            # Получаем тикеры для всех символов
            tickers = await client.fetch_tickers()
            
            for symbol in INTER_EXCHANGE_SYMBOLS:
                if symbol in tickers:
                    ticker = tickers[symbol]
                    bid = ticker.get('bid', 0)
                    ask = ticker.get('ask', 0)
                    
                    if bid and ask and bid > 0 and ask > 0:
                        self._update_price(symbol, exchange, bid, ask)
                        
        except Exception as e:
            if 'rate limit' in str(e).lower():
                print(f"⚠️ Rate limit на {exchange}, ждем...")
                await asyncio.sleep(10)
            else:
                print(f"⚠️ Ошибка получения цен с {exchange}: {e}")
    
    async def collect_all_prices_loop(self):
        """Цикл сбора цен для всех бирж через REST API."""
        while self.is_running:
            try:
                tasks = [self.fetch_prices(exchange) for exchange in EXCHANGES.keys()]
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            exchange = list(EXCHANGES.keys())[i]
                            print(f"⚠️ Ошибка сбора с {exchange}: {result}")
                
                # Обновляем статус сборщика данных
                self.scanner_status['collector']['active'] = True
                
                await asyncio.sleep(2)  # Пауза между циклами сбора
            except Exception as e:
                print(f"⚠️ Ошибка в collect_all_prices_loop: {e}")
                await asyncio.sleep(5)
                
    def _now_ms(self) -> int:
        """Получение текущего времени в миллисекундах."""
        return int(time.time() * 1000)
    def _ensure_symbol_entry(self, symbol: str, exchange: str):
        if symbol not in self.prices:
            self.prices[symbol] = {}
        if exchange not in self.prices[symbol]:
            self.prices[symbol][exchange] = {'bid': 0.0, 'ask': 0.0, 'exchange': exchange, 'ts': 0.0}
            
        if symbol not in self.orderbooks:
            self.orderbooks[symbol] = {}
 
    def _update_price(self, symbol: str, exchange: str, bid: float, ask: float):
        if bid and ask and bid > 0 and ask > 0:
            self._ensure_symbol_entry(symbol, exchange)
            now_ts = time.time()
            self.prices[symbol][exchange].update({
                'bid': bid,
                'ask': ask,
                'ts': now_ts
            })
            # Обновляем статус сканера
            self.scanner_status['prices_updated'] += 1
            self.scanner_status['last_price_update_ts'] = int(now_ts * 1000)
            # Событийный анализ конкретного символа
            if EVENT_INTER_ENABLED and self.mode in ('inter', 'both'):
                try:
                    # Дебаунсинг, чтобы не спамить событиями
                    last_event_time = self._debounce.get(symbol, 0)
                    if now_ts * 1000 - last_event_time > EVENT_DEBOUNCE_MS:
                        self._debounce[symbol] = now_ts * 1000
                        self._event_symbols.add(symbol)
                        if hasattr(self, '_event_trigger'):
                            self._event_trigger.set()
                except Exception as e:
                    print(f"Ошибка в логике событийного анализа для {symbol}: {e}")

    async def _place_order(self, ex_name: str, symbol: str, side: str, amount: float, price: float, order_type: str = 'limit') -> Dict:
        """Размещает ордер на бирже и возвращает результат."""
        exchange_obj = getattr(self, ex_name)
        try:
            print(f"  -> Размещаю {side.upper()} ордер на {ex_name}: {amount:.6f} {symbol} @ {price:.6f}")
            if side == 'buy':
                order = await exchange_obj.create_limit_buy_order(symbol, amount, price, {'timeInForce': 'IOC'})
            else:
                order = await exchange_obj.create_limit_sell_order(symbol, amount, price, {'timeInForce': 'IOC'})
            print(f"  <- Ордер {order['id']} на {ex_name} успешно размещен.")
            # Обновляем метрики трейдера
            if side == 'buy':
                self.trader_status['executor']['orders_placed'] += 1
            else:
                self.trader_status['executor']['orders_filled'] += 1
            return order
        except Exception as e:
            print(f"  <- ❌ Ошибка при размещении ордера на {ex_name}: {e}")
            self.trader_status['executor']['orders_failed'] += 1
            raise e

    async def validate_opportunity(self, opp: Dict) -> bool:
        """Валидирует арбитражную возможность перед исполнением."""
        try:
            self.trader_status['validator']['active'] = True
            symbol = opp['symbol']
            buy_ex = opp['buy_exchange']
            sell_ex = opp['sell_exchange']
            position_size_usd = DEFAULT_POSITION_SIZE_USD
            
            # 0. Проверка через риск-менеджер (если доступен)
            if self.risk_manager:
                approved, reason = self.risk_manager.validate_opportunity(opp)
                if not approved:
                    print(f"🛡️ Риск-менеджер отклонил сделку: {reason}")
                    self.trader_status['risk_manager']['positions_rejected'] += 1
                    self.trader_status['validator']['checks_failed'] += 1
                    return False
                self.trader_status['risk_manager']['positions_approved'] += 1
            
            # 1. Проверка минимального профита
            if opp['profit_pct'] < MIN_PROFIT_THRESHOLD:
                print(f"⚠️ Возможность {symbol} не прошла по профиту: {opp['profit_pct']:.2f}% < {MIN_PROFIT_THRESHOLD}%")
                self.trader_status['validator']['checks_failed'] += 1
                return False
            
            # 2. Проверка балансов
            buy_balance = self.balances.get(buy_ex, {})
            sell_balance = self.balances.get(sell_ex, {})
            
            if not buy_balance or not sell_balance:
                print(f"⚠️ Не удалось получить балансы для {buy_ex} или {sell_ex}")
                self.trader_status['validator']['checks_failed'] += 1
                return False
            
            # 3. Проверка достаточности баланса покупки
            quote_currency = self.symbol_meta.get(buy_ex, {}).get(symbol, {}).get('quote', 'USDT')
            if buy_balance.get(quote_currency, {}).get('free', 0) < DEFAULT_POSITION_SIZE_USD:
                print(f"⚠️ Недостаточно {quote_currency} на {buy_ex} для сделки. Требуется: ${DEFAULT_POSITION_SIZE_USD}")
                self.trader_status['validator']['checks_failed'] += 1
                return False
            
            # 4. Проверка достаточности баланса продажи
            base_currency = self.symbol_meta.get(sell_ex, {}).get(symbol, {}).get('base', 'BTC')
            qty_needed_for_sale = DEFAULT_POSITION_SIZE_USD / self.prices.get(symbol, {}).get(sell_ex, {}).get('ask', 1e9)
            if sell_balance.get(base_currency, {}).get('free', 0) < qty_needed_for_sale:
                print(f"⚠️ Недостаточно {base_currency} на {sell_ex}. Нужно: ~{qty_needed_for_sale:.6f}, доступно: {sell_balance[base_currency]['free']:.6f}")
                self.trader_status['validator']['checks_failed'] += 1
                return False
            
            # Все проверки пройдены
            self.trader_status['validator']['checks_passed'] += 1
            return True
        except Exception as e:
            print(f"❌ Ошибка валидации: {e}")
            self.trader_status['validator']['checks_failed'] += 1
            return False
        
    async def scan_inter_exchange_opportunities(self):
        """Сканирует межбиржевые арбитражные возможности."""
        opportunities = []
        now_ts = time.time()
        
        # Обновляем статус сканера
        self.scanner_status['scans_performed'] += 1
        self.scanner_status['last_scan_ts'] = int(now_ts * 1000)
        
        for symbol in INTER_EXCHANGE_SYMBOLS:
            if symbol not in self.prices or len(self.prices[symbol]) < 2:
                continue
            
            prices_for_symbol = self.prices[symbol]
            
            # Ищем лучшие цены покупки и продажи среди всех бирж
            best_bid = 0
            best_bid_exchange = None
            best_ask = float('inf')
            best_ask_exchange = None
            
            for exchange, price_data in prices_for_symbol.items():
                # Проверяем свежесть данных (не старше 5 секунд)
                if now_ts - price_data.get('ts', 0) > 5:
                    continue
                    
                bid = price_data.get('bid', 0)
                ask = price_data.get('ask', 0)
                
                if bid > best_bid and bid > 0:
                    best_bid = bid
                    best_bid_exchange = exchange
                    
                if ask < best_ask and ask > 0:
                    best_ask = ask
                    best_ask_exchange = exchange
            
            # Проверяем есть ли арбитражная возможность
            if best_bid_exchange and best_ask_exchange and best_bid_exchange != best_ask_exchange:
                if best_bid > best_ask:  # Арбитраж возможен только если bid > ask
                    spread = best_bid - best_ask
                    spread_pct = (spread / best_ask) * 100
                    
                    # Учитываем реальные комиссии бирж
                    buy_fee = EXCHANGES.get(best_ask_exchange, {}).get('taker_fee', 0.1)
                    sell_fee = EXCHANGES.get(best_bid_exchange, {}).get('taker_fee', 0.1)
                    total_fees = buy_fee + sell_fee
                    net_profit_pct = spread_pct - total_fees
                    
                    if net_profit_pct > MIN_PROFIT_THRESHOLD:
                        opportunity = {
                            'symbol': symbol,
                            'buy_exchange': best_ask_exchange,
                            'sell_exchange': best_bid_exchange,
                            'buy_price': best_ask,
                            'sell_price': best_bid,
                            'spread': spread,
                            'spread_pct': spread_pct,
                            'profit_pct': net_profit_pct,
                            'timestamp': now_ts,
                            'type': 'inter_exchange',
                            'buy_fee': buy_fee,
                            'sell_fee': sell_fee
                        }
                        opportunities.append(opportunity)
                        
                        # Обновляем статус сканера
                        self.scanner_status['opportunities_found'] += 1
                        
                        # Логируем найденную возможность
                        print(f"⚡ Арбитраж: {symbol} {best_ask_exchange}→{best_bid_exchange} "
                              f"спред: {spread_pct:.2f}%, чистая: {net_profit_pct:.2f}%")
        
        return opportunities
    
    async def execute_paper_trade(self, opp: Dict):
        """Исполняет сделку в paper режиме."""
        try:
            symbol = opp['symbol']
            buy_ex = opp['buy_exchange']
            sell_ex = opp['sell_exchange']
            buy_price = opp['buy_price']
            sell_price = opp['sell_price']
            
            # Расчет размера позиции
            position_size_usd = DEFAULT_POSITION_SIZE_USD
            quantity = position_size_usd / buy_price
            
            # Расчет прибыли с учетом комиссий
            buy_cost = position_size_usd * (1 + opp['buy_fee'] / 100)
            sell_revenue = (quantity * sell_price) * (1 - opp['sell_fee'] / 100)
            net_profit = sell_revenue - buy_cost
            net_profit_pct = (net_profit / buy_cost) * 100
            
            # Создаем запись о сделке
            trade_record = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'type': 'inter_exchange',
                'buy_exchange': buy_ex,
                'sell_exchange': sell_ex,
                'buy_price': buy_price,
                'sell_price': sell_price,
                'quantity': quantity,
                'position_size_usd': position_size_usd,
                'buy_fee_pct': opp['buy_fee'],
                'sell_fee_pct': opp['sell_fee'],
                'gross_profit_pct': opp['spread_pct'],
                'net_profit_pct': net_profit_pct,
                'net_profit_usd': net_profit,
                'paper_balance': self.paper_balance + net_profit
            }
            
            # Обновляем балансы и статистику
            self.paper_balance += net_profit
            self.paper_total_pnl += net_profit
            self.session_profit_usd += net_profit
            self.session_trades += 1
            self.paper_trades.append(trade_record)
            
            if self.paper_start_balance > 0:
                self.session_profit_pct = (self.session_profit_usd / self.paper_start_balance) * 100
            
            # Обновляем метрики успешного исполнения
            self.trader_status['executor']['orders_placed'] += 2  # buy + sell
            self.trader_status['executor']['orders_filled'] += 2
            self.trader_status['tracker']['trades_monitored'] += 1
            self.trader_status['tracker']['trades_completed'] += 1
            self.trader_status['tracker']['active'] = True
            
            print(f"✅ Paper сделка #{len(self.paper_trades)}: {symbol} "
                  f"{buy_ex}→{sell_ex} прибыль: ${net_profit:.2f} ({net_profit_pct:.2f}%)")
            
            # Сохраняем сделку в CSV
            try:
                file_path = self.csv_filename
                is_new_file = not os.path.exists(file_path)
                df = pd.DataFrame([trade_record])
                df.to_csv(file_path, mode='a', header=is_new_file, index=False)
            except Exception as e:
                print(f"⚠️ Ошибка записи в лог сделок: {e}")
                
        except Exception as e:
            print(f"❌ Ошибка исполнения paper сделки: {e}")
            self.trader_status['executor']['orders_failed'] += 1

    async def close_sessions(self):
        """Закрывает все открытые сессии и соединения."""
        self.is_running = False
        try:
            # Закрываем WebSocket соединения
            for task in getattr(self, 'ws_tasks', []):
                if task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Закрываем HTTP сессии
            if hasattr(self, 'session') and self.session:
                await self.session.close()
            
            if hasattr(self, 'direct_session') and self.direct_session:
                await self.direct_session.close()
            
            # Закрываем CCXT клиенты
            for exchange_name, client in self.clients.items():
                if hasattr(client, 'close'):
                    await client.close()
            
            print("✅ Все сессии закрыты")
        except Exception as e:
            print(f"⚠️ Ошибка при закрытии сессий: {e}")
    
    async def close(self):
        """Грациозная остановка: отмена задач, финальное сохранение статистики, закрытие HTTP-сессии."""
        self.is_running = False
        try:
            print("🛑 Остановка бота... Отменяю фоновые задачи и сохраняю статистику")
            # Отмена фоновых задач
            tasks = []
            try:
                for t in getattr(self, 'ws_tasks', []) or []:
                    if t and not t.done():
                        t.cancel()
                        tasks.append(t)
            except Exception:
                pass
            for name in ('_event_task', '_rest_price_task', '_save_csv_task'):
                t = getattr(self, name, None)
                if t and not t.done():
                    try:
                        t.cancel()
                        tasks.append(t)
                    except Exception:
                        pass
            # Дожидаемся отмены
            for t in tasks:
                try:
                    await t
                except Exception:
                    pass
            # Финальное сохранение статистики (сессионная прибыль включена)
            try:
                self.save_to_csv()
            except Exception as e:
                print(f"⚠️ Ошибка финального сохранения статистики: {e}")
            # Закрываем HTTP-сессию
            try:
                if getattr(self, 'session', None):
                    await self.session.close()
            except Exception as e:
                print(f"⚠️ Ошибка закрытия HTTP-сессии: {e}")
            
            print("✅ Бот остановлен. Финальная статистика сохранена.")
        except Exception as e:
            print(f"⚠️ Ошибка при остановке бота: {e}")
    
    def _print_trade_visualization(self, trade_data: Dict):
        """Красивая визуализация сделки в терминале."""
        symbol = trade_data['symbol']
        buy_ex = trade_data['buy_exchange']
        sell_ex = trade_data['sell_exchange']
        net_profit = trade_data.get('net_profit', trade_data.get('net_pct', 0))
        net_usd = trade_data.get('net_usd', 0)
        size_usd = trade_data['size_usd']
        
        # Определяем цвет для прибыли/убытка
        if net_usd > 0:
            profit_icon = "✅"
            color_start = "\033[92m"  # Зелёный
        else:
            profit_icon = "❌"
            color_start = "\033[91m"  # Красный
        color_end = "\033[0m"
        
        # Рисуем рамку
        print("\n" + "═" * 60)
        print(f"  📈 АРБИТРАЖНАЯ СДЕЛКА #{self.session_trades}")
        print("─" * 60)
        
        # Маршрут
        print(f"  📍 Маршрут: {buy_ex} → {sell_ex}")
        print(f"  💎 Символ: {symbol}")
        
        # Цены
        buy_price = trade_data.get('buy_price_eff', 0)
        sell_price = trade_data.get('sell_price_eff', 0)
        spread = (sell_price - buy_price) / buy_price * 100 if buy_price > 0 else 0
        print(f"  💸 Покупка: ${buy_price:.4f} | Продажа: ${sell_price:.4f}")
        print(f"  📊 Спред: {spread:.3f}%")
        
        # Объёмы
        qty = trade_data.get('qty_base', 0)
        print(f"  📦 Объём: {qty:.8f} | Размер: ${size_usd:.2f}")
        
        # Прибыль
        print("─" * 60)
        session_color = "\033[92m" if self.session_profit_usd > 0 else "\033[91m"
        print(f"  {profit_icon} Результат: {color_start}${net_usd:.2f} ({net_profit:.3f}%){color_end}")
        
        # Сессионная статистика
        print("─" * 60)
        print(f"  💼 Сессия: {session_color}${self.session_profit_usd:.2f} ({self.session_profit_pct:.3f}%){color_end}")
        print(f"  📈 Всего сделок: {self.session_trades}")
        avg_profit = self.session_profit_usd / max(1, self.session_trades)
        print(f"  💰 Средняя прибыль: ${avg_profit:.2f}")
        print("═" * 60)
    
    def print_system_status(self):
        """Выводит в консоль полный статус системы: Сканер и Трейдер."""
        now = int(time.time() * 1000)
        prices_updated = self.scanner_status['prices_updated']
        scans_performed = self.scanner_status['scans_performed']
        opps_found = self.scanner_status['opportunities_found']

        last_price_update_ago = (now - self.scanner_status['last_price_update_ts']) / 1000 if self.scanner_status['last_price_update_ts'] else -1
        last_scan_ago = (now - self.scanner_status['last_scan_ts']) / 1000 if self.scanner_status['last_scan_ts'] else -1

        # Состояние WS соединений
        ws_status_str = ' '.join([
            f"✅ {ex.upper()}" if self.ws_connected.get(ex) else f"🔌 {ex.upper()}"
            for ex in self.ws_exchanges
        ])

        # Очистка экрана
        print("\033[H\033[J", end="")
        
        # Заголовок системы
        print("╔═══════════════════════════════════════════════════════════════════════╗")
        print("║           MEGA ARBITRAGE BOT - СИСТЕМА МОНИТОРИНГА v2.0              ║")
        print("╠═══════════════════════════════════════════════════════════════════════╣")
        print(f"║ Режим: {self.mode.upper():^10} │ Время работы: {int((time.time() - self.statistics['start_time'].timestamp()) / 60):>3} мин │ PnL: ${self.paper_total_pnl:+.2f}  ║")
        print("╚═══════════════════════════════════════════════════════════════════════╝")
        print()
        
        # МОДУЛЬ 1: СКАНЕР
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│                        📡 МОДУЛЬ СКАНЕР                              │")
        print("├─────────────────┬───────────────────────────┬───────────────────────┤")
        print("│ Компонент       │ Статус                    │ Метрики               │")
        print("├─────────────────┼───────────────────────────┼───────────────────────┤")
        
        # Сборщик данных
        collector_status = "✅ Работает" if last_price_update_ago != -1 and last_price_update_ago < 10 else "🔴 Проблема"
        collector_metrics = f"{prices_updated:>5} цен │ {last_price_update_ago:>4.1f}с"
        print(f"│ Сборщик данных  │ {collector_status:<25} │ {collector_metrics:<21} │")
        
        # Хранилище цен
        store_status = "✅ Активно" if len(self.prices) > 0 else "⚠️ Пусто"
        store_metrics = f"{len(self.prices):>5} пар │ {sum(len(v) for v in self.prices.values()):>5} тикеров"
        print(f"│ Хранилище цен   │ {store_status:<25} │ {store_metrics:<21} │")
        
        # Анализатор
        analyzer_status = "✅ Работает" if last_scan_ago != -1 and last_scan_ago < 10 else "💤 Ожидание"
        analyzer_metrics = f"{scans_performed:>5} скан │ {opps_found:>5} возм."
        print(f"│ Анализатор      │ {analyzer_status:<25} │ {analyzer_metrics:<21} │")

        print("└─────────────────┴───────────────────────────┴───────────────────────┘")
        print()
        
        # МОДУЛЬ 2: ТРЕЙДЕР
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│                        💰 МОДУЛЬ ТРЕЙДЕР                             │")
        print("├─────────────────┬───────────────────────────┬───────────────────────┤")
        print("│ Компонент       │ Статус                    │ Метрики               │")
        print("├─────────────────┼───────────────────────────┼───────────────────────┤")
        
        # Валидатор
        val = self.trader_status['validator']
        val_status = "✅ Активен" if val['active'] else "💤 Ожидание"
        val_metrics = f"✓{val['checks_passed']:>4} │ ✗{val['checks_failed']:>4}"
        print(f"│ Валидатор       │ {val_status:<25} │ {val_metrics:<21} │")
        
        # Риск-менеджер
        risk = self.trader_status['risk_manager']
        risk_status = "✅ Активен" if risk['active'] else "💤 Ожидание"
        risk_metrics = f"✓{risk['positions_approved']:>4} │ ✗{risk['positions_rejected']:>4}"
        print(f"│ Риск-менеджер   │ {risk_status:<25} │ {risk_metrics:<21} │")
        
        # Исполнитель
        exec = self.trader_status['executor']
        exec_status = "✅ Активен" if exec['active'] else "💤 Ожидание"
        exec_metrics = f"📤{exec['orders_placed']:>3} │ ✅{exec['orders_filled']:>3}"
        print(f"│ Исполнитель     │ {exec_status:<25} │ {exec_metrics:<21} │")
        
        # Трекер
        track = self.trader_status['tracker']
        track_status = "✅ Активен" if track['active'] else "💤 Ожидание"
        track_metrics = f"👁{track['trades_monitored']:>3} │ ✓{track['trades_completed']:>3}"
        print(f"│ Трекер сделок   │ {track_status:<25} │ {track_metrics:<21} │")
        
        print("└─────────────────┴───────────────────────────┴───────────────────────┘")
        print()
        
        # Статус подключений
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│                      🔌 СТАТУС ПОДКЛЮЧЕНИЙ                           │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        ws_line = "│ WebSocket: "
        for ex in self.ws_exchanges:
            if self.ws_connected.get(ex):
                ws_line += f"✅ {ex.upper()} "
            else:
                ws_line += f"🔴 {ex.upper()} "
        ws_line = ws_line.ljust(71) + "│"
        print(ws_line)
        print("└─────────────────────────────────────────────────────────────────────┘")
        
        sys.stdout.flush()

    def print_key_parameters(self):
        """Выводит красивые ключевые параметры конфигурации в терминал."""
        params = {
            "Режим работы": "WebSocket" if USE_WS else "REST API",
            "Прокси используется": "Да" if PROXY_URL else "Нет",
            "uvloop ускорение": "Включено" if UVLOOP_ENABLED else "Отключено",
            "Порог устаревания данных (STALE_MS)": f"{STALE_MS} мс",
            "Интервал сканирования": f"{SCAN_INTERVAL_SECONDS} с",
            "Минимальная прибыль (межбирж.)": f"{INTER_MIN_PROFIT_PCT}%",
            "WebSocket биржи": ", ".join([ex for ex, enabled in WS_EXCHANGES.items() if enabled])
        }

        print("\n┌───────────────────────────────┐")
        print("│   ⚙️  Ключевые параметры сканера   │")
        print("├───────────────────────────────┤")
        for key, value in params.items():
            print(f"│ {key:<30} │ {value:<35} │")
        print("└───────────────────────────────┘\n")

    def print_startup_banner(self):
        """Выводит красивый баннер при запуске."""
        print("\n" + "="*70)
        print("""    
    ╔╦╗╔═╗╔═╗╔═╗  ╔═╗╦═╗╔╗ ╦╔╦╗╦═╗╔═╗╔═╗╔═╗  ╔╗ ╔═╗╔╦╗
    ║║║║╣ ║ ╦╠═╣  ╠═╣╠╦╝╠╩╗║ ║ ╠╦╝╠═╣║ ╦║╣   ╠╩╗║ ║ ║ 
    ╩ ╩╚═╝╚═╝╩ ╩  ╩ ╩╩╚═╚═╝╩ ╩ ╩╚═╩ ╩╚═╝╚═╝  ╚═╝╚═╝ ╩ 
        """)
        print("="*70)
        print(f"  🚀 Версия: 2.0 | Режим: {'DEMO' if PAPER_TRADING else 'REAL'}")
        position_size = self.paper_balance * (POSITION_SIZE_PCT / 100.0)
        print(f"  💰 Капитал: ${self.paper_balance:,.2f}")
        print(f"  📊 Позиция: ${position_size:,.2f} ({POSITION_SIZE_PCT}% от капитала)")
        print(f"  🎯 Мин. прибыль: {INTER_MIN_PROFIT_PCT:.2f}%")
        # Подсчитываем общее количество символов на всех биржах
        total_symbols = sum(len(symbols) for symbols in self.symbols.values())
        print("="*70)
        
        # Статус API ключей
        print("\n📋 Статус подключений:")
        for exchange, is_valid in self.api_keys_valid.items():
            if is_valid:
                print(f"  ✅ {exchange.upper()}: Готов к торговле")
            else:
                print(f"  ⚠️  {exchange.upper()}: Только чтение (нет API ключей)")
        
        print("\n" + "="*70)
        print("  Бот запущен! Ожидание арбитражных возможностей...")
        print("="*70 + "\n")
    
    async def _reconcile_on_startup(self):
        """Сверка состояния при старте: отмена висячих ордеров, проверка балансов."""
        print("\n🔄 Выполняется reconciliation...")
        
        if PAPER_TRADING:
            print("  📝 Демо режим - пропускаем reconciliation")
            return
        
        for exchange in EXCHANGES.keys():
            if not self.api_keys_valid.get(exchange):
                continue
            
            try:
                # 1. Получаем и отменяем открытые ордера
                print(f"  🔍 Проверка {exchange}...")
                # TODO: Реализовать получение открытых ордеров
                # open_orders = await self._get_open_orders(exchange)
                # for order in open_orders:
                #     await self._cancel_order(exchange, order['id'])
                #     print(f"    ❌ Отменён ордер {order['id']}")
                
                # 2. Получаем актуальные балансы
                await self._fetch_balance(exchange)
                balances = self.real_balances.get(exchange, {})
                usdt_balance = balances.get('USDT', 0)
                if usdt_balance > 0:
                    print(f"    💰 USDT: ${usdt_balance:.2f}")
                
            except Exception as e:
                print(f"    ⚠️ Ошибка: {e}")
        
        print("  ✅ Reconciliation завершён\n")

    async def _scanner_status_loop(self):
        """Фоновая задача для периодического обновления статуса в терминале."""
        await asyncio.sleep(2)  # Даем системе время на инициализацию
        while self.is_running:
            try:
                self.print_system_status()
                await asyncio.sleep(1) # Обновление раз в секунду
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ошибка в цикле статуса: {e}")
    
    async def _scanner_loop(self):
        """Основной цикл сканирования арбитражных возможностей."""
        await asyncio.sleep(3)  # Даем время на инициализацию
        while self.is_running:
            try:
                # Сканируем межбиржевые возможности
                opportunities = await self.scan_inter_exchange_opportunities()
                
                # Обрабатываем найденные возможности
                for opp in opportunities:
                    # Валидация
                    if await self.validate_opportunity(opp):
                        # Исполнение в paper режиме
                        if self.mode == 'paper':
                            await self.execute_paper_trade(opp)
                
                await asyncio.sleep(SCAN_INTERVAL_SECONDS)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Ошибка в цикле сканирования: {e}")
                await asyncio.sleep(5)
    
    async def run_bot(self):
        """Главная точка входа для запуска бота."""
        print("🚀 Запуск Mega Arbitrage Bot...")
        
        # Инициализация HTTP сессии
        connector = None
        if PROXY_URL:
            import aiohttp_socks
            connector = aiohttp_socks.ProxyConnector.from_url(PROXY_URL)
            print(f"🔌 Используется прокси: {PROXY_URL}")
        self.session = aiohttp.ClientSession(connector=connector)
        
        try:
            # Запускаем фоновые задачи
            tasks = []
            
            # 1. Задача отображения статуса
            status_task = asyncio.create_task(self._scanner_status_loop())
            tasks.append(status_task)
            print("✅ Панель мониторинга запущена")
            
            # 2. Задача сканирования
            scanner_task = asyncio.create_task(self._scanner_loop())
            tasks.append(scanner_task)
            print("✅ Сканер арбитража запущен")
            
            # 3. Задача сбора цен
            if USE_WS:
                # WebSocket режим
                try:
                    # Запускаем WebSocket для Bybit
                    if WS_EXCHANGES.get('bybit'):
                        ws_task = asyncio.create_task(self._ws_bybit())
                        tasks.append(ws_task)
                        print("✅ WebSocket Bybit запущен")
                    
                    # REST для остальных бирж
                    rest_task = asyncio.create_task(self.collect_non_ws_prices_loop())
                    tasks.append(rest_task)
                    print("✅ REST сборщик цен запущен")
                except Exception as e:
                    print(f"⚠️ Ошибка запуска WebSocket: {e}")
                    # Fallback на полный REST
                    rest_task = asyncio.create_task(self.collect_all_prices_loop())
                    tasks.append(rest_task)
            else:
                # Полный REST режим
                rest_task = asyncio.create_task(self.collect_all_prices_loop())
                tasks.append(rest_task)
                print("✅ REST сборщик цен запущен")
            
            print("\n" + "="*70)
            print("✅ Все системы запущены! Для остановки нажмите Ctrl+C")
            print("="*70 + "\n")
            
            # Ждем завершения всех задач
            await asyncio.gather(*tasks)
            
        except asyncio.CancelledError:
            print("\n⚠️ Получен сигнал остановки...")
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Останавливаем все задачи
            self.is_running = False
            await self.close_sessions()


# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

async def main(mode: str):
    parser = argparse.ArgumentParser(description='Mega Arbitrage Bot')
    parser.add_argument('--mode', type=str, choices=['inter', 'tri', 'both'], default='both', help='Trading mode')
    args = parser.parse_args()

    bot = MegaArbitrageBot(mode=args.mode)
    try:
        await bot.run_bot()
    except KeyboardInterrupt:
        print("\nПолучен сигнал отмены, начинаю штатную остановку...")
    finally:
        print("🛑 Остановка бота... Отменяю фоновые задачи.")
        if 'bot' in locals():
            await bot.close_sessions()
        print("✅ Бот полностью остановлен.")

if __name__ == "__main__":
    asyncio.run(main('both'))
