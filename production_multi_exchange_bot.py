#!/usr/bin/env python3
"""
🚀 PRODUCTION MULTI-EXCHANGE ARBITRAGE BOT
Профессиональный арбитражный бот для 7 бирж
Версия: 1.0.0
"""

import asyncio
import logging
import signal
import sys
import time
import json
import os
import time
from pathlib import Path
from datetime import datetime
from order_book_analyzer import OrderBookAnalyzer, LiquidityAnalysis
from triangular_arbitrage import TriangularArbitrageScanner, TriangularExecutor, TriangularOpportunity
from typing import Dict, List, Optional, Set
from collections import defaultdict
import aiohttp
from colorama import init as colorama_init, Fore, Style
from tabulate import tabulate

from production_config import (
    EXCHANGES_CONFIG, API_KEYS, TRADING_CONFIG, 
    WEBSOCKET_CONFIG, DYNAMIC_PAIRS_CONFIG,
    RISK_MANAGEMENT, LOGGING_CONFIG
)
from websocket_manager import WebSocketManager, OrderBook
from trading_engine import TradingEngine, ArbitrageOpportunity
from exchange_connector import ExchangeConnector
from symbol_utils import normalize_symbol, is_normalized

# Настройка логирования
logging.basicConfig(
    level=LOGGING_CONFIG['level'],
    format=LOGGING_CONFIG['format'],
    handlers=[
        logging.FileHandler(LOGGING_CONFIG['file']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('ProductionBot')
colorama_init(autoreset=True)

class ProductionArbitrageBot:
    """Главный класс производственного арбитражного бота"""
    
    def __init__(self):
        self.ws_manager = None
        self.trading_engine = TradingEngine()
        self.exchange_connector = ExchangeConnector(mode=TRADING_CONFIG['mode'])
        self.orderbooks = defaultdict(dict)  # {symbol: {exchange: OrderBook}}
        self.active_pairs = set()
        self.running = False
        self.last_pair_update = 0
        self.opportunity_cooldowns = {}  # {opportunity_key: timestamp} для предотвращения спама
        self.scan_counter = 0  # Счетчик сканирований
        # Очереди и данные
        self.opportunity_queue = asyncio.Queue()
        self.balances = {}
        
        # Получаем список включенных бирж
        self.enabled_exchanges = [exchange_id for exchange_id, config in EXCHANGES_CONFIG.items() 
                                 if config.get('enabled', False)]
        
        # Новые модули
        self.orderbook_analyzer = OrderBookAnalyzer()
        # Переопределяем пороги ликвидности из TRADING_CONFIG (поддержка paper-настроек)
        try:
            self.orderbook_analyzer.min_liquidity_usd = TRADING_CONFIG.get('min_liquidity_usd', TRADING_CONFIG.get('position_size_usd', 100))
            self.orderbook_analyzer.max_price_impact = TRADING_CONFIG.get('max_price_impact_pct', 2.0)
            self.orderbook_analyzer.min_depth_levels = TRADING_CONFIG.get('min_depth_levels', 1)
        except Exception:
            pass
        self.triangular_scanner = TriangularArbitrageScanner()
        self.triangular_executor = TriangularExecutor(self.trading_engine) 
        
        self.statistics = {
            'start_time': time.time(),
            'scans': 0,
            'opportunities_found': 0,
            'trades_executed': 0,
            'ws_messages': 0,
            'errors': 0,
            'candidates_detected': 0
        }
        # Детализированная статистика
        # По бирже: считаем возможности, сделки, успехи/провалы, сумму прибыли и объема, сумму процентов прибыли
        self.stats_by_exchange = defaultdict(lambda: {
            'opportunities': 0,
            'trades': 0,
            'successful': 0,
            'failed': 0,
            'profit_usd': 0.0,
            'profit_pct_sum': 0.0,
            'volume_usd': 0.0
        })
        # По связке (symbol + buy->sell)
        self.stats_by_pair = defaultdict(lambda: {
            'opportunities': 0,
            'trades': 0,
            'successful': 0,
            'failed': 0,
            'profit_usd': 0.0,
            'profit_pct_sum': 0.0,
            'volume_usd': 0.0
        })
        
    async def start(self):
        """Запуск бота"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК PRODUCTION ARBITRAGE BOT v1.0.0")
        logger.info(f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"💼 Режим: {TRADING_CONFIG['mode'].upper()}")
        logger.info(f"💰 Мин. прибыль: {TRADING_CONFIG['min_profit_threshold']}%")
        logger.info("=" * 60)
        logger.info(
            f"📡 Источник данных: {'WebSocket' if TRADING_CONFIG.get('use_websocket', True) else 'REST polling only'}"
        )
        
        self.running = True
        
        try:
            # Сначала запускаем торговый движок, чтобы CCXT рынки были загружены
            await self.trading_engine.start()
            
            # Инициализация ExchangeConnector для REST данных (особенно Bitget)
            await self.exchange_connector.initialize()

            # Инициализация после запуска движка (discover_pairs применит CCXT-фильтр)
            await self._initialize()
            # Красивый стартовый баннер
            try:
                self._print_start_banner()
            except Exception:
                pass
            
            # Запуск основных компонентов
            tasks = [
                self._run_websocket_manager(),
                self._run_rest_polling(),  # REST polling для Bitget и других бирж без WS
                self._scan_opportunities(),
                self._run_executor(),
                self._run_pair_updater(),
                self._run_statistics()
            ]
            
            # Запуск всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except KeyboardInterrupt:
            logger.info("\n⚠️ Получен сигнал остановки")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка бота"""
        logger.info("\n🛑 Остановка бота...")
        self.running = False
        
        # Остановка компонентов
        if self.ws_manager:
            await self.ws_manager.stop()
        
        await self.trading_engine.stop()
        await self.exchange_connector.close()
        
        # Финальная статистика
        self._print_final_statistics()
        
        logger.info("✅ Бот остановлен")
    
    async def _run_rest_polling(self):
        """REST polling для бирж без WebSocket (особенно Bitget)"""
        logger.info("📡 Запуск REST polling для Bitget и других бирж...")
        
        while self.running:
            try:
                # Получаем данные orderbook для активных пар через REST
                for symbol in list(self.active_pairs):
                    for exchange_id in ['bitget', 'phemex']:  # ✅ Включаем и Phemex
                        if exchange_id not in self.enabled_exchanges:
                            continue
                        
                        try:
                            # Получаем orderbook через ExchangeConnector
                            orderbook_data = await self.exchange_connector.fetch_orderbook(exchange_id, symbol)
                            
                            if orderbook_data and orderbook_data.get('bids') and orderbook_data.get('asks'):
                                # Создаем объект OrderBook
                                orderbook = OrderBook(
                                    symbol=symbol,
                                    exchange=exchange_id,
                                    bids=orderbook_data['bids'][:10],  # Топ 10 уровней
                                    asks=orderbook_data['asks'][:10],
                                    timestamp=time.time()
                                )
                                
                                # Сохраняем в локальный кеш
                                self.orderbooks[symbol][exchange_id] = orderbook
                                logger.debug(f"✅ {exchange_id} {symbol}: bid={orderbook.bids[0][0]:.6f}, ask={orderbook.asks[0][0]:.6f}")
                                
                        except Exception as e:
                            logger.warning(f"REST polling ошибка {exchange_id} {symbol}: {e}")
                            continue
                
                # Интервал polling - каждые 2 секунды
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"REST polling критическая ошибка: {e}")
                await asyncio.sleep(5)
    
    async def _initialize(self):
        """Инициализация бота"""
        logger.info("🔧 Инициализация...")
        
        # Загрузка торговых пар
        await self.discover_pairs()
        
        # Инициализация WebSocket менеджера
        self.ws_manager = WebSocketManager(
            on_orderbook_update=self._on_orderbook_update
        )
        
        logger.info(f"✅ Инициализация завершена. Активных пар: {len(self.active_pairs)}")
    
    def _print_start_banner(self):
        """Цветной стартовый баннер с конфигом и биржами."""
        try:
            mode = TRADING_CONFIG.get('mode', 'demo').upper()
            ws_source = 'WebSocket' if TRADING_CONFIG.get('use_websocket', True) else 'REST only'
            header = f"🚀 PRODUCTION ARBITRAGE BOT v1.0.0 | {mode} | Data: {ws_source}"
            print("\n" + Fore.CYAN + "═" * 80)
            print(Fore.CYAN + header)
            print(Fore.CYAN + "═" * 80)

            # Биржи
            ex_rows = []
            for ex_id in self.enabled_exchanges:
                cfg = EXCHANGES_CONFIG.get(ex_id, {})
                ex_rows.append([
                    ex_id,
                    cfg.get('name', ex_id.upper()),
                    'ON' if cfg.get('websocket', False) else 'OFF',
                    'ON' if cfg.get('poll_rest', False) else 'OFF',
                    f"{cfg.get('fee', 0.0) * 100:.2f}%"
                ])
            if ex_rows:
                print(Fore.YELLOW + "Биржи (включены):")
                print(tabulate(ex_rows, headers=['ID', 'Биржа', 'WS', 'REST', 'Комиссия'], tablefmt='github'))

            # Ключевые параметры торговли
            conf_rows = [
                ['Min Profit %', TRADING_CONFIG.get('min_profit_threshold')],
                ['Scan Interval (s)', TRADING_CONFIG.get('scan_interval')],
                ['Slippage %', TRADING_CONFIG.get('slippage_tolerance', 0.0)],
                ['Pair Cooldown (s)', TRADING_CONFIG.get('pair_cooldown_seconds')],
                ['Position Size $', TRADING_CONFIG.get('position_size_usd')],
                ['Inter-Exchange', TRADING_CONFIG.get('enable_inter_exchange', True)],
                ['Triangular', TRADING_CONFIG.get('enable_triangular', False)],
                ['Exhaustive Scan', TRADING_CONFIG.get('enable_exhaustive_pair_scanning', False)]
            ]
            print(Fore.YELLOW + "Торговые параметры:")
            print(tabulate(conf_rows, headers=['Параметр', 'Значение'], tablefmt='github'))

            # Параметры discovery
            dp = DYNAMIC_PAIRS_CONFIG
            disc_rows = [
                ['Enabled', dp.get('enabled', True)],
                ['Min Exchanges', dp.get('min_exchanges')],
                ['Max Pairs', dp.get('max_pairs')],
                ['Per-Exchange Limit', dp.get('per_exchange_discovery_limit')],
                ['Priority Pairs', len(dp.get('priority_pairs', []))]
            ]
            print(Fore.YELLOW + "Discovery пар:")
            print(tabulate(disc_rows, headers=['Параметр', 'Значение'], tablefmt='github'))
            print(Fore.CYAN + "═" * 80 + "\n")
        except Exception as e:
            logger.debug(f"_print_start_banner error: {e}")
    
    async def discover_pairs(self):
        """Динамическое обнаружение торговых пар"""
        logger.info("🔍 Поиск торговых пар...")
        
        all_pairs = defaultdict(set)  # {symbol: set(exchanges)}
        
        for exchange_id, config in EXCHANGES_CONFIG.items():
            if not config['enabled']:
                continue
                
            try:
                pairs = await self._fetch_exchange_pairs(exchange_id)
                for pair in pairs:
                    all_pairs[pair].add(exchange_id)
                    
                logger.info(f"✅ {config['name']}: {len(pairs)} пар")
                if len(pairs) == 0:
                    logger.warning(f"⚠️ ДИАГНОСТИКА {exchange_id}: получено 0 пар из API")
                
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки пар {config['name']}: {e}")
        
        # Фильтрация пар: в DEMO/TESTNET режиме приоритизируем пары, которые есть минимум на 2 из 3 бирж (OKX, Bitget, Phemex)
        enabled_set = set(self.enabled_exchanges)
        demo_mode = TRADING_CONFIG.get('mode', 'demo') in ['demo', 'testnet']  # ✅ Включаем testnet
        real_mode = TRADING_CONFIG.get('mode') == 'real'
        self.active_pairs = set()
        priority_pairs = DYNAMIC_PAIRS_CONFIG['priority_pairs']

        used_intersection = False
        # Режим строгого списка пар (CLI --only-pairs)
        only_pairs_mode = TRADING_CONFIG.get('only_pairs', False)
        if only_pairs_mode:
            desired = set(priority_pairs)
            for pair in desired:
                exs = all_pairs.get(pair, set())
                if exs & enabled_set:
                    self.active_pairs.add(pair)
            logger.info(f"🎯 Only-pairs mode: выбрано {len(self.active_pairs)} из {len(desired)} доступных пар")
            if not self.active_pairs:
                logger.warning("⚠️ Only-pairs: ни одна из указанных пар не найдена на включенных биржах")
            used_intersection = True
            logger.info("🔒 Only-pairs strict: пропускаем расширение списка пар (демо-фильтрация 2-из-3)")
        
        # В реальном режиме требуем пересечение 3-из-3 (OKX, Bitget, Phemex)
        if real_mode and not only_pairs_mode:
            # Приоритет: пересечение 2-из-2 для OKX & Bitget
            duo = {'okx', 'bitget'} & enabled_set
            if len(duo) == 2:
                two_of_two_duo = {s for s, exs in all_pairs.items() if duo.issubset(exs)}
                if two_of_two_duo:
                    # 1) Приоритетные пары
                    for pair in priority_pairs:
                        if pair in two_of_two_duo:
                            self.active_pairs.add(pair)
                            if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                break
                    # 2) Остальные пары OKX&Bitget
                    if len(self.active_pairs) < DYNAMIC_PAIRS_CONFIG['max_pairs']:
                        for pair in sorted(two_of_two_duo):
                            if pair not in self.active_pairs:
                                self.active_pairs.add(pair)
                                if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                    break
                    logger.info(f"🎯 Фильтрация на пересечение 2-из-2 (OKX, Bitget): {len(self.active_pairs)} пар")
                    used_intersection = True
                else:
                    logger.warning("⚠️ Не найдено пар с пересечением 2-из-2 для (OKX, Bitget)")
            else:
                # Фолбек: если включены все три — допускаем 3-из-3
                trio = {'okx', 'bitget', 'phemex'} & enabled_set
                if len(trio) == 3:
                    three_of_three = {s for s, exs in all_pairs.items() if trio.issubset(exs)}
                    if three_of_three:
                        for pair in priority_pairs:
                            if pair in three_of_three:
                                self.active_pairs.add(pair)
                                if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                    break
                        if len(self.active_pairs) < DYNAMIC_PAIRS_CONFIG['max_pairs']:
                            for pair in sorted(three_of_three):
                                if pair not in self.active_pairs:
                                    self.active_pairs.add(pair)
                                    if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                        break
                        logger.info(f"🎯 Фильтрация на пересечение 3-из-3 (OKX, Bitget, Phemex): {len(self.active_pairs)} пар")
                        used_intersection = True
                    else:
                        logger.warning("⚠️ Не найдено пар с пересечением 3-из-3 для (OKX, Bitget, Phemex)")
                else:
                    logger.warning(f"⚠️ Для режима real желательно включить okx и bitget; текущие включены: {sorted(list(enabled_set))}")
        if demo_mode and not only_pairs_mode:  # ✅ Теперь работает для testnet
            trio = {'okx', 'bitget', 'phemex'} & enabled_set
            if len(trio) >= 2:
                # Пары, присутствующие минимум на 2 из активных бирж из набора (OKX, Bitget, Phemex)
                two_of_three = {s for s, exs in all_pairs.items() if len(exs & trio) >= 2}
                if two_of_three:
                    # 1) Приоритет по списку приоритетных пар
                    for pair in priority_pairs:
                        if pair in two_of_three:
                            self.active_pairs.add(pair)
                            if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                break
                    # 2) Добираем оставшиеся из множества 2-из-3
                    if len(self.active_pairs) < DYNAMIC_PAIRS_CONFIG['max_pairs']:
                        for pair in sorted(two_of_three):
                            if pair not in self.active_pairs:
                                self.active_pairs.add(pair)
                                if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                                    break
                    logger.info(f"🎯 Фильтрация на пересечение 2-из-3 (OKX, Bitget, Phemex): {len(self.active_pairs)} пар")
                    used_intersection = True

        if not used_intersection and not real_mode:
            # Сначала добавляем все приоритетные пары, которые есть хотя бы на 2 биржах
            for pair in priority_pairs:
                if pair in all_pairs and len(all_pairs[pair]) >= DYNAMIC_PAIRS_CONFIG['min_exchanges']:
                    self.active_pairs.add(pair)
            # Добавляем остальные пары с минимум 2 биржами
            for symbol, exchanges in all_pairs.items():
                if len(self.active_pairs) >= DYNAMIC_PAIRS_CONFIG['max_pairs']:
                    break
                if symbol not in self.active_pairs and len(exchanges) >= DYNAMIC_PAIRS_CONFIG['min_exchanges']:
                    self.active_pairs.add(symbol)

        # Если пар мало, снижаем требования (но НЕ в режиме only-pairs)
        if len(self.active_pairs) < 10 and demo_mode and not only_pairs_mode and {'okx', 'bitget'}.issubset(enabled_set):
            # Жесткая безопасная защита: пробуем добавить самые ликвидные, если есть в пересечении
            for pair in ['BTC/USDT', 'ETH/USDT']:
                if pair in all_pairs and 'okx' in all_pairs[pair] and 'bitget' in all_pairs[pair]:
                    self.active_pairs.add(pair)
        # Аналогичная защита для real: OKX & Bitget
        if len(self.active_pairs) < 10 and real_mode and not only_pairs_mode and {'okx', 'bitget'}.issubset(enabled_set):
            top_pairs = [
                'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT',
                'PEPE/USDT', 'OP/USDT', 'ARB/USDT', 'TON/USDT', 'LINK/USDT',
                'BCH/USDT', 'LTC/USDT', 'ADA/USDT', 'MATIC/USDT'
            ]
            for pair in top_pairs:
                if pair in all_pairs and 'okx' in all_pairs[pair] and 'bitget' in all_pairs[pair]:
                    self.active_pairs.add(pair)
        elif only_pairs_mode:
            logger.info("🔒 Only-pairs strict: пропускаем добавление базовых пар по защите")

        if len(self.active_pairs) < 30 and not used_intersection and not only_pairs_mode:
            logger.info(f"⚠️ Мало пар с пересечением. Добавляю топовые пары...")
            # Добавляем первые 50 приоритетных пар независимо от пересечения
            for pair in priority_pairs[:50]:
                if pair in all_pairs:
                    self.active_pairs.add(pair)
        elif only_pairs_mode and not used_intersection:
            logger.info("🔒 Only-pairs strict: пропускаем добавление топовых пар")

        # Дополнительная фильтрация: ограничиваем активные пары теми,
        # которые реально присутствуют в ccxt markets на требуемом пересечении.
        try:
            # Реальный режим: проверка присутствия в markets на OKX&Bitget (2-из-2) с фолбеком
            if real_mode and not only_pairs_mode:
                duo_set = {'okx', 'bitget'} & enabled_set
                if len(duo_set) >= 2:
                    # Собираем множества символов из ccxt для OKX и Bitget
                    ccxt_symbols_by_ex = {}
                    for ex in sorted(duo_set):
                        info = self.trading_engine.exchange_clients.get(ex, {}) if hasattr(self, 'trading_engine') else {}
                        ccxt_client = info.get('ccxt') if isinstance(info, dict) else None
                        if ccxt_client:
                            try:
                                syms = set(getattr(ccxt_client, 'symbols', []) or list((getattr(ccxt_client, 'markets', {}) or {}).keys()))
                            except Exception:
                                syms = set()
                            ccxt_symbols_by_ex[ex] = syms
                    loaded_sets = {ex for ex, syms in ccxt_symbols_by_ex.items() if syms}
                    loaded_count = len(loaded_sets)
                    if loaded_count >= 2:
                        def ccxt_presence_both(sym: str) -> bool:
                            return all(sym in syms for ex, syms in ccxt_symbols_by_ex.items())
                        before_cnt = len(self.active_pairs)
                        self.active_pairs = {s for s in self.active_pairs if ccxt_presence_both(s)}
                        logger.info(f"🎯 Доп. фильтрация по CCXT markets (real, OKX&Bitget 2-из-2): {before_cnt} -> {len(self.active_pairs)} пар")
                    elif loaded_count == 1:
                        def ccxt_presence_loaded(sym: str) -> bool:
                            return any(sym in syms for ex, syms in ccxt_symbols_by_ex.items())
                        before_cnt = len(self.active_pairs)
                        self.active_pairs = {s for s in self.active_pairs if ccxt_presence_loaded(s)}
                        logger.info(f"🎯 Доп. фильтрация по CCXT markets (real, >=1 из {sorted(list(loaded_sets))}): {before_cnt} -> {len(self.active_pairs)} пар")
                    else:
                        logger.info("ℹ️ Пропуск доп. фильтрации по CCXT: ни у OKX/Bitget не загружены markets (real)")
                else:
                    logger.info("ℹ️ Пропуск доп. фильтрации по CCXT: OKX и Bitget неактивны или не оба включены")
            elif demo_mode and not only_pairs_mode:
                demo_set = enabled_set & set(TRADING_CONFIG.get('demo_supported_exchanges', []))
                # Собираем множества символов из ccxt для доступных клиентов
                ccxt_symbols_by_ex = {}
                for ex in sorted(demo_set):
                    info = self.trading_engine.exchange_clients.get(ex, {}) if hasattr(self, 'trading_engine') else {}
                    ccxt_client = info.get('ccxt') if isinstance(info, dict) else None
                    if ccxt_client:
                        try:
                            syms = set(getattr(ccxt_client, 'symbols', []) or list((getattr(ccxt_client, 'markets', {}) or {}).keys()))
                        except Exception:
                            syms = set()
                        ccxt_symbols_by_ex[ex] = syms
                # Считаем только те биржи, у которых markets действительно загружены (не пустые)
                loaded_sets = {ex for ex, syms in ccxt_symbols_by_ex.items() if syms}
                loaded_count = len(loaded_sets)
                if loaded_count >= 2:
                    def ccxt_presence_count(sym: str) -> int:
                        return sum(1 for syms in ccxt_symbols_by_ex.values() if sym in syms)
                    before_cnt = len(self.active_pairs)
                    self.active_pairs = {s for s in self.active_pairs if ccxt_presence_count(s) >= 2}
                    logger.info(f"🎯 Доп. фильтрация по CCXT markets (demo, 2-из-3): {before_cnt} -> {len(self.active_pairs)} пар")
                    # Если пар стало слишком мало, пытаемся добавить базовые ликвидные, если присутствуют минимум в 2 markets
                    if len(self.active_pairs) < 5:
                        for pair in ['BTC/USDT', 'ETH/USDT']:
                            if ccxt_presence_count(pair) >= 2:
                                self.active_pairs.add(pair)
                elif loaded_count == 1:
                    # Смягчаем ограничение: оставляем пары, присутствующие хотя бы в одном загруженном markets
                    def ccxt_presence_count(sym: str) -> int:
                        return sum(1 for syms in ccxt_symbols_by_ex.values() if sym in syms)
                    before_cnt = len(self.active_pairs)
                    self.active_pairs = {s for s in self.active_pairs if ccxt_presence_count(s) >= 1}
                    logger.info(f"🎯 Доп. фильтрация по CCXT markets (demo, >=1 из {sorted(list(loaded_sets))}): {before_cnt} -> {len(self.active_pairs)} пар")
                    if len(self.active_pairs) < 5:
                        for pair in ['BTC/USDT', 'ETH/USDT']:
                            if ccxt_presence_count(pair) >= 1:
                                self.active_pairs.add(pair)
                else:
                    # Если никто не загрузил markets, пропускаем CCXT-фильтрацию
                    logger.info("ℹ️ Пропуск доп. фильтрации по CCXT: ни у одной биржи не загружены markets")
            elif only_pairs_mode:
                logger.info("🔒 Only-pairs strict: пропускаем доп. фильтрацию по CCXT markets")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка доп. фильтрации по CCXT markets: {e}")

        logger.info(f"📊 Найдено {len(self.active_pairs)} активных пар для арбитража")
        if len(self.active_pairs) == 0:
            logger.warning(f"⚠️ ДИАГНОСТИКА: enabled_set={enabled_set}, trio intersection={enabled_set & {'okx', 'bitget', 'phemex'}}, all_pairs count={len(all_pairs)}")
            logger.warning(f"⚠️ ДИАГНОСТИКА: demo_mode={demo_mode}, used_intersection={used_intersection}, only_pairs_mode={only_pairs_mode}")
        if only_pairs_mode:
            try:
                logger.info(f"🔒 Only-pairs список: {sorted(list(self.active_pairs))}")
            except Exception:
                logger.info("🔒 Only-pairs список: <error formatting pairs list>")
        
        # Обновление времени
        self.last_pair_update = time.time()
    
    async def _fetch_exchange_pairs(self, exchange_id: str) -> List[str]:
        """Получить список пар с биржи"""
        if exchange_id not in EXCHANGES_CONFIG:
            logger.error(f"Exchange {exchange_id} not found in EXCHANGES_CONFIG")
            logger.error(f"Available exchanges: {list(EXCHANGES_CONFIG.keys())}")
            return []
        
        config = EXCHANGES_CONFIG[exchange_id]
        # Лимит количества пар, получаемых с каждой биржи при discovery
        discovery_limit = DYNAMIC_PAIRS_CONFIG.get('per_exchange_discovery_limit', 100)
        
        try:
            async with aiohttp.ClientSession() as session:
                if exchange_id == 'mexc':
                    url = f"{config['rest_url']}/api/v3/exchangeInfo"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data.get('symbols', []):
                            # MEXC использует строковый статус: "1" = активен
                            if symbol.get('status') == '1' and symbol.get('quoteAsset') == 'USDT':
                                base = symbol['baseAsset']
                                pairs.append(f"{base}/USDT")
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'bybit':
                    url = f"{config['rest_url']}/v5/market/instruments-info?category=spot"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data['result']['list']:
                            if symbol['status'] == 'Trading' and 'USDT' in symbol['symbol']:
                                base = symbol['symbol'].replace('USDT', '')
                                pairs.append(f"{base}/USDT")
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'huobi':
                    url = f"{config['rest_url']}/v1/common/symbols"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data.get('data', []):
                            if symbol['state'] == 'online' and symbol['quote-currency'] == 'usdt':
                                pairs.append(f"{symbol['base-currency'].upper()}/USDT")
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'binance':
                    url = "https://api.binance.com/api/v3/exchangeInfo"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for symbol in data.get('symbols', []):
                            if symbol['status'] == 'TRADING' and symbol['quoteAsset'] == 'USDT':
                                pairs.append(f"{symbol['baseAsset']}/USDT")
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'okx':
                    url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for ticker in data.get('data', []):
                            if 'USDT' in ticker['instId']:
                                symbol = ticker['instId'].replace('-', '/')
                                pairs.append(symbol)
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'gate':
                    url = "https://api.gateio.ws/api/v4/spot/currency_pairs"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for pair in data:
                            if pair['trade_status'] == 'tradable' and 'USDT' in pair['id']:
                                pairs.append(pair['id'].replace('_', '/'))
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'bitget':
                    url = "https://api.bitget.com/api/spot/v1/market/tickers"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for ticker in data.get('data', []):
                            sym_raw = str(ticker.get('symbol', '')).upper()
                            if not sym_raw:
                                continue
                            # Убираем суффиксы канала спота Bitget (например, _SPBL)
                            basequote = sym_raw.split('_')[0]
                            # Нормализация: ожидаем BASEUSDT
                            if basequote.endswith('USDT') and len(basequote) > 4:
                                base = basequote[:-4]
                                pairs.append(f"{base}/USDT")
                        return pairs[:discovery_limit]
                        
                elif exchange_id == 'phemex':
                    url = "https://api.phemex.com/public/products"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        pairs = []
                        for product in data.get('data', {}).get('products', []):
                            if product.get('type') == 'Spot' and product['quoteCurrency'] == 'USDT':
                                pairs.append(f"{product['baseCurrency']}/USDT")
                        return pairs[:discovery_limit]
                        
                # Fallback для неизвестных бирж
                else:
                    logger.warning(f"⚠️ Неизвестная биржа {exchange_id}, используем базовый список")
                    return [
                        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
                        'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT'
                    ]
                    
        except Exception as e:
            logger.error(f"Ошибка получения пар {exchange_id}: {e}")
            return []
    
    async def _on_orderbook_update(self, orderbook: OrderBook):
        """Обработчик обновления стакана"""
        try:
            # Сохраняем стакан (с нормализацией символа)
            norm_symbol = normalize_symbol(getattr(orderbook, 'symbol', None))
            if not norm_symbol:
                return
            # Обновим символ у объекта для консистентности
            orderbook.symbol = norm_symbol
            if norm_symbol in self.active_pairs:
                if norm_symbol not in self.orderbooks:
                    self.orderbooks[norm_symbol] = {}
                self.orderbooks[norm_symbol][orderbook.exchange] = orderbook
                self.statistics['ws_messages'] += 1
            else:
                # Пропускаем обновление для неактивных пар
                pass
                
        except Exception as e:
            logger.error(f"Ошибка обработки orderbook: {e}")
            self.statistics['errors'] += 1
    
    async def _run_websocket_manager(self):
        """Запуск WebSocket менеджера"""
        try:
            await self.ws_manager.start(list(self.active_pairs))
        except Exception as e:
            logger.error(f"Ошибка WebSocket менеджера: {e}")
    
    async def _scan_opportunities(self):
        """Основной цикл сканирования арбитражных возможностей"""
        logger.info("🔍 Запуск сканера арбитража...")
        
        while self.running:
            # Нормальная задержка между сканами; изменяется в случае ошибки
            delay = TRADING_CONFIG['scan_interval']
            try:
                scan_start = time.time()
                # Получаем текущие ордербуки
                current_time = time.time()
                opportunities = []
                
                # Сканирование межбиржевого арбитража
                if TRADING_CONFIG.get('enable_inter_exchange', True):
                    for symbol, exchanges_data in self.orderbooks.items():
                        if len(exchanges_data) < 2:
                            continue
                        # Режим: исчерпывающий перебор пар или одиночная лучшая пара
                        if TRADING_CONFIG.get('enable_exhaustive_pair_scanning', False):
                            found_opps = self._find_inter_exchange_pairs(symbol, exchanges_data)
                            for opp in found_opps:
                                # Считаем кандидатов до проверки ликвидности
                                self.statistics['candidates_detected'] += 1
                                if self._check_liquidity_for_opportunity(opp):
                                    await self.opportunity_queue.put(opp)
                                    opportunities.append(opp)
                                    self.last_opportunity_time = time.time()
                                    # Пер-метрики по найденной возможности
                                    symbol = opp.symbols[0]
                                    buy_ex, sell_ex = opp.exchanges[0], opp.exchanges[1]
                                    pair_key = f"{symbol}|{buy_ex}->{sell_ex}"
                                    self.stats_by_pair[pair_key]['opportunities'] += 1
                                    self.stats_by_exchange[buy_ex]['opportunities'] += 1
                                    self.stats_by_exchange[sell_ex]['opportunities'] += 1
                                    # Устанавливаем кулдаун для пары покупка->продажа
                                    key = f"{symbol}_{opp.exchanges[0]}_{opp.exchanges[1]}"
                                    self.opportunity_cooldowns[key] = time.time()
                                    # Логирование каждой найденной возможности
                                    print("\n" + "🎯"*40)
                                    print(f"\n💎 НАЙДЕНА АРБИТРАЖНАЯ ВОЗМОЖНОСТЬ!")
                                    print(f"  Пара: {symbol}")
                                    print(f"  Маршрут: {opp.exchanges[0]} → {opp.exchanges[1]}")
                                    print(f"  Прибыль: {opp.expected_profit_pct:.4f}%")
                                    print(f"  Ожидаемая прибыль: ${opp.expected_profit_usd:.2f}")
                                    print("🎯"*40 + "\n")
                        else:
                            opportunity = self._check_inter_exchange_arbitrage(
                                symbol, exchanges_data
                            )
                            if opportunity:
                                # Считаем кандидатов до проверки ликвидности
                                self.statistics['candidates_detected'] += 1
                                # Проверяем ликвидность перед добавлением
                                if self._check_liquidity_for_opportunity(opportunity):
                                    await self.opportunity_queue.put(opportunity)
                                    opportunities.append(opportunity)
                                    self.last_opportunity_time = time.time()
                                    # Пер-метрики по найденной возможности
                                    symbol = opportunity.symbols[0]
                                    buy_ex, sell_ex = opportunity.exchanges[0], opportunity.exchanges[1]
                                    pair_key = f"{symbol}|{buy_ex}->{sell_ex}"
                                    self.stats_by_pair[pair_key]['opportunities'] += 1
                                    self.stats_by_exchange[buy_ex]['opportunities'] += 1
                                    self.stats_by_exchange[sell_ex]['opportunities'] += 1
                                    
                                    # Красивый вывод найденной возможности
                                    print("\n" + "🎯"*40)
                                    print(f"\n💎 НАЙДЕНА АРБИТРАЖНАЯ ВОЗМОЖНОСТЬ!")
                                    print(f"  Пара: {symbol}")
                                    print(f"  Маршрут: {opportunity.exchanges[0]} → {opportunity.exchanges[1]}")
                                    print(f"  Прибыль: {opportunity.expected_profit_pct:.4f}%")
                                    print(f"  Ожидаемая прибыль: ${opportunity.expected_profit_usd:.2f}")
                                    print("🎯"*40 + "\n") 
                
                # Сканирование треугольного арбитража
                if TRADING_CONFIG.get('enable_triangular', False):
                    for exchange, config in EXCHANGES_CONFIG.items():
                        if not config['enabled']:
                            continue
                        
                        # Собираем ордербуки одной биржи
                        exchange_orderbooks = {}
                        for symbol, exchanges_data in self.orderbooks.items():
                            if exchange in exchanges_data:
                                orderbook = exchanges_data[exchange]
                                # Конвертируем OrderBook в словарь для треугольного арбитража
                                exchange_orderbooks[symbol] = {
                                    'bids': orderbook.bids if hasattr(orderbook, 'bids') else [],
                                    'asks': orderbook.asks if hasattr(orderbook, 'asks') else []
                                }
                        
                        if len(exchange_orderbooks) >= 3:  # Минимум 3 пары для треугольника
                            triangular_opportunities = self.triangular_scanner.scan_opportunities(
                                exchange,
                                exchange_orderbooks,
                                config.get('fee', 0.001) * 100
                            )
                            
                            for t_opp in triangular_opportunities:
                                await self.opportunity_queue.put(t_opp)
                                opportunities.append(t_opp)
                
                # Обновление статистики по найденным возможностям
                if len(opportunities) > 0:
                    self.statistics['opportunities_found'] += len(opportunities)
                    self.last_opportunity_time = time.time()
                
            except Exception as e:
                logger.error(f"Ошибка сканера: {e}")
                self.statistics['errors'] += 1
                delay = 5
            finally:
                # Exception-safe инкремент сканов и логирование каждые 10
                try:
                    self.scan_counter += 1
                    self.statistics['scans'] = self.statistics.get('scans', 0) + 1
                    if self.scan_counter % 10 == 0:
                        logger.info(f"🔍 Сканирований: {self.scan_counter}")
                except Exception:
                    pass
                # Единая задержка после цикла
                await asyncio.sleep(delay)
    
    async def _run_executor(self):
        """Исполнитель арбитражных сделок"""
        logger.info("💼 Запуск исполнителя сделок...")
        
        while self.running:
            try:
                # Ожидание возможности
                opportunity = await asyncio.wait_for(
                    self.opportunity_queue.get(),
                    timeout=10
                )
                
                # Проверка свежести
                if not opportunity.is_fresh:
                    logger.warning("⚠️ Возможность устарела")
                    continue
                
                # Исполнение
                if isinstance(opportunity, ArbitrageOpportunity):
                    result = await self.trading_engine.execute_arbitrage(
                        opportunity
                    )
                elif isinstance(opportunity, TriangularOpportunity):
                    # Исполнение треугольного арбитража
                    result = await self.triangular_executor.execute_triangular(
                        opportunity
                    )
                
                # Обновление пер-метрик по результату
                if isinstance(opportunity, ArbitrageOpportunity):
                    symbol = opportunity.symbols[0]
                    buy_ex, sell_ex = opportunity.exchanges[0], opportunity.exchanges[1]
                    pair_key = f"{symbol}|{buy_ex}->{sell_ex}"
                    # Базовые инкременты
                    self.stats_by_pair[pair_key]['trades'] += 1
                    self.stats_by_exchange[buy_ex]['trades'] += 1
                    self.stats_by_exchange[sell_ex]['trades'] += 1
                    if result:
                        self.statistics['trades_executed'] += 1
                        self.stats_by_pair[pair_key]['successful'] += 1
                        self.stats_by_exchange[buy_ex]['successful'] += 1
                        self.stats_by_exchange[sell_ex]['successful'] += 1
                        # Попытка получить данные о прибыли из trade_history движка
                        profit_usd = 0.0
                        profit_pct = 0.0
                        volume_usd = TRADING_CONFIG.get('position_size_usd', 100)
                        if getattr(self.trading_engine, 'trade_history', None):
                            last_trade = self.trading_engine.trade_history[-1]
                            try:
                                if (last_trade.get('exchanges') == [buy_ex, sell_ex] and
                                    last_trade.get('symbols') == [symbol]):
                                    profit_usd = float(last_trade.get('net_profit', 0.0))
                                    profit_pct = float(last_trade.get('profit_pct', 0.0))
                                    volume_usd = float(last_trade.get('position_size', volume_usd))
                            except Exception:
                                pass
                        # Атрибутируем прибыль связке и обеим биржам (полная сумма каждой)
                        self.stats_by_pair[pair_key]['profit_usd'] += profit_usd
                        self.stats_by_pair[pair_key]['profit_pct_sum'] += profit_pct
                        self.stats_by_pair[pair_key]['volume_usd'] += volume_usd
                        self.stats_by_exchange[buy_ex]['profit_usd'] += profit_usd
                        self.stats_by_exchange[buy_ex]['profit_pct_sum'] += profit_pct
                        self.stats_by_exchange[buy_ex]['volume_usd'] += volume_usd
                        self.stats_by_exchange[sell_ex]['profit_usd'] += profit_usd
                        self.stats_by_exchange[sell_ex]['profit_pct_sum'] += profit_pct
                        self.stats_by_exchange[sell_ex]['volume_usd'] += volume_usd
                        logger.info(f"✅ Сделка исполнена успешно")
                    else:
                        self.stats_by_pair[pair_key]['failed'] += 1
                        self.stats_by_exchange[buy_ex]['failed'] += 1
                        self.stats_by_exchange[sell_ex]['failed'] += 1
                        logger.warning(f"❌ Сделка не исполнена")
                    
                    # Обновляем балансы после успешной сделки в реальном режиме (межбиржевой арбитраж)
                    if result:
                        try:
                            if TRADING_CONFIG.get('mode') == 'real':
                                await self.trading_engine.update_balances()
                                logger.info("🔄 Балансы обновлены после сделки (real)")
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка обновления балансов после сделки: {e}")
                
                # Обновление балансов для успешных треугольных сделок в реальном режиме
                if isinstance(opportunity, TriangularOpportunity) and result and TRADING_CONFIG.get('mode') == 'real':
                    try:
                        await self.trading_engine.update_balances()
                        logger.info("🔄 Балансы обновлены после треугольной сделки (real)")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка обновления балансов после треугольной сделки: {e}")
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Ошибка исполнителя: {e}")
                self.statistics['errors'] += 1
                await asyncio.sleep(1)
    
    async def _run_pair_updater(self):
        """Периодическое обновление торговых пар"""
        while self.running:
            try:
                # Проверка времени последнего обновления
                if time.time() - self.last_pair_update > DYNAMIC_PAIRS_CONFIG['update_interval']:
                    logger.info("🔍 Обнаружение торговых пар...")
                    try:
                        await self.discover_pairs()
                    except Exception as e:
                        logger.error(f"Ошибка при обнаружении пар: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                        raise
                    
                    if not self.active_pairs:
                        raise Exception("Нет активных торговых пар")
                    
                    # Перезапуск WebSocket с новыми парами
                    await self.ws_manager.stop()
                    await asyncio.sleep(2)
                    asyncio.create_task(
                        self.ws_manager.start(list(self.active_pairs))
                    )
                
                await asyncio.sleep(60)  # Проверка каждую минуту
                
            except Exception as e:
                logger.error(f"Ошибка обновления пар: {e}")
                await asyncio.sleep(300)
    
    async def _run_statistics(self):
        """Периодический вывод статистики"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Обновление каждые 30 секунд

                # Собираем данные о подключенных биржах
                connected_exchanges = []
                disconnected_exchanges = []
                if self.ws_manager and hasattr(self.ws_manager, 'connections'):
                    conns = set(self.ws_manager.connections.keys())
                else:
                    conns = set()
                for exchange_id in self.enabled_exchanges:
                    if exchange_id in conns:
                        connected_exchanges.append(exchange_id)
                    else:
                        disconnected_exchanges.append(exchange_id)

                # Подсчет активных пар по биржам
                pairs_by_exchange = {}
                for symbol in self.active_pairs:
                    if symbol in self.orderbooks:
                        for exchange in self.orderbooks[symbol]:
                            pairs_by_exchange[exchange] = pairs_by_exchange.get(exchange, 0) + 1

                # Заголовок
                print("\n" + Fore.CYAN + "═" * 80)
                print(Fore.CYAN + "📊 СТАТУС АРБИТРАЖНОГО БОТА" + Style.RESET_ALL + f"  |  {datetime.now().strftime('%H:%M:%S')}")
                print(Fore.CYAN + "═" * 80)

                # Таблица подключений
                conn_rows = []
                for ex_id in self.enabled_exchanges:
                    name = EXCHANGES_CONFIG.get(ex_id, {}).get('name', ex_id.upper())
                    # Биржа считается онлайн если есть WebSocket подключение ИЛИ активные пары (REST polling)
                    ws_connected = ex_id in connected_exchanges
                    has_active_pairs = pairs_by_exchange.get(ex_id, 0) > 0
                    online = ws_connected or has_active_pairs
                    status = (Fore.GREEN + 'ONLINE' + Style.RESET_ALL) if online else (Fore.RED + 'OFFLINE' + Style.RESET_ALL)
                    conn_rows.append([ex_id, name, status, pairs_by_exchange.get(ex_id, 0)])
                if conn_rows:
                    print(Fore.YELLOW + "🔌 Подключения:")
                    print(tabulate(conn_rows, headers=['ID', 'Биржа', 'Статус', 'Активных пар'], tablefmt='github'))

                # Сводка сканера
                scans = self.statistics.get('scans', 0)
                candidates = self.statistics.get('candidates_detected', 0)
                opps = self.statistics.get('opportunities_found', 0)
                trades = self.statistics.get('trades_executed', 0)
                errors = self.statistics.get('errors', 0)
                if scans > 0:
                    uptime = time.time() - self.statistics.get('start_time', time.time())
                    scan_rate = scans / max(uptime, 1)
                else:
                    scan_rate = 0.0
                print(Fore.YELLOW + "💰 Арбитраж:")
                print(tabulate([
                    ['Scans', scans],
                    ['Candidates', candidates],
                    ['Opportunities', opps],
                    ['Trades', trades],
                    ['Errors', errors],
                    ['Scan rate (1/s)', f"{scan_rate:.2f}"]
                ], headers=['Метрика', 'Значение'], tablefmt='github'))

                # Топ по биржам
                if self.stats_by_exchange:
                    top_ex = sorted(self.stats_by_exchange.items(), key=lambda kv: kv[1]['trades'], reverse=True)[:5]
                    ex_rows = []
                    for ex, s in top_ex:
                        avg_pct = (s['profit_pct_sum'] / s['successful']) if s['successful'] > 0 else 0.0
                        ex_rows.append([ex, s['opportunities'], s['trades'], f"✅{s['successful']}/❌{s['failed']}", f"${s['profit_usd']:.2f}", f"{avg_pct:.3f}%"]) 
                    if ex_rows:
                        print(Fore.YELLOW + "📈 По биржам (топ-5):")
                        print(tabulate(ex_rows, headers=['Биржа', 'Возм.', 'Сделки', 'Успех/Провал', 'Прибыль $', 'Ср.%'], tablefmt='github'))

                # Топ по связкам
                if self.stats_by_pair:
                    top_pairs = sorted(self.stats_by_pair.items(), key=lambda kv: kv[1]['successful'], reverse=True)[:5]
                    pair_rows = []
                    for pair, s in top_pairs:
                        avg_pct = (s['profit_pct_sum'] / s['successful']) if s['successful'] > 0 else 0.0
                        pair_rows.append([pair, s['opportunities'], s['trades'], f"✅{s['successful']}/❌{s['failed']}", f"${s['profit_usd']:.2f}", f"{avg_pct:.3f}%"]) 
                    if pair_rows:
                        print(Fore.YELLOW + "🔗 По связкам (топ-5):")
                        print(tabulate(pair_rows, headers=['Связка', 'Возм.', 'Сделки', 'Успех/Провал', 'Прибыль $', 'Ср.%'], tablefmt='github'))

                # Последняя возможность
                if hasattr(self, 'last_opportunity_time') and self.last_opportunity_time:
                    time_since = time.time() - self.last_opportunity_time
                    print(Fore.YELLOW + f"⏰ Последняя возможность: {time_since:.0f} сек назад")

                print(Fore.CYAN + "═" * 80 + "\n")
            
            except Exception as e:
                logger.error(f"Ошибка вывода статистики: {e}")
    
    def _check_liquidity_for_opportunity(self, opportunity: ArbitrageOpportunity) -> bool:
        """Проверяет ликвидность для арбитражной возможности"""
        try:
            # Получаем ордербуки
            buy_exchange = opportunity.exchanges[0]
            sell_exchange = opportunity.exchanges[1]
            symbol = opportunity.symbols[0]
            
            if symbol not in self.orderbooks:
                return False
            
            buy_orderbook_obj = self.orderbooks[symbol].get(buy_exchange)
            sell_orderbook_obj = self.orderbooks[symbol].get(sell_exchange)
            
            if not buy_orderbook_obj or not sell_orderbook_obj:
                return False
            
            # Конвертируем OrderBook в словарь для анализатора
            buy_orderbook = {
                'bids': buy_orderbook_obj.bids if hasattr(buy_orderbook_obj, 'bids') else [],
                'asks': buy_orderbook_obj.asks if hasattr(buy_orderbook_obj, 'asks') else []
            }
            sell_orderbook = {
                'bids': sell_orderbook_obj.bids if hasattr(sell_orderbook_obj, 'bids') else [],
                'asks': sell_orderbook_obj.asks if hasattr(sell_orderbook_obj, 'asks') else []
            }
            
            # Анализируем ликвидность
            volume_usd = TRADING_CONFIG.get('position_size_usd', 100)
            buy_analysis = self.orderbook_analyzer.analyze_liquidity(
                buy_orderbook,
                'buy',
                volume_usd,
                buy_exchange,
                symbol
            )
            
            sell_analysis = self.orderbook_analyzer.analyze_liquidity(
                sell_orderbook,
                'sell',
                volume_usd,
                sell_exchange,
                symbol
            )
            
            # Проходит если обе стороны имеют достаточную ликвидность
            if buy_analysis.can_execute and sell_analysis.can_execute:
                # Корректируем ожидаемую прибыль с учетом проскальзывания
                slippage_impact = buy_analysis.price_impact + sell_analysis.price_impact
                opportunity.expected_profit_pct -= slippage_impact
                
                return opportunity.expected_profit_pct > TRADING_CONFIG['min_profit_threshold']
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки ликвидности: {e}")
            return False
    
    def _check_inter_exchange_arbitrage(self, symbol: str, exchanges_data: Dict) -> Optional[ArbitrageOpportunity]:
        """Проверка межбиржевого арбитража"""
        try:
            # Находим лучшие цены
            best_bid = None
            best_bid_exchange = None
            best_bid_volume = 0
            best_ask = None
            best_ask_exchange = None
            best_ask_volume = 0
            
            # Собираем все цены для логирования
            prices_info = []
            stale_info = []
            considered_exchanges = 0
            stale_exchanges = 0
            
            for exchange, orderbook in exchanges_data.items():
                # Проверка свежести данных (пер-"биржевой" TTL с учётом REST-поллинга)
                allowed_age = TRADING_CONFIG['max_opportunity_age']
                ex_cfg = EXCHANGES_CONFIG.get(exchange, {})
                if ex_cfg.get('poll_rest'):
                    # Разрешаем возраст не меньше интервала поллинга + небольшой запас 0.5s
                    poll_interval = ex_cfg.get('poll_interval', 0)
                    allowed_age = max(allowed_age, poll_interval + 0.5)
                
                if orderbook.age > allowed_age:
                    stale_exchanges += 1
                    stale_info.append(f"{exchange}:{orderbook.age:.2f}s>TTL{allowed_age:.2f}s")
                    continue
                
                considered_exchanges += 1
                
                if orderbook.best_bid and orderbook.best_ask:
                    prices_info.append(f"{exchange}: bid={orderbook.best_bid:.4f}, ask={orderbook.best_ask:.4f}")
                
                if orderbook.best_bid and (not best_bid or orderbook.best_bid > best_bid):
                    best_bid = orderbook.best_bid
                    best_bid_exchange = exchange
                    best_bid_volume = orderbook.get_depth_volume(1)['bid']
                
                if orderbook.best_ask and (not best_ask or orderbook.best_ask < best_ask):
                    best_ask = orderbook.best_ask
                    best_ask_exchange = exchange
                    best_ask_volume = orderbook.get_depth_volume(1)['ask']
            
            # Логируем собранные цены каждые 100 проверок
            if hasattr(self, '_check_counter'):
                self._check_counter += 1
            else:
                self._check_counter = 1
                
            if self._check_counter % 100 == 0 and prices_info:
                logger.info(f"📊 {symbol} цены: {' | '.join(prices_info[:3])}")
                if stale_exchanges:
                    logger.info(f"⏱️ {symbol} свежесть: допущено={considered_exchanges}, отброшено по старости={stale_exchanges} [{'; '.join(stale_info[:3])}]")
            
            if not (best_bid and best_ask):
                if self._check_counter % 500 == 0:
                    logger.debug(f"  {symbol}: Недостаточно данных (bid={best_bid}, ask={best_ask})")
                return None
                
            if best_bid_exchange == best_ask_exchange:
                return None
            # CCXT пред-фильтр: символ должен присутствовать на обеих биржах по данным ccxt
            try:
                if not self._ccxt_pair_present(symbol, best_ask_exchange, best_bid_exchange):
                    # Ограничим частоту логов
                    cnt = getattr(self, '_ccxt_skip_log_counter', 0)
                    if cnt % 50 == 0:
                        p_buy, m_buy, s_buy = self._ccxt_presence(best_ask_exchange, symbol)
                        p_sell, m_sell, s_sell = self._ccxt_presence(best_bid_exchange, symbol)
                        logger.info(
                            f"⏭️ CCXT prefilter skip {symbol}: {best_ask_exchange}[has={p_buy},mkt={m_buy}] -> {best_bid_exchange}[has={p_sell},mkt={m_sell}]"
                        )
                    self._ccxt_skip_log_counter = cnt + 1
                    return None
            except Exception:
                pass
            
            # Расчет прибыли
            spread_pct = (best_bid - best_ask) / best_ask * 100
            
            # ЛОГИРОВАНИЕ КАНДИДАТОВ для анализа (каждые 100 проверок)
            if self._check_counter % 100 == 0 and spread_pct > 0.01:
                logger.info(f"📊 Кандидат {symbol}: спред={spread_pct:.3f}% {best_ask_exchange}@{best_ask:.6f} → {best_bid_exchange}@{best_bid:.6f}")
            
            # Расчет комиссий  
            if best_ask_exchange in EXCHANGES_CONFIG:
                buy_fee = EXCHANGES_CONFIG[best_ask_exchange].get('fee', 0.001) * 100
            else:
                buy_fee = 0.1
                
            if best_bid_exchange in EXCHANGES_CONFIG:
                sell_fee = EXCHANGES_CONFIG[best_bid_exchange].get('fee', 0.001) * 100
            else:
                sell_fee = 0.1
                
            total_fees = buy_fee + sell_fee
            
            # Учет слиппеджа
            slippage = TRADING_CONFIG['slippage_tolerance'] * 100
            
            # Чистая прибыль
            net_profit_pct = spread_pct - total_fees - slippage
            
            # Детальное логирование для близких к порогу возможностей
            if spread_pct > 0:
                if self._check_counter % 50 == 0 or net_profit_pct > -0.1:
                    logger.info(f"🔍 {symbol}: {best_ask_exchange}→{best_bid_exchange}")
                    logger.info(f"   Спред: {spread_pct:.4f}% (bid={best_bid:.4f}, ask={best_ask:.4f})")
                    logger.info(f"   Комиссии: {total_fees:.4f}% (покупка={buy_fee:.3f}%, продажа={sell_fee:.3f}%)")
                    logger.info(f"   Слиппедж: {slippage:.3f}%")
                    logger.info(f"   Чистая прибыль: {net_profit_pct:.4f}% (порог: {TRADING_CONFIG['min_profit_threshold']}%)")
                    logger.info(f"   Объемы: bid={best_bid_volume:.2f}, ask={best_ask_volume:.2f}")
            
            if net_profit_pct < TRADING_CONFIG['min_profit_threshold']:
                return None
            
            # Проверяем кулдаун для этой возможности
            opportunity_key = f"{symbol}_{best_ask_exchange}_{best_bid_exchange}"
            current_time = time.time()
            
            cooldown = TRADING_CONFIG.get('pair_cooldown_seconds', 30)
            if opportunity_key in self.opportunity_cooldowns:
                if current_time - self.opportunity_cooldowns[opportunity_key] < cooldown:
                    return None
            
            # НАЙДЕНА ВОЗМОЖНОСТЬ!
            logger.warning(f"🎯 АРБИТРАЖ НАЙДЕН! {symbol}: {best_ask_exchange}→{best_bid_exchange}, прибыль: {net_profit_pct:.4f}%")
            
            # Записываем время для кулдауна
            self.opportunity_cooldowns[opportunity_key] = current_time
            
            # Минимальный объем
            min_volume = min(best_bid_volume, best_ask_volume) * best_ask
            
            # Расчет прибыли в USD
            position_size = TRADING_CONFIG.get('position_size_usd', 100)
            expected_profit_usd = position_size * net_profit_pct / 100
            
            return ArbitrageOpportunity(
                type='inter_exchange',
                path=[best_ask_exchange, best_bid_exchange],
                exchanges=[best_ask_exchange, best_bid_exchange],
                symbols=[symbol],
                prices={
                    f'{best_ask_exchange}_ask': best_ask,
                    f'{best_bid_exchange}_bid': best_bid
                },
                volumes={
                    best_ask_exchange: best_ask_volume,
                    best_bid_exchange: best_bid_volume
                },
                expected_profit_pct=net_profit_pct,
                expected_profit_usd=expected_profit_usd,
                min_volume=min_volume
            )
            
        except Exception as e:
            logger.error(f"Ошибка проверки арбитража: {e}")
            return None

    def _ccxt_presence(self, exchange: str, symbol: str):
        """Возвращает (present, markets_count, symbols_count) для пары на бирже по данным ccxt."""
        try:
            info = self.trading_engine.exchange_clients.get(exchange, {}) if hasattr(self, 'trading_engine') else {}
            ccxt_client = info.get('ccxt') if isinstance(info, dict) else None
            if not ccxt_client:
                return False, 0, 0
            try:
                markets = getattr(ccxt_client, 'markets', {}) or {}
                mkt_count = len(markets)
            except Exception:
                markets = {}
                mkt_count = 0
            try:
                symbols = set(getattr(ccxt_client, 'symbols', []))
            except Exception:
                symbols = set()
            if not symbols:
                try:
                    symbols = set(getattr(ccxt_client, 'symbols', []) or list(markets.keys()))
                except Exception:
                    symbols = set(markets.keys())
            sym_count = len(symbols)
            present = (symbol in symbols) or (symbol in markets)
            return present, mkt_count, sym_count
        except Exception:
            return False, 0, 0

    def _ccxt_pair_present(self, symbol: str, ex1: str, ex2: str) -> bool:
        """Ослабленная проверка присутствия пары - пропускаем если хотя бы одна биржа не загружена"""
        p1, m1, s1 = self._ccxt_presence(ex1, symbol)
        p2, m2, s2 = self._ccxt_presence(ex2, symbol)
        
        # Если markets не загружены (0), пропускаем проверку (считаем что пара есть)
        if m1 == 0 or m2 == 0:
            return True
            
        # Если symbols не загружены, пропускаем проверку    
        if s1 == 0 or s2 == 0:
            return True
            
        # Строгая проверка только если оба exchange полностью инициализированы
        return p1 and p2

    def _find_inter_exchange_pairs(self, symbol: str, exchanges_data: Dict) -> List[ArbitrageOpportunity]:
        """Исчерпывающий поиск межбиржевых пар (покупка->продажа) для символа.
        Возвращает список подходящих возможностей, отсортированный по ожидаемой прибыли."""
        opportunities: List[ArbitrageOpportunity] = []
        try:
            # Кандидаты на покупку (минимальная цена с учетом комиссии)
            buy_candidates = []  # (exchange, ask_price, ask_vol, eff_price, fee_pct)
            sell_candidates = []  # (exchange, bid_price, bid_vol, eff_price, fee_pct)
            for exchange, orderbook in exchanges_data.items():
                # Проверка свежести данных как в одиночной проверке
                allowed_age = TRADING_CONFIG['max_opportunity_age']
                ex_cfg = EXCHANGES_CONFIG.get(exchange, {})
                if ex_cfg.get('poll_rest'):
                    poll_interval = ex_cfg.get('poll_interval', 0)
                    allowed_age = max(allowed_age, poll_interval + 0.5)
                if not hasattr(orderbook, 'age') or orderbook.age > allowed_age:
                    continue
                fee_pct = EXCHANGES_CONFIG.get(exchange, {}).get('fee', 0) * 100
                if getattr(orderbook, 'best_ask', None):
                    try:
                        ask_vol = orderbook.get_depth_volume(1)['ask']
                    except Exception:
                        ask_vol = 0
                    eff_buy = orderbook.best_ask * (1 + fee_pct / 100)
                    buy_candidates.append((exchange, orderbook.best_ask, ask_vol, eff_buy, fee_pct))
                if getattr(orderbook, 'best_bid', None):
                    try:
                        bid_vol = orderbook.get_depth_volume(1)['bid']
                    except Exception:
                        bid_vol = 0
                    eff_sell = orderbook.best_bid * (1 - fee_pct / 100)
                    sell_candidates.append((exchange, orderbook.best_bid, bid_vol, eff_sell, fee_pct))

            if not buy_candidates or not sell_candidates:
                return opportunities

            # Сортировка и обрезка списков кандидатов
            buy_candidates.sort(key=lambda x: (x[3], x[4]))  # по эффективной цене покупки, затем по комиссии
            sell_candidates.sort(key=lambda x: (-x[3], x[4]))  # по эффективной цене продажи убыв., затем комиссия
            max_buys = TRADING_CONFIG.get('max_buy_candidates_per_symbol', 3)
            max_sells = TRADING_CONFIG.get('max_sell_candidates_per_symbol', 3)
            buy_candidates = buy_candidates[:max_buys]
            sell_candidates = sell_candidates[:max_sells]

            slippage_tol_pct = TRADING_CONFIG.get('slippage_tolerance', 0) * 100
            min_profit_pct = TRADING_CONFIG.get('min_profit_threshold', 0)
            cooldown = TRADING_CONFIG.get('pair_cooldown_seconds', 30)
            position_size = TRADING_CONFIG.get('position_size_usd', 100)

            # Перебор всех пар покупка->продажа
            for buy_ex, ask, ask_vol, _, buy_fee_pct in buy_candidates:
                for sell_ex, bid, bid_vol, _, sell_fee_pct in sell_candidates:
                    if buy_ex == sell_ex:
                        continue
                    if ask <= 0:
                        continue
                    # CCXT пред-фильтр: символ должен присутствовать на обеих биржах
                    try:
                        if not self._ccxt_pair_present(symbol, buy_ex, sell_ex):
                            continue
                    except Exception:
                        pass
                    spread_pct = (bid - ask) / ask * 100
                    total_fees = buy_fee_pct + sell_fee_pct
                    net_profit_pct = spread_pct - total_fees - slippage_tol_pct
                    if net_profit_pct < min_profit_pct:
                        continue
                    # Кулдаун
                    key = f"{symbol}_{buy_ex}_{sell_ex}"
                    now = time.time()
                    if key in self.opportunity_cooldowns and (now - self.opportunity_cooldowns[key]) < cooldown:
                        continue
                    # Объем и ожидаемая прибыль
                    min_volume_usd = min(bid_vol, ask_vol) * ask
                    expected_profit_usd = position_size * net_profit_pct / 100
                    opp = ArbitrageOpportunity(
                        type='inter_exchange',
                        path=[buy_ex, sell_ex],
                        exchanges=[buy_ex, sell_ex],
                        symbols=[symbol],
                        prices={
                            f'{buy_ex}_ask': ask,
                            f'{sell_ex}_bid': bid
                        },
                        volumes={
                            buy_ex: ask_vol,
                            sell_ex: bid_vol
                        },
                        expected_profit_pct=net_profit_pct,
                        expected_profit_usd=expected_profit_usd,
                        min_volume=min_volume_usd
                    )
                    opportunities.append(opp)

            # Сортировка возможностей по ожидаемой прибыли
            opportunities.sort(key=lambda o: o.expected_profit_pct, reverse=True)
            
            return opportunities
        except Exception as e:
            logger.error(f"Ошибка исчерпывающего поиска пар для {symbol}: {e}")
            return opportunities
    
    
    
    def _print_final_statistics(self):
        """Вывод финальной статистики"""
        runtime = (time.time() - self.statistics['start_time']) / 3600
        trading_stats = self.trading_engine.get_stats()
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        logger.info("=" * 60)
        logger.info(f"⏱️ Время работы: {runtime:.2f} часов")
        logger.info(f"🔍 Всего сканирований: {self.statistics['scans']}")
        logger.info(f"🧮 Кандидатов (до ликвидности): {self.statistics['candidates_detected']}")
        logger.info(f"💎 Найдено возможностей: {self.statistics['opportunities_found']}")
        logger.info(f"💼 Исполнено сделок: {self.statistics['trades_executed']}")
        logger.info(f"✅ Успешных сделок: {trading_stats.get('successful', 0)}")
        logger.info(f"❌ Неудачных сделок: {trading_stats.get('failed', 0)}")
        logger.info(f"📨 WebSocket сообщений: {self.statistics['ws_messages']}")
        logger.info(f"⚠️ Ошибок: {self.statistics['errors']}")
        logger.info(f"💰 Общая прибыль: ${trading_stats.get('total_profit_usd', 0):.2f}")
        logger.info(f"📊 Прибыль %: {trading_stats.get('total_profit_pct', 0):.3f}%")
        logger.info(f"📦 Общий объем: ${trading_stats.get('total_volume', 0):.2f}")
        # Разделы по биржам и по связкам
        if self.stats_by_exchange:
            logger.info("\n📈 Статистика по биржам:")
            for ex, s in sorted(self.stats_by_exchange.items(), key=lambda kv: kv[1]['trades'], reverse=True):
                avg_pct = (s['profit_pct_sum'] / s['successful']) if s['successful'] > 0 else 0.0
                logger.info(f"  • {ex}: возм={s['opportunities']}, сделки={s['trades']} (✅{s['successful']}/❌{s['failed']}), прибыль=${s['profit_usd']:.2f}, ср.%={avg_pct:.3f}%")
        if self.stats_by_pair:
            logger.info("\n🔗 Статистика по связкам:")
            for pair, s in sorted(self.stats_by_pair.items(), key=lambda kv: kv[1]['trades'], reverse=True):
                avg_pct = (s['profit_pct_sum'] / s['successful']) if s['successful'] > 0 else 0.0
                logger.info(f"  • {pair}: возм={s['opportunities']}, сделки={s['trades']} (✅{s['successful']}/❌{s['failed']}), прибыль=${s['profit_usd']:.2f}, ср.%={avg_pct:.3f}%")
        logger.info("=" * 60)

async def main():
    """Главная функция"""
    bot = ProductionArbitrageBot()
    
    # Обработка сигналов остановки
    def signal_handler(sig, frame):
        logger.info("\n⚠️ Получен сигнал остановки...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Запуск бота
    await bot.start()

if __name__ == "__main__":
    # Запуск
    asyncio.run(main())
