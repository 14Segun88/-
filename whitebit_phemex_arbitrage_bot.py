#!/usr/bin/env python3
"""
🚀 WHITEBIT-PHEMEX АРБИТРАЖНЫЙ БОТ
Реальный арбитраж между WhiteBit и Phemex (режимы берутся из конфигурации)
"""

import asyncio
import aiohttp
import time
import json
import hashlib
import hmac
import logging
import csv
import argparse
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN
import ccxt.async_support as ccxt
import os
import sys

# Импортируем нашу конфигурацию
try:
    from config_whitebit_phemex import (
        API_KEYS, EXCHANGES_CONFIG, TRADING_PAIRS, TRADING_CONFIG,
        RISK_MANAGEMENT, LOGGING_CONFIG, DYNAMIC_PAIRS_CONFIG, validate_config
    )
except Exception:
    try:
        from production_whitebit_phemex_config import (
            API_KEYS, EXCHANGES_CONFIG, TRADING_PAIRS, TRADING_CONFIG,
            RISK_MANAGEMENT, LOGGING_CONFIG, DYNAMIC_PAIRS_CONFIG, validate_config
        )
    except Exception:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)
        from config_whitebit_phemex import (
            API_KEYS, EXCHANGES_CONFIG, TRADING_PAIRS, TRADING_CONFIG,
            RISK_MANAGEMENT, LOGGING_CONFIG, DYNAMIC_PAIRS_CONFIG, validate_config
        )

# Настройка логирования (не конфигурируем root при импорте; конфигурация — в раннере)
logger = logging.getLogger('WhiteBitPhemexBot')
if not logger.handlers:
    logger.setLevel(LOGGING_CONFIG['level'])

class WhiteBitPhemexArbitrageBot:
    """Арбитражный бот для торговли между WhiteBit и Phemex"""
    
    def __init__(self):
        self.session = None
        self.whitebit_client = None
        self.phemex_client = None
        self.running = False
        self.prices = {}  # Кэш цен
        self.last_prices_update = {}
        self.opportunities_count = 0
        self.trades_count = 0
        self.total_profit = 0.0
        self.cooldowns = {}  # Кулдауны по парам
        self.whitebit_quote_currency = 'USDT'  # По умолчанию, может переключиться на DUSDT
        self.whitebit_symbols = set()  # Доступные символы на WhiteBit
        self.phemex_symbols = set()    # Доступные символы на Phemex
        self.active_pairs: List[str] = []  # Динамически отобранные пары (пересечение рынков)
        self.last_pairs_refresh: float = 0.0
        
        # Создаем CSV файлы для логирования
        self.init_csv_files()
        
    def init_csv_files(self):
        """Инициализация CSV файлов для логирования"""
        # Файл для сделок
        with open(LOGGING_CONFIG['trades_file'], 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'pair', 'direction', 'buy_exchange', 'sell_exchange',
                'buy_price', 'sell_price', 'quantity', 'profit_usd', 'profit_pct',
                'status', 'buy_order_id', 'sell_order_id'
            ])
            
        # Файл для возможностей
        with open(LOGGING_CONFIG['opportunities_file'], 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp', 'pair', 'whitebit_price', 'phemex_price', 
                'spread_pct', 'profit_after_fees', 'action_taken'
            ])
    
    async def start(self):
        """Запуск бота"""
        logger.info("🚀 Запуск WhiteBit-Phemex арбитражного бота...")
        
        # Валидация конфигурации
        errors, warnings = validate_config()
        if errors:
            for error in errors:
                logger.error(error)
            raise Exception("Критические ошибки в конфигурации")
            
        for warning in warnings:
            logger.warning(warning)
        
        # Создание HTTP сессии
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Инициализация клиентов бирж
        await self.init_exchanges()
        
        # Проверка подключений
        await self.test_connections()
        
        # Основной цикл торговли
        self.running = True
        logger.info("✅ Бот запущен и начинает поиск арбитражных возможностей")
        
        try:
            while self.running:
                await self.arbitrage_cycle()
                await asyncio.sleep(TRADING_CONFIG['scan_interval'])
        except KeyboardInterrupt:
            logger.info("⏹️ Получен сигнал остановки...")
        finally:
            await self.stop()
    
    async def init_exchanges(self):
        """Инициализация клиентов бирж"""
        logger.info("🔗 Инициализация подключений к биржам...")
        
        # WhiteBit через ccxt
        wb_config = API_KEYS['whitebit']
        self.whitebit_client = ccxt.whitebit({
            'apiKey': wb_config['apiKey'],
            'secret': wb_config['secret'],
            'sandbox': False,  # Demo режим, но не sandbox
            'enableRateLimit': True
        })
        
        # Phemex через ccxt (режим из конфигурации)
        ph_config = API_KEYS['phemex']
        ph_ex_cfg = EXCHANGES_CONFIG.get('phemex', {})
        ph_testnet = bool(ph_config.get('testnet_mode', ph_ex_cfg.get('testnet_mode', False)))
        ph_kwargs = {
            'apiKey': ph_config['apiKey'],
            'secret': ph_config['secret'],
            'sandbox': ph_testnet,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'  # ВАЖНО: используем спот рынки
            }
        }
        if ph_testnet:
            # Явно указываем testnet URLs
            test_urls = (ph_config.get('testnet_urls') or {
                'api': 'https://testnet-api.phemex.com',
                'public': 'https://testnet-api.phemex.com',
                'private': 'https://testnet-api.phemex.com'
            })
            ph_kwargs['urls'] = {
                'api': test_urls.get('api', 'https://testnet-api.phemex.com'),
                'public': test_urls.get('public', 'https://testnet-api.phemex.com'),
                'private': test_urls.get('private', 'https://testnet-api.phemex.com')
            }
        # Создаём клиента Phemex
        self.phemex_client = ccxt.phemex(ph_kwargs)
        # Включаем/выключаем sandbox в соответствии с конфигом
        try:
            self.phemex_client.set_sandbox_mode(ph_testnet)
        except Exception:
            pass
        try:
            await self.whitebit_client.load_markets()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить рынки WhiteBit: {e}")
        try:
            await self.phemex_client.load_markets()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить рынки Phemex: {e}")
        
        logger.info("✅ Клиенты бирж инициализированы")
        # Сохраняем список доступных символов WhiteBit
        try:
            self.whitebit_symbols = set(self.whitebit_client.symbols or [])
        except Exception:
            self.whitebit_symbols = set()
        # Список доступных символов Phemex
        try:
            self.phemex_symbols = set(self.phemex_client.symbols or [])
        except Exception:
            self.phemex_symbols = set()
    
    async def test_connections(self):
        """Тестирование подключений к биржам"""
        logger.info("🧪 Тестирование подключений...")
        
        # Тест WhiteBit
        try:
            wb_balance = await self.whitebit_client.fetch_balance()
            wb_free_map = (wb_balance.get('free', {}) or {})
            wb_free_usdt = wb_free_map.get('USDT', 0)
            wb_free_dusdt = wb_free_map.get('DUSDT', 0)
            if wb_free_usdt and float(wb_free_usdt) > 0:
                logger.info(f"✅ WhiteBit подключен. Свободно: {wb_free_usdt} USDT")
                self.whitebit_quote_currency = 'USDT'
            else:
                logger.info(f"✅ WhiteBit подключен. Свободно (демо): {wb_free_dusdt} DUSDT")
                self.whitebit_quote_currency = 'DUSDT'
        except Exception:
            logger.exception("❌ Ошибка подключения к WhiteBit")
            raise
        
        # Тест Phemex
        try:
            ph_balance = await self.phemex_client.fetch_balance()
            ph_free = (ph_balance.get('free', {}) or {})
            logger.info(f"✅ Phemex подключен. Свободно: {ph_free.get('BTC', 0)} BTC, {ph_free.get('USDT', 0)} USDT")
        except Exception:
            logger.exception("❌ Ошибка подключения к Phemex")
            raise
        
        # После успешных проверок — сформируем активные пары
        await self.refresh_active_pairs(force=True)

    async def refresh_active_pairs(self, force: bool = False):
        """Переопределяет self.active_pairs пересечением рынков WB и Phemex.
        Использует TRADING_PAIRS + priority из DYNAMIC_PAIRS_CONFIG. Ограничивает max_pairs.
        """
        now = time.time()
        interval = max(60, int(DYNAMIC_PAIRS_CONFIG.get('update_interval', 1800)))
        if not force and (now - self.last_pairs_refresh) < interval and self.active_pairs:
            return

        wb_syms = self.whitebit_symbols
        ph_syms = self.phemex_symbols
        if not wb_syms or not ph_syms:
            try:
                wb_syms = set(self.whitebit_client.symbols or [])
                ph_syms = set(self.phemex_client.symbols or [])
            except Exception:
                pass

        # Кандидаты: из конфига + приоритетные
        seed = list(dict.fromkeys(list(TRADING_PAIRS) + list(DYNAMIC_PAIRS_CONFIG.get('priority_pairs', []))))

        selected: List[str] = []
        for pair in seed:
            # Должен существовать на Phemex как канонический (e.g. BTC/USDT)
            if pair not in ph_syms:
                continue
            # Должен резолвиться на WhiteBit с учетом DUSDT/DBTC
            if self._whitebit_symbol(pair):
                selected.append(pair)
            if len(selected) >= int(DYNAMIC_PAIRS_CONFIG.get('max_pairs', 50)):
                break

        # Фоллбек — хотя бы BTC/USDT, если ничего не найдено
        if not selected and 'BTC/USDT' in ph_syms and self._whitebit_symbol('BTC/USDT'):
            selected = ['BTC/USDT']

        self.active_pairs = selected
        self.last_pairs_refresh = now
        logger.info(f"🎯 Активные пары ({len(self.active_pairs)}): {', '.join(self.active_pairs) if self.active_pairs else '—'}")
    
    async def fetch_prices(self) -> Dict[str, Dict[str, float]]:
        """Получение цен с обеих бирж"""
        prices = {}
        
        # Обновим список активных пар периодически
        await self.refresh_active_pairs(force=False)
        pairs = self.active_pairs or TRADING_PAIRS
        for pair in pairs:
            try:
                # WhiteBit (учитываем USDT/DUSDT)
                wb_symbol = self._whitebit_symbol(pair)
                if not wb_symbol:
                    # Эта пара недоступна на WhiteBit в текущей котируемой валюте
                    raise ValueError(f"Нет доступного рынка для {pair} на WhiteBit")
                wb_ticker = await self.whitebit_client.fetch_ticker(wb_symbol)
                wb_price = {
                    'bid': float(wb_ticker['bid']) if wb_ticker['bid'] else 0,
                    'ask': float(wb_ticker['ask']) if wb_ticker['ask'] else 0,
                    'timestamp': time.time()
                }
                
                # Phemex
                ph_price = {'bid': 0.0, 'ask': 0.0, 'timestamp': time.time()}
                try:
                    ph_ticker = await self.phemex_client.fetch_ticker(pair)
                    if isinstance(ph_ticker, dict):
                        ph_price['bid'] = float(ph_ticker.get('bid') or 0)
                        ph_price['ask'] = float(ph_ticker.get('ask') or 0)
                except Exception as e:
                    logger.warning(f"⚠️ CCXT Phemex fetch_ticker ошибка для {pair}: {e}")
                # Фоллбек на прямой REST, если bid/ask пустые
                if ph_price['bid'] <= 0 or ph_price['ask'] <= 0:
                    rest_price = await self._fetch_phemex_bidask_rest(pair)
                    if rest_price:
                        ph_price.update(rest_price)
                
                if wb_price['bid'] > 0 and wb_price['ask'] > 0 and ph_price['bid'] > 0 and ph_price['ask'] > 0:
                    prices[pair] = {
                        'whitebit': wb_price,
                        'phemex': ph_price
                    }
                    
            except Exception as e:
                logger.warning(f"⚠️ Ошибка получения цены {pair}: {e}")
                continue
        
        self.prices = prices
        return prices

    def _whitebit_symbol(self, canonical_pair: str) -> Optional[str]:
        """Возвращает символ для WhiteBit с учётом USDT/DUSDT и реального наличия рынка.
        Возвращает None, если подходящий символ не найден на WhiteBit.
        """
        try:
            base, quote = canonical_pair.split('/')
        except Exception:
            return None
        if not self.whitebit_symbols:
            # Если по какой-то причине список не загружен — используем простое правило
            return canonical_pair.replace('/USDT', '/DUSDT') if self.whitebit_quote_currency == 'DUSDT' else canonical_pair
        candidates = []
        if self.whitebit_quote_currency == 'DUSDT':
            # Приоритет демо-рынков с префиксом 'D'
            candidates = [
                f"D{base}/DUSDT",
                f"{base}/DUSDT",
                f"{base}/USDT",
            ]
        else:
            candidates = [
                f"{base}/USDT",
            ]
        for sym in candidates:
            if sym in self.whitebit_symbols:
                return sym
        return None

    async def _fetch_phemex_bidask_rest(self, pair: str) -> Optional[Dict[str, float]]:
        """Фоллбек: получить bid/ask с Phemex через прямой REST orderbook (URL из конфига)"""
        try:
            # Преобразуем символ в формат Phemex: BTC/USDT -> sBTCUSDT
            ph_symbol = 's' + pair.replace('/', '')
            # Выбираем базовый URL из конфигурации (mainnet/testnet)
            rest_base = (EXCHANGES_CONFIG.get('phemex', {}) or {}).get('rest_url', 'https://api.phemex.com')
            url = f"{rest_base.rstrip('/')}/md/orderbook?symbol={ph_symbol}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache'
            }
            scale = 100000000.0  # 10^8 — Phemex Ep масштаб для цены
            # До 3 попыток с небольшим бэкоффом
            for attempt in range(3):
                try:
                    async with self.session.get(url, headers=headers, timeout=10) as resp:
                        if resp.status != 200:
                            logger.debug(f"Phemex REST fallback HTTP {resp.status} для {pair} (попытка {attempt+1})")
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        data = await resp.json()
                        result = data.get('result', {}) or {}
                        book = result.get('book', {}) or {}
                        bids = book.get('bids', []) or []
                        asks = book.get('asks', []) or []
                        if not bids or not asks:
                            logger.debug(f"Phemex REST fallback пустой стакан для {pair} (попытка {attempt+1})")
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        def _num(x):
                            try:
                                return float(x)
                            except Exception:
                                return 0.0
                        # Значения в Ep: берём первый уровень [priceEp, qty]
                        bb_ep = _num(bids[0][0]) if isinstance(bids[0], (list, tuple)) else _num(bids[0])
                        ba_ep = _num(asks[0][0]) if isinstance(asks[0], (list, tuple)) else _num(asks[0])
                        if bb_ep <= 0 or ba_ep <= 0:
                            logger.debug(f"Phemex REST fallback нулевые цены для {pair} (попытка {attempt+1})")
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        best_bid = bb_ep / scale
                        best_ask = ba_ep / scale
                        if best_bid <= 0 or best_ask <= 0:
                            await asyncio.sleep(0.3 * (attempt + 1))
                            continue
                        logger.debug(f"Phemex REST fallback использован для {pair}: bid={best_bid}, ask={best_ask}")
                        return {'bid': best_bid, 'ask': best_ask, 'timestamp': time.time()}
                except Exception as ie:
                    logger.debug(f"Phemex REST fallback ошибка попытка {attempt+1} для {pair}: {ie}")
                    await asyncio.sleep(0.3 * (attempt + 1))
            return None
        except Exception as e:
            logger.warning(f"⚠️ Ошибка REST Phemex orderbook для {pair}: {e}")
            return None

    def calculate_arbitrage_opportunity(
        self,
        pair: str,
        prices: Dict[str, Dict[str, float]],
        ignore_threshold: bool = False,
        preferred_direction: Optional[str] = None,
    ) -> Optional[Dict]:
        """Расчёт наилучшей арбитражной возможности по паре."""
        wb_price = prices['whitebit']
        ph_price = prices['phemex']

        # Возможность 1: Купить на WhiteBit, продать на Phemex
        buy_wb_sell_ph = {
            'direction': 'WB→PH',
            'buy_exchange': 'whitebit',
            'sell_exchange': 'phemex',
            'buy_price': wb_price['ask'],  # Покупаем по ask
            'sell_price': ph_price['bid'],  # Продаем по bid
        }

        # Возможность 2: Купить на Phemex, продать на WhiteBit
        buy_ph_sell_wb = {
            'direction': 'PH→WB',
            'buy_exchange': 'phemex',
            'sell_exchange': 'whitebit',
            'buy_price': ph_price['ask'],
            'sell_price': wb_price['bid'],
        }

        opportunities = []
        evaluated = []

        for opp in [buy_wb_sell_ph, buy_ph_sell_wb]:
            if opp['buy_price'] > 0 and opp['sell_price'] > 0:
                # Расчёт спреда
                spread_pct = ((opp['sell_price'] - opp['buy_price']) / opp['buy_price']) * 100

                # Учет комиссий
                total_fees = EXCHANGES_CONFIG['whitebit']['fee'] + EXCHANGES_CONFIG['phemex']['fee']
                total_fees_pct = total_fees * 100

                # Чистая прибыль
                net_profit_pct = spread_pct - total_fees_pct

                opp.update({
                    'pair': pair,
                    'spread_pct': spread_pct,
                    'total_fees_pct': total_fees_pct,
                    'net_profit_pct': net_profit_pct,
                    'timestamp': time.time(),
                })
                evaluated.append(opp)

                if not ignore_threshold:
                    if net_profit_pct >= TRADING_CONFIG['min_profit_threshold']:
                        opportunities.append(opp)

        # Возврат результата
        if ignore_threshold:
            if not evaluated:
                return None
            if preferred_direction:
                for o in evaluated:
                    if o['direction'] == preferred_direction:
                        return o
            return max(evaluated, key=lambda x: x['net_profit_pct'])
        else:
            if opportunities:
                return max(opportunities, key=lambda x: x['net_profit_pct'])
            return None
    
    def is_pair_on_cooldown(self, pair: str) -> bool:
        """Проверка, находится ли пара в кулдауне"""
        if pair in self.cooldowns:
            time_passed = time.time() - self.cooldowns[pair]
            if time_passed < TRADING_CONFIG['pair_cooldown_seconds']:
                return True
            else:
                del self.cooldowns[pair]
        return False
    
    def set_pair_cooldown(self, pair: str):
        """Установка кулдауна для пары"""
        self.cooldowns[pair] = time.time()
    
    async def _precheck_sell_inventory(self, opportunity: Dict, pair: str) -> Tuple[bool, float]:
        """Быстрая проверка наличия базового актива на стороне продажи.
        Возвращает (ok, sell_free_base)."""
        try:
            sell_client = self.phemex_client if opportunity['sell_exchange'] == 'phemex' else self.whitebit_client
            sell_symbol = self._whitebit_symbol(pair) if opportunity['sell_exchange'] == 'whitebit' else pair
            if opportunity['sell_exchange'] == 'whitebit' and not sell_symbol:
                return False, 0.0
            sell_base = sell_symbol.split('/')[0] if '/' in sell_symbol else pair.split('/')[0]
            sell_bal = await sell_client.fetch_balance()
            sell_free_map = (sell_bal.get('free', {}) or {})
            sell_free_base = float(sell_free_map.get(sell_base, 0) or 0)
            return (sell_free_base > 0), sell_free_base
        except Exception:
            return False, 0.0
    
    async def execute_arbitrage(self, opportunity: Dict) -> bool:
        """Исполнение арбитражной сделки"""
        pair = opportunity['pair']
        position_size_usd = TRADING_CONFIG['position_size_usd']
        
        logger.info(f"📈 Исполняю арбитраж {opportunity['direction']} {pair}: "
                   f"прибыль {opportunity['net_profit_pct']:.3f}%")
        
        try:
            # Определяем клиентов
            buy_client = self.whitebit_client if opportunity['buy_exchange'] == 'whitebit' else self.phemex_client
            sell_client = self.phemex_client if opportunity['sell_exchange'] == 'phemex' else self.whitebit_client
            # Определяем символы ордеров (WhiteBit может требовать DUSDT)
            buy_symbol = self._whitebit_symbol(pair) if opportunity['buy_exchange'] == 'whitebit' else pair
            sell_symbol = self._whitebit_symbol(pair) if opportunity['sell_exchange'] == 'whitebit' else pair
            if opportunity['buy_exchange'] == 'whitebit' and not buy_symbol:
                logger.error("❌ Невозможно купить на WhiteBit: подходящий рынок не найден")
                return False
            if opportunity['sell_exchange'] == 'whitebit' and not sell_symbol:
                logger.error("❌ Невозможно продать на WhiteBit: подходящий рынок не найден")
                return False
            
            # Динамически подгоняем размер позиции под доступные балансы
            buy_quote = buy_symbol.split('/')[-1] if '/' in buy_symbol else (
                self.whitebit_quote_currency if opportunity['buy_exchange'] == 'whitebit' else 'USDT'
            )
            sell_base = sell_symbol.split('/')[0] if '/' in sell_symbol else pair.split('/')[0]

            # Баланс покупающей биржи (котируемая валюта)
            try:
                buy_bal = await buy_client.fetch_balance()
                buy_free_map = (buy_bal.get('free', {}) or {})
                buy_free_quote = float(buy_free_map.get(buy_quote, 0) or 0)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить баланс {opportunity['buy_exchange']}: {e}")
                buy_free_quote = 0.0

            position_size = min(position_size_usd, buy_free_quote * 0.98)
            if position_size < 5:
                logger.warning(
                    f"⚠️ Недостаточно средств на {opportunity['buy_exchange']} ({buy_quote}={buy_free_quote}) для позиции ${position_size_usd}; пропуск"
                )
                return False

            # Рассчитываем предварительное количество для торговли (по покупающей стороне)
            prelim_qty = position_size / opportunity['buy_price']

            # Проверяем/ограничиваем по наличию базового актива на стороне продажи (спот)
            try:
                sell_bal = await sell_client.fetch_balance()
                sell_free_map = (sell_bal.get('free', {}) or {})
                sell_free_base = float(sell_free_map.get(sell_base, 0) or 0)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить баланс {opportunity['sell_exchange']}: {e}")
                sell_free_base = 0.0

            max_qty_sell = sell_free_base * 0.98
            if max_qty_sell <= 0:
                logger.warning(
                    f"⚠️ Недостаточно {sell_base} на {opportunity['sell_exchange']} для продажи. Доступно: {sell_free_base} — ставлю короткий кулдаун"
                )
                # Короткий кулдаун, чтобы не спамить попытками по этой паре
                self.set_pair_cooldown(pair)
                return False

            quantity = min(prelim_qty, max_qty_sell)

            # Округляем количество до допустимой точности
            if pair == 'BTC/USDT':
                quantity = round(quantity, 5)
            else:
                quantity = round(quantity, 3)
            if quantity <= 0:
                logger.warning("⚠️ Расчетное количество после ограничений <= 0; пропуск")
                self.set_pair_cooldown(pair)
                return False

            logger.info(f"💰 Размещаю ордера: количество {quantity}, размер позиции ${position_size}")
            
            # РЕАЛЬНЫЕ ОРДЕРА - НЕ СИМУЛЯЦИЯ!
            buy_order = None
            sell_order = None
            
            # Размещаем ордер на покупку
            try:
                buy_order = await buy_client.create_market_buy_order(buy_symbol, quantity)
                logger.info(f"✅ Ордер на покупку размещен: {buy_order['id']} на {opportunity['buy_exchange']}")
            except Exception as e:
                # WhiteBit иногда возвращает успешный FILLED-ордер внутри текста ошибки.
                handled = False
                if opportunity['buy_exchange'] == 'whitebit':
                    raw = str(e)
                    json_str = raw[raw.find('{'):] if '{' in raw else ''
                    parsed = None
                    if json_str:
                        try:
                            parsed = json.loads(json_str)
                        except Exception:
                            parsed = None
                    status = (parsed or {}).get('status') if isinstance(parsed, dict) else None
                    if isinstance(parsed, dict) and str(status).upper() == 'FILLED':
                        oid = str(parsed.get('orderId') or parsed.get('id') or '')
                        buy_order = {'id': oid or 'unknown'}
                        logger.warning("⚠️ WhiteBit сообщил FILLED внутри ошибки; продолжаю как успешную покупку")
                        handled = True
                if not handled:
                    logger.error(f"❌ Ошибка размещения ордера на покупку: {e}")
                    return False
            
            # Размещаем ордер на продажу
            try:
                sell_order = await sell_client.create_market_sell_order(sell_symbol, quantity)
                logger.info(f"✅ Ордер на продажу размещен: {sell_order['id']} на {opportunity['sell_exchange']}")
            except Exception as e:
                handled = False
                if opportunity['sell_exchange'] == 'whitebit':
                    raw = str(e)
                    json_str = raw[raw.find('{'):] if '{' in raw else ''
                    parsed = None
                    if json_str:
                        try:
                            parsed = json.loads(json_str)
                        except Exception:
                            parsed = None
                    status = (parsed or {}).get('status') if isinstance(parsed, dict) else None
                    if isinstance(parsed, dict) and str(status).upper() == 'FILLED':
                        oid = str(parsed.get('orderId') or parsed.get('id') or '')
                        sell_order = {'id': oid or 'unknown'}
                        logger.warning("⚠️ WhiteBit сообщил FILLED внутри ошибки; продолжаю как успешную продажу")
                        handled = True
                if not handled:
                    logger.error(f"❌ Ошибка размещения ордера на продажу: {e}")
                    # Попытка отменить ордер на покупку если продажа не удалась
                    if buy_order:
                        try:
                            oid = str(buy_order.get('id') or '') if isinstance(buy_order, dict) else ''
                            if oid and oid.lower() != 'unknown':
                                sym = buy_symbol or pair
                                await buy_client.cancel_order(oid, sym)
                                logger.warning(f"⚠️ Ордер на покупку отменен из-за ошибки продажи (id={oid}, symbol={sym})")
                            else:
                                logger.warning("⚠️ Неизвестный ID buy-ордера — пропускаю отмену")
                        except Exception as ce:
                            logger.warning(f"⚠️ Не удалось отменить ордер на покупку: {ce}")
                    return False
            
            # Логирование успешной сделки
            profit_usd = position_size * (opportunity['net_profit_pct'] / 100)
            self.total_profit += profit_usd
            self.trades_count += 1
            
            # Запись в CSV
            with open(LOGGING_CONFIG['trades_file'], 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    pair,
                    opportunity['direction'],
                    opportunity['buy_exchange'],
                    opportunity['sell_exchange'],
                    opportunity['buy_price'],
                    opportunity['sell_price'],
                    quantity,
                    profit_usd,
                    opportunity['net_profit_pct'],
                    'EXECUTED',
                    buy_order['id'] if buy_order else '',
                    sell_order['id'] if sell_order else ''
                ])
            
            logger.info(f"💸 Сделка выполнена! Прибыль: ${profit_usd:.2f} ({opportunity['net_profit_pct']:.3f}%)")
            logger.info(f"📊 Всего сделок: {self.trades_count}, общая прибыль: ${self.total_profit:.2f}")
            
            return True
            
        except Exception:
            logger.exception("❌ Ошибка исполнения арбитража")
            return False
    
    async def arbitrage_cycle(self):
        """Один цикл поиска и исполнения арбитража"""
        try:
            # Получаем цены
            prices = await self.fetch_prices()
            if not prices:
                logger.debug("Нет доступных цен для расчёта.")
                return
            
            # Параметры форс-режима
            force_mode = bool(TRADING_CONFIG.get('force_execute_any'))
            force_once = bool(TRADING_CONFIG.get('force_execute_once'))
            force_pair = TRADING_CONFIG.get('force_pair')
            force_dir = TRADING_CONFIG.get('force_direction')
            
            # Выбор целевых пар
            target_pairs = self.active_pairs or TRADING_PAIRS
            if force_mode and force_pair and (force_pair in prices):
                target_pairs = [force_pair]
            
            executed = False
            
            for pair in target_pairs:
                if pair not in prices:
                    continue
                if not force_mode and self.is_pair_on_cooldown(pair):
                    continue
                
                opp = self.calculate_arbitrage_opportunity(
                    pair,
                    prices[pair],
                    ignore_threshold=force_mode,
                    preferred_direction=force_dir if force_mode else None,
                )
                
                # Обработка возможности и логирование
                if opp:
                    # Значения для логов
                    if opp['direction'] == 'WB→PH':
                        wb_logged = prices[pair]['whitebit']['ask']
                        ph_logged = prices[pair]['phemex']['bid']
                    else:  # PH→WB
                        wb_logged = prices[pair]['whitebit']['bid']
                        ph_logged = prices[pair]['phemex']['ask']

                    # Фильтр аномального спреда (тестнет дисбалансы)
                    max_spread = float(TRADING_CONFIG.get('max_reasonable_spread_pct', 50.0))
                    if not force_mode and opp['spread_pct'] > max_spread:
                        with open(LOGGING_CONFIG['opportunities_file'], 'a', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                datetime.now().isoformat(),
                                pair,
                                wb_logged,
                                ph_logged,
                                opp['spread_pct'],
                                opp['net_profit_pct'],
                                'SKIP_SPREAD'
                            ])
                        self.opportunities_count += 1
                        continue

                    # Предварительная проверка инвентаря на стороне продажи
                    ok_inventory, sell_free_base = await self._precheck_sell_inventory(opp, pair)
                    if not ok_inventory:
                        with open(LOGGING_CONFIG['opportunities_file'], 'a', newline='') as f:
                            writer = csv.writer(f)
                            writer.writerow([
                                datetime.now().isoformat(),
                                pair,
                                wb_logged,
                                ph_logged,
                                opp['spread_pct'],
                                opp['net_profit_pct'],
                                'SKIP_NO_SELL_BASE'
                            ])
                        self.opportunities_count += 1
                        self.set_pair_cooldown(pair)
                        continue

                    will_execute = (force_mode or opp['net_profit_pct'] >= TRADING_CONFIG['min_profit_threshold'])
                    with open(LOGGING_CONFIG['opportunities_file'], 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            datetime.now().isoformat(),
                            pair,
                            wb_logged,
                            ph_logged,
                            opp['spread_pct'],
                            opp['net_profit_pct'],
                            'EXECUTE' if will_execute else 'SKIP'
                        ])
                    self.opportunities_count += 1

                    if will_execute:
                        executed = await self.execute_arbitrage(opp)
                        if executed:
                            self.set_pair_cooldown(pair)
                            break
                else:
                    # Нет валидной возможности — продолжаем искать
                    continue
            
            # Если форс одноразовый — отключаем его после успешной сделки
            if executed and force_mode and force_once:
                TRADING_CONFIG['force_execute_any'] = False
                logger.info("🧪 Форс-режим был одноразовым — отключаю его.")
                # Завершаем работу после одной форс-сделки
                self.running = False
                logger.info("⏹️ Останавливаю бота после одноразовой форс-сделки.")
        
        except Exception:
            logger.exception("⚠️ Ошибка в цикле арбитража")
    
    async def stop(self):
        """Остановка бота и освобождение ресурсов"""
        try:
            self.running = False
            
            if self.whitebit_client:
                await self.whitebit_client.close()
                self.whitebit_client = None
            if self.phemex_client:
                await self.phemex_client.close()
                self.phemex_client = None
            if self.session:
                await self.session.close()
                self.session = None
            
            logger.info("📊 Финальная статистика:")
            logger.info(f"   Возможностей найдено: {self.opportunities_count}")
            logger.info(f"   Сделок выполнено: {self.trades_count}")
            logger.info(f"   Общая прибыль: ${self.total_profit:.2f}")
            logger.info("✅ Бот остановлен")
        
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при остановке бота: {e}")

async def run_bot(config_overrides: Optional[dict] = None):
    """Импорт-безопасный запуск бота.
    Принимает необязательные переопределения параметров TRADING_CONFIG.
    """
    # Применяем переопределения конфигурации, если переданы
    if config_overrides:
        try:
            TRADING_CONFIG.update({k: v for k, v in config_overrides.items() if v is not None})
        except Exception:
            pass

    # Сообщение о форс-режиме (если активирован)
    if TRADING_CONFIG.get('force_execute_any'):
        logger.warning(
            f"🧪 Включен форс-режим: pair={TRADING_CONFIG.get('force_pair')}, "
            f"dir={TRADING_CONFIG.get('force_direction')}, size=${TRADING_CONFIG.get('position_size_usd')}"
        )

    bot = WhiteBitPhemexArbitrageBot()
    try:
        await bot.start()
    except asyncio.CancelledError:
        logger.info("⏹️ Получен сигнал отмены (CancelledError). Останавливаю бота...")
        await bot.stop()
    except KeyboardInterrupt:
        logger.info("⏹️ KeyboardInterrupt: остановка по запросу пользователя.")
        await bot.stop()
    except Exception:
        logger.exception("💥 Критическая ошибка")
        await bot.stop()

async def main():
    """Главная функция"""
    # CLI аргументы
    parser = argparse.ArgumentParser(description='WhiteBit-Phemex Arbitrage Bot')
    parser.add_argument('--force-execute', action='store_true', help='Принудительно выполнить сделку даже при отрицательной прибыли')
    parser.add_argument('--force-once', action='store_true', help='Выполнить принудительно только один раз, затем вернуться в обычный режим')
    parser.add_argument('--force-direction', type=str, choices=['WB→PH', 'PH→WB'], help='Направление форс-сделки')
    parser.add_argument('--force-pair', type=str, help='Пара для форс-сделки (например, BTC/USDT)')
    parser.add_argument('--size', type=float, help='Размер позиции в USDT (перекрывает конфиг)')
    parser.add_argument('--min-profit', type=float, help='Минимальная прибыль (%%) для обычного режима')
    args = parser.parse_args()

    # Формируем переопределения из аргументов CLI
    overrides = {}
    if args.size is not None:
        overrides['position_size_usd'] = float(args.size)
    if args.min_profit is not None:
        overrides['min_profit_threshold'] = float(args.min_profit)
    overrides['force_execute_any'] = bool(args.force_execute)
    overrides['force_execute_once'] = bool(args.force_once)
    overrides['force_direction'] = args.force_direction
    overrides['force_pair'] = args.force_pair

    await run_bot(overrides)

if __name__ == "__main__":
    # Конфигурируем логирование для автономного запуска: выводим и в файл, и в терминал
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.setLevel(LOGGING_CONFIG['level'])
        formatter = logging.Formatter(LOGGING_CONFIG['format'], datefmt=LOGGING_CONFIG['date_format'])
        # FileHandler — сохраняем логи в файл
        fh = logging.FileHandler(LOGGING_CONFIG.get('file', 'whitebit_phemex_bot.log'))
        fh.setFormatter(formatter)
        root_logger.addHandler(fh)
        # StreamHandler — показываем логи в терминале
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        root_logger.addHandler(sh)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
