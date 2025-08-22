#!/usr/bin/env python3
"""
🌐 WEBSOCKET MANAGER
Управление WebSocket соединениями для всех бирж
"""

import asyncio
import websockets
import json
import time
import logging
import aiohttp
import gzip
import random  # Добавляем модуль random для генерации случайных задержек
from typing import Dict, List, Optional, Callable, Any, Tuple, Union
from dataclasses import dataclass
from collections import defaultdict, deque
from urllib.parse import urlsplit, urlparse
from production_config import EXCHANGES_CONFIG, WEBSOCKET_CONFIG, PROXY_CONFIG, API_KEYS, TRADING_CONFIG
from symbol_utils import normalize_symbol

logger = logging.getLogger('WSManager')

@dataclass
class OrderBook:
    """Стакан ордеров"""
    symbol: str
    exchange: str
    bids: List[tuple]  # [(price, volume), ...]
    asks: List[tuple]
    timestamp: float
    
    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None
    
    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None
    
    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return (self.best_ask - self.best_bid) / self.best_bid * 100
        return None
    
    @property
    def age(self) -> float:
        """Возраст данных в секундах"""
        return time.time() - self.timestamp
    
    def get_depth_volume(self, levels: int = 5) -> Dict[str, float]:
        """Получить объем на глубине"""
        bid_vol = sum(v for _, v in self.bids[:levels])
        ask_vol = sum(v for _, v in self.asks[:levels])
        return {'bid': bid_vol, 'ask': ask_vol}

class WebSocketManager:
    """Менеджер WebSocket соединений"""
    
    def __init__(self, on_orderbook_update: Optional[Callable] = None, on_ticker_update: Optional[Callable] = None):
        self.connections = {}
        self.subscriptions = defaultdict(set)
        self.reconnect_delays = defaultdict(lambda: WEBSOCKET_CONFIG['reconnect_delay'])
        self.running = False
        self.on_orderbook_update = on_orderbook_update
        self.on_ticker_update = on_ticker_update
        self.last_ping = defaultdict(float)
        self.message_counts = defaultdict(int)  # Счетчик сообщений для каждой биржи
        self.error_counts = defaultdict(int)    # Счетчик ошибок для каждой биржи
        self.orderbooks = {}  # Кэш ордербуков
        self.last_update_time = defaultdict(float)  # Время последнего обновления для каждого символа
        self.message_queue = asyncio.Queue()  # Очередь сообщений для обработки
        
        # Список активных бирж
        self.exchanges = [ex for ex, conf in EXCHANGES_CONFIG.items() if conf.get('enabled', False)]
        logger.info(f"ИНИЦИАЛИЗАЦИЯ: Найдено {len(self.exchanges)} активных бирж: {self.exchanges}")
        
        # Инициализируем счетчики для всех активных бирж
        for ex in self.exchanges:
            self.message_counts[ex] = 0
            self.error_counts[ex] = 0
            self.last_ping[ex] = 0
        
        # Проверяем каждую биржу отдельно
        for ex, conf in EXCHANGES_CONFIG.items():
            enabled = conf.get('enabled', False)
            logger.info(f"   {ex}: enabled={enabled}, websocket={conf.get('websocket', False)}")
        
    async def start(self, symbols: List[str]):
        """Запуск WebSocket соединений"""
        self.running = True
        self.symbols = symbols
        self.use_websocket = TRADING_CONFIG.get('use_websocket', True)
        logger.info(f"Инициализация каналов данных для {len(symbols)} символов | WebSocket={self.use_websocket}")
        
        # Инициализируем счетчики для всех активных бирж (во избежание KeyError при ранних инкрементах)
        for ex in self.exchanges:
            if ex not in self.message_counts:
                self.message_counts[ex] = 0
            if ex not in self.error_counts:
                self.error_counts[ex] = 0
        if self.use_websocket:
            # Запуск подключений для активных бирж (учитываем per-exchange флаг websocket)
            tasks = []
            logger.info(f"АКТИВНЫЕ БИРЖИ (WS): {self.exchanges}")
            
            for exchange in self.exchanges:
                if not EXCHANGES_CONFIG.get(exchange, {}).get('websocket', False):
                    logger.info(f"Пропуск WS для {exchange}: websocket=false")
                    continue
                logger.info(f"ПЫТАЕМСЯ ЗАПУСТИТЬ WS: {exchange}")
                if exchange == 'mexc':
                    logger.info("Подключение к MEXC WebSocket...")
                    tasks.append(self._connect_mexc())
                    # Также запускаем REST API как backup
                    asyncio.create_task(self._poll_mexc_rest())
                elif exchange == 'bybit':
                    logger.info("ЗАПУСК BYBIT!")
                    tasks.append(self._connect_bybit())
                elif exchange == 'huobi':
                    logger.info("ЗАПУСК HUOBI!")
                    tasks.append(self._connect_huobi())
                elif exchange == 'binance':
                    logger.info("ЗАПУСК BINANCE!")
                    tasks.append(self._connect_binance())
                elif exchange == 'okx':
                    tasks.append(self._connect_okx())
                elif exchange == 'gate':
                    tasks.append(self._connect_gate())
                elif exchange == 'kucoin':
                    tasks.append(self._connect_kucoin())
                elif exchange == 'kraken':
                    tasks.append(self._connect_kraken())
                elif exchange == 'bitget':
                    tasks.append(self._connect_bitget())
                elif exchange == 'phemex':
                    tasks.append(self._connect_phemex())
            
            logger.info(f"ГОТОВИМСЯ ЗАПУСТИТЬ {len(tasks)} задач WebSocket")
            
            # Запускаем задачи с обработкой ошибок
            if tasks:
                for i, task in enumerate(tasks):
                    logger.info(f"ЗАПУСКАЕМ ЗАДАЧУ {i}: {task}")
                    try:
                        async_task = asyncio.create_task(task)
                        def handle_task_exception(task_obj):
                            try:
                                task_obj.result()
                            except Exception as e:
                                logger.error(f"WebSocket задача {i} завершилась с ошибкой: {e}")
                        async_task.add_done_callback(handle_task_exception)
                        logger.info(f"Задача {i} успешно создана")
                    except Exception as e:
                        logger.error(f"Ошибка создания задачи {i}: {e}")
            else:
                logger.warning("Нет WS задач к запуску (возможно, все отключены в конфиге)")
            
            # Дополнительно: запускаем REST-поллеры для бирж, у которых WS отключён, но poll_rest включен (например, Phemex)
            for ex in self.exchanges:
                ex_conf = EXCHANGES_CONFIG.get(ex, {})
                if ex_conf.get('poll_rest', False) and not ex_conf.get('websocket', False):
                    if ex == 'phemex':
                        logger.info("Запуск REST polling для Phemex (websocket=false)")
                        asyncio.create_task(self._poll_phemex_rest())
        else:
            # Режим REST polling (демо/ограниченная среда)
            logger.info("WebSocket отключен. Запуск REST polling задач...")
            targets = set(s.replace('/', '').upper() for s in self.symbols if 'USDT' in s)
            logger.info(f"REST poll targets (пример): {list(targets)[:5]} ... всего {len(targets)}")
            # Запускаем pollers ТОЛЬКО для включенных бирж с poll_rest=true
            ex_poll_targets = [ex for ex, conf in EXCHANGES_CONFIG.items() if conf.get('enabled', False) and conf.get('poll_rest', False)]
            logger.info(f"REST pollers для активных бирж: {ex_poll_targets}")
            # Инициализируем счетчики для всех REST-целей (во избежание KeyError)
            for ex in ex_poll_targets:
                if ex not in self.message_counts:
                    self.message_counts[ex] = 0
                if ex not in self.error_counts:
                    self.error_counts[ex] = 0
            # Стартуем соответствующие pollers
            if 'mexc' in ex_poll_targets:
                asyncio.create_task(self._poll_mexc_rest())
            if 'bybit' in ex_poll_targets:
                asyncio.create_task(self._poll_bybit_rest())
            if 'binance' in ex_poll_targets:
                asyncio.create_task(self._poll_binance_rest())
            if 'okx' in ex_poll_targets:
                asyncio.create_task(self._poll_okx_rest())
            if 'gate' in ex_poll_targets:
                asyncio.create_task(self._poll_gate_rest())
            if 'bitget' in ex_poll_targets:
                asyncio.create_task(self._poll_bitget_rest())
            if 'huobi' in ex_poll_targets:
                asyncio.create_task(self._poll_huobi_rest())
            if 'phemex' in ex_poll_targets:
                asyncio.create_task(self._poll_phemex_rest())
    
    async def _poll_mexc_rest(self):
        """Получение данных MEXC через REST API"""
        logger.info("Запуск REST API polling для MEXC")
        
        while self.running:
            try:
                async with aiohttp.ClientSession() as session:
                    # Получаем тикеры для всех активных символов
                    mexc_symbols = [s.replace('/', '') for s in self.symbols if 'USDT' in s]
                    
                    # MEXC API endpoint для тикеров
                    url = f"{EXCHANGES_CONFIG['mexc']['rest_url']}/api/v3/ticker/24hr"
                    
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            tickers = await resp.json()
                            
                            for ticker in tickers:
                                symbol = ticker.get('symbol', '')
                                if symbol in mexc_symbols:
                                    # Создаем OrderBook из тикера
                                    bid_price = float(ticker.get('bidPrice', 0))
                                    ask_price = float(ticker.get('askPrice', 0))
                                    
                                    if bid_price > 0 and ask_price > 0:
                                        # Форматируем символ обратно
                                        base = symbol[:-4]  # Убираем USDT
                                        formatted_symbol = normalize_symbol(f"{base}/USDT")
                                        
                                        orderbook = OrderBook(
                                            symbol=formatted_symbol,
                                            exchange='mexc',
                                            bids=[(bid_price, float(ticker.get('bidQty', 1)))],
                                            asks=[(ask_price, float(ticker.get('askQty', 1)))],
                                            timestamp=time.time()
                                        )
                                        
                                        # Сохраняем в локальный кэш
                                        if 'mexc' not in self.orderbooks:
                                            self.orderbooks['mexc'] = {}
                                        self.orderbooks['mexc'][formatted_symbol] = orderbook
                                        
                                        if self.on_orderbook_update:
                                            await self.on_orderbook_update(orderbook)
                            
                            # Убедимся, что счетчики MEXC инициализированы (REST-поток может стартовать раньше WS)
                            if 'mexc' not in self.message_counts:
                                self.message_counts['mexc'] = 0
                            if 'mexc' not in self.error_counts:
                                self.error_counts['mexc'] = 0
                            
                            self.message_counts['mexc'] += len(mexc_symbols)
                            logger.debug(f"Обновлено {len(mexc_symbols)} пар")
                
                # Пауза между запросами (учитываем rate limits)
                await asyncio.sleep(2)  # Обновляем каждые 2 секунды
                
            except Exception as e:
                logger.error(f"Ошибка MEXC REST API: {e}")
                await asyncio.sleep(5)
    
    # =====================
    # REST polling helpers
    # =====================
    async def _poll_bybit_rest(self):
        """Получение best bid/ask Bybit через REST (v5 tickers, SPOT)"""
        logger.info("Запуск REST API polling для Bybit")
        while self.running:
            try:
                url = f"{EXCHANGES_CONFIG['bybit']['rest_url']}/v5/market/tickers?category=spot"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                            items = (payload.get('result') or {}).get('list', [])
                            targets = set(s.replace('/', '').upper() for s in self.symbols if 'USDT' in s)
                            for it in items:
                                symbol = it.get('symbol', '')
                                if symbol not in targets:
                                    continue
                                bid = float(it.get('bid1Price') or it.get('bidPrice') or 0)  # разные ревизии
                                ask = float(it.get('ask1Price') or it.get('askPrice') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(f"{symbol[:-4]}/USDT")
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='bybit',
                                        bids=[(bid, float(it.get('bid1Size') or 1))],
                                        asks=[(ask, float(it.get('ask1Size') or 1))],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['bybit'] += len(items)
                await asyncio.sleep(EXCHANGES_CONFIG['bybit'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Bybit REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_binance_rest(self):
        """Получение best bid/ask Binance через REST (bookTicker)"""
        logger.info("Запуск REST API polling для Binance")
        while self.running:
            try:
                url = f"{EXCHANGES_CONFIG['binance']['rest_url']}/api/v3/ticker/bookTicker"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            targets = set(s.replace('/', '').upper() for s in self.symbols if 'USDT' in s)
                            for item in data:
                                symbol = item.get('symbol', '')
                                if symbol not in targets:
                                    continue
                                bid = float(item.get('bidPrice') or 0)
                                ask = float(item.get('askPrice') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(f"{symbol[:-4]}/USDT")
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='binance',
                                        bids=[(bid, float(item.get('bidQty') or 1))],
                                        asks=[(ask, float(item.get('askQty') or 1))],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['binance'] += len(data)
                await asyncio.sleep(EXCHANGES_CONFIG['binance'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Binance REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_okx_rest(self):
        """Получение best bid/ask OKX через REST (tickers SPOT)"""
        logger.info("Запуск REST API polling для OKX")
        while self.running:
            try:
                url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                            items = payload.get('data', [])
                            targets = set(s.replace('/', '').upper().replace('/', '') for s in self.symbols if 'USDT' in s)
                            for it in items:
                                inst_id = it.get('instId', '')  # e.g., BTC-USDT
                                flat = inst_id.replace('-', '')
                                if flat not in targets:
                                    continue
                                bid = float(it.get('bidPx') or 0)
                                ask = float(it.get('askPx') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(inst_id.replace('-', '/'))
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='okx',
                                        bids=[(bid, float(it.get('bidSz') or 1))],
                                        asks=[(ask, float(it.get('askSz') or 1))],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['okx'] += len(items)
                await asyncio.sleep(EXCHANGES_CONFIG['okx'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка OKX REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_gate_rest(self):
        """Получение best bid/ask Gate.io через REST (tickers)"""
        logger.info("Запуск REST API polling для Gate.io")
        while self.running:
            try:
                url = "https://api.gateio.ws/api/v4/spot/tickers"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            targets = set(s.replace('/', '_').upper() for s in self.symbols if 'USDT' in s)
                            for item in data:
                                cp = item.get('currency_pair', '')
                                if cp.upper() not in targets:
                                    continue
                                bid = float(item.get('highest_bid') or 0)
                                ask = float(item.get('lowest_ask') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(cp.replace('_', '/'))
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='gate',
                                        bids=[(bid, 1.0)],
                                        asks=[(ask, 1.0)],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['gate'] += len(data)
                await asyncio.sleep(EXCHANGES_CONFIG['gate'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Gate REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_bitget_rest(self):
        """Получение best bid/ask Bitget через REST (tickers)"""
        logger.info("Запуск REST API polling для Bitget")
        while self.running:
            try:
                url = "https://api.bitget.com/api/spot/v1/market/tickers"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                            items = payload.get('data', [])
                            targets = set(s.replace('/', '').upper() for s in self.symbols if 'USDT' in s)
                            for it in items:
                                symbol = it.get('symbol', '')  # e.g., BTCUSDT
                                if symbol not in targets:
                                    continue
                                bid = float(it.get('buyOne') or it.get('bestBid') or it.get('bidPr') or 0)
                                ask = float(it.get('sellOne') or it.get('bestAsk') or it.get('askPr') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(f"{symbol[:-4]}/USDT")
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='bitget',
                                        bids=[(bid, float(it.get('bidSz') or 1))],
                                        asks=[(ask, float(it.get('askSz') or 1))],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['bitget'] += len(items)
                await asyncio.sleep(EXCHANGES_CONFIG['bitget'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Bitget REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_huobi_rest(self):
        """Получение best bid/ask Huobi (HTX) через REST (market/tickers)"""
        logger.info("Запуск REST API polling для Huobi")
        while self.running:
            try:
                url = f"{EXCHANGES_CONFIG['huobi']['rest_url']}/market/tickers"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                            items = payload.get('data', [])
                            targets = set(s.replace('/', '').lower() for s in self.symbols if 'USDT' in s)
                            for it in items:
                                sym = it.get('symbol', '')  # e.g., btcusdt
                                if sym not in targets:
                                    continue
                                bid = float(it.get('bid') or 0)
                                ask = float(it.get('ask') or 0)
                                if bid > 0 and ask > 0:
                                    formatted = normalize_symbol(f"{sym[:-4].upper()}/USDT")
                                    ob = OrderBook(
                                        symbol=formatted,
                                        exchange='huobi',
                                        bids=[(bid, 1.0)],
                                        asks=[(ask, 1.0)],
                                        timestamp=time.time()
                                    )
                                    if self.on_orderbook_update:
                                        await self.on_orderbook_update(ob)
                            self.message_counts['huobi'] += len(items)
                await asyncio.sleep(EXCHANGES_CONFIG['huobi'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Huobi REST API: {e}")
                await asyncio.sleep(5)

    async def _poll_phemex_rest(self):
        """Получение best bid/ask Phemex через REST (spot ticker 24hr)"""
        logger.info("Запуск REST API polling для Phemex")
        while self.running:
            try:
                targets = set(s.replace('/', '').upper() for s in self.symbols if 'USDT' in s)
                updated = 0
                base = EXCHANGES_CONFIG['phemex']['rest_url']
                endpoints = [
                    f"{base}/md/spot/ticker/24hr",
                    f"{base}/md/spot/tickers",
                ]
                async with aiohttp.ClientSession() as session:
                    payload = None
                    for url in endpoints:
                        try:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    payload = await resp.json()
                                    logger.info(f"Phemex REST: используем эндпоинт {url}")
                                    break
                                else:
                                    logger.debug(f"Phemex REST: {url} -> HTTP {resp.status}")
                        except Exception as e:
                            logger.debug(f"Phemex REST: ошибка запроса {url}: {e}")

                    if payload is not None:
                        # Извлекаем список тикеров из различных возможных структур ответа
                        tickers = []
                        if isinstance(payload, dict):
                            if isinstance(payload.get('data'), dict):
                                tickers = payload['data'].get('tickers') or payload['data'].get('rows') or []
                            elif isinstance(payload.get('result'), dict):
                                tickers = payload['result'].get('tickers') or payload['result'].get('rows') or []
                            elif isinstance(payload.get('tickers'), list):
                                tickers = payload.get('tickers')
                        elif isinstance(payload, list):
                            tickers = payload

                        for it in tickers or []:
                            sym = (it.get('symbol') or it.get('symbolName') or it.get('sym') or '').upper()
                            if not sym or sym not in targets:
                                continue

                            bid = ask = 0.0
                            if ('bidEp' in it) or ('askEp' in it):
                                bid = float(it.get('bidEp') or 0) / 10000.0
                                ask = float(it.get('askEp') or 0) / 10000.0
                            elif ('bidPx' in it) or ('askPx' in it):
                                bid = float(it.get('bidPx') or 0)
                                ask = float(it.get('askPx') or 0)
                            elif ('bid' in it) or ('ask' in it):
                                bid = float(it.get('bid') or 0)
                                ask = float(it.get('ask') or 0)

                            if bid > 0 and ask > 0:
                                formatted = normalize_symbol(f"{sym[:-4]}/USDT" if sym.endswith('USDT') else sym.replace('-', '/'))
                                ob = OrderBook(
                                    symbol=formatted,
                                    exchange='phemex',
                                    bids=[(bid, 1.0)],
                                    asks=[(ask, 1.0)],
                                    timestamp=time.time()
                                )
                                if self.on_orderbook_update:
                                    await self.on_orderbook_update(ob)
                                updated += 1

                        # Увеличим счетчик сообщений
                        if 'phemex' not in self.message_counts:
                            self.message_counts['phemex'] = 0
                        self.message_counts['phemex'] += updated

                await asyncio.sleep(EXCHANGES_CONFIG['phemex'].get('poll_interval', 2))
            except Exception as e:
                logger.error(f"Ошибка Phemex REST API: {e}")
                await asyncio.sleep(5)

    async def _connect_bitget(self):
        """Подключение к Bitget WebSocket (временно отключено)"""
        logger.info("Bitget WebSocket временно отключен из-за технических проблем")
        return
        rate_limit_delay = 5  # Начальная задержка при rate limit (увеличивается при ошибках)
        max_rate_limit_delay = 300  # Увеличиваем максимальную задержку до 5 минут
        last_rate_limit_time = 0  # Время последнего превышения лимита
        consecutive_errors = 0  # Счетчик последовательных ошибок
        max_consecutive_errors = 10  # Максимальное количество последовательных ошибок
        
        while self.running:
            try:
                # Основной URL берём из конфига. Для demo wspap public используем fallback на wspap private,
                # иначе fallback на legacy v1 production.
                primary_url = EXCHANGES_CONFIG['bitget']['ws_url']
                if 'wspap.bitget.com' in primary_url and '/public' in primary_url:
                    fallback_url = 'wss://wspap.bitget.com/v2/ws/private'
                else:
                    fallback_url = 'wss://ws.bitget.com/spot/v1/stream'
                urls = [primary_url]
                if fallback_url != primary_url:
                    urls.append(fallback_url)

                # Bitget требует API ключи для WebSocket (для login)
                api_key = API_KEYS.get('bitget', {}).get('apiKey') or API_KEYS.get('bitget', {}).get('api_key')
                secret = API_KEYS.get('bitget', {}).get('secret')
                passphrase = API_KEYS.get('bitget', {}).get('passphrase', '')

                if not api_key or not secret:
                    logger.error("Bitget API ключи не найдены")
                    await asyncio.sleep(30)
                    continue
                    
                # Проверяем, не достигли ли мы лимита запросов
                if rate_limit_delay > 0:
                    logger.info(f"Ожидание {rate_limit_delay} сек. перед повторным подключением...")
                    await asyncio.sleep(rate_limit_delay)

                connected = False
                last_exc: Optional[Exception] = None

                for url in urls:
                    if not self.running:
                        break
                    try:
                        logger.info(f"Подключение к Bitget WebSocket: {url}")
                        # Для demo-окружения Bitget требуется заголовок PAPTRADING=1
                        extra_headers = {}
                        try:
                            bitget_env = str(API_KEYS.get('bitget', {}).get('env', '')).lower()
                            if bitget_env == 'demo' or TRADING_CONFIG.get('mode') in ('demo', 'paper'):
                                extra_headers['paptrading'] = '1'
                                logger.info("Bitget: используем paptrading=1 (demo)")
                        except Exception as e:
                            logger.warning(f"Ошибка при настройке заголовков Bitget: {e}")
                            
                        # Добавляем User-Agent и другие полезные заголовки
                        extra_headers.update({
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                            'Accept-Encoding': 'gzip, deflate, br',
                            'Accept': 'application/json'
                        })
                            
                        # Увеличиваем таймауты и добавляем дополнительные параметры соединения
                        connect_timeout = 15
                        if rate_limit_delay > 10:  # Если у нас уже были ошибки rate limit, даем больше времени на подключение
                            connect_timeout = 30
                            
                        async with websockets.connect(
                            url,
                            extra_headers=extra_headers if extra_headers else None,
                            ping_interval=30,  # Увеличиваем интервал пинга
                            ping_timeout=15,   # Увеличиваем таймаут пинга
                            close_timeout=15,  # Увеличиваем таймаут закрытия
                            open_timeout=connect_timeout,  # Таймаут на подключение
                            max_size=10 * 1024 * 1024  # Увеличиваем максимальный размер сообщения
                        ) as ws:
                            # Сбрасываем задержку при успешном подключении
                            if rate_limit_delay > 5:
                                rate_limit_delay = 5
                                logger.info("Сброс задержки подключения к Bitget")
                                
                            self.connections['bitget'] = ws
                            logger.info("Bitget WebSocket подключен")

                            # Аутентификация (login) только на private эндпоинтах
                            is_public = '/public' in url
                            if not is_public:
                                ts = str(int(time.time()))
                                msg = ts + 'GET' + '/user/verify'
                                import hmac
                                import hashlib
                                import base64
                                sign = base64.b64encode(
                                    hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()
                                ).decode()

                                auth_msg = {
                                    "op": "login",
                                    "args": [{
                                        "apiKey": api_key,
                                        "passphrase": passphrase,
                                        "timestamp": ts,
                                        "sign": sign
                                    }]
                                }
                                
                                try:
                                    await ws.send(json.dumps(auth_msg))
                                    logger.info("Bitget: login отправлен (passphrase присутствует)")

                                    # Не блокируемся надолго: пытаемся поймать login ack до подписок (до 5с)
                                    login_checked = False
                                    start_wait = time.time()
                                    login_attempts = 0
                                    max_login_attempts = 2
                                    
                                    while login_attempts < max_login_attempts and time.time() - start_wait < 5:
                                        try:
                                            raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                                            data = None
                                            try:
                                                data = json.loads(raw)
                                            except json.JSONDecodeError as je:
                                                logger.warning(f"Bitget: ошибка декодирования JSON: {je}, raw: {raw[:200]}...")
                                                continue
                                                
                                            # Логируем первые несколько сообщений для отладки
                                            if 'bitget' not in self.message_counts or self.message_counts['bitget'] < 5:
                                                logger.info(f"Bitget raw: {raw[:200]}...")
                                            
                                            if isinstance(data, dict):
                                                # Обработка ошибки rate limit
                                                if data.get('code') == '30016' or 'too many requests' in str(data).lower():
                                                    rate_limit_delay = min(rate_limit_delay * 2, max_rate_limit_delay)
                                                    logger.warning(f"Bitget: превышен лимит запросов. Увеличиваем задержку до {rate_limit_delay} сек.")
                                                    await asyncio.sleep(rate_limit_delay)
                                                    break
                                                    
                                                # Обработка успешного логина
                                                if 'event' in data and 'login' in str(data.get('event', '')).lower():
                                                    code = str(data.get('code', ''))
                                                    if code in ('', '0', '00000', 'success'):
                                                        logger.info(f"Bitget: login ack ✅ code={code}")
                                                        login_checked = True
                                                        # Сбрасываем задержку при успешном логине
                                                        if rate_limit_delay > 5:
                                                            old_delay = rate_limit_delay
                                                            rate_limit_delay = 5
                                                            logger.info(f"Bitget: сброс задержки с {old_delay} до {rate_limit_delay} сек.")
                                                        break
                                                    else:
                                                        logger.error(f"Bitget: login ack ❌ code={code} msg={data.get('msg', '')}")
                                                        login_attempts += 1
                                                        if login_attempts >= max_login_attempts:
                                                            logger.error("Bitget: превышено максимальное количество попыток входа")
                                                            raise Exception("Не удалось аутентифицироваться в Bitget")
                                                        await asyncio.sleep(1)  # Ждем перед следующей попыткой
                                                        
                                        except asyncio.TimeoutError:
                                            logger.warning("Bitget: таймаут ожидания ответа на логин")
                                            break
                                        except Exception as e:
                                            logger.error(f"Bitget: ошибка при обработке ответа на логин: {e}", exc_info=True)
                                            break
                                            
                                    if not login_checked:
                                        logger.warning("Bitget: не удалось подтвердить вход, продолжаем без аутентификации")
                                        
                                except Exception as e:
                                    logger.error(f"Bitget: ошибка при отправке логина: {e}")
                                    # Продолжаем без аутентификации, возможно, публичный эндпоинт
                            else:
                                logger.info("Bitget: public WS — пропускаем login")

                            # Подписка на тикеры и стаканы с батчингом и троттлингом
                            # Ограничиваем количество пар для подписки и добавляем приоритетные пары первыми
                            priority_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'ADA/USDT', 'DOGE/USDT']
                            
                            # Получаем все доступные пары, убираем дубликаты и ограничиваем общее количество
                            all_pairs = list(dict.fromkeys(
                                [p for p in priority_pairs if p in self.symbols] + 
                                [s for s in self.symbols if s not in priority_pairs and 'USDT' in s]
                            ))[:50]  # Увеличиваем лимит до 50 пар
                            
                            # Преобразуем формат символов для Bitget
                            symbols_to_subscribe = [s.replace('/', '').upper() for s in all_pairs]
                            if not symbols_to_subscribe:
                                symbols_to_subscribe = ['BTCUSDT']
                            
                            # Группируем подписки по 3 символа для снижения нагрузки
                            batch_size = 3  # Уменьшаем размер батча для снижения нагрузки
                            symbol_batches = [symbols_to_subscribe[i:i + batch_size] for i in range(0, len(symbols_to_subscribe), batch_size)]
                            
                            # Добавляем задержку перед началом подписок
                            await asyncio.sleep(1)
                            
                            # Уменьшаем размер батча, если были ошибки
                            if 'error' in locals() and error:
                                batch_size = max(1, batch_size // 2)
                                logger.info(f"Уменьшаем размер батча до {batch_size}")
                                await asyncio.sleep(2)
                        
                        # Добавляем дополнительную задержку после подписки на все пары
                        await asyncio.sleep(2)
                        connected = True
                        last_message_time = time.time()
                        error_count = 0
                        max_errors = 5
                        consecutive_errors = 0
                        
                        # Инициализируем счетчики
                        self.message_counts['bitget'] = 0
                        self.error_counts['bitget'] = 0

                        # Основной цикл чтения сообщений
                        while self.running:
                            try:
                                # Проверяем таймаут молчания
                                current_time = time.time()
                                if current_time - last_message_time > 45:
                                    logger.warning("Bitget: долгое отсутствие сообщений ({} сек), переподключаемся...".format(
                                        int(current_time - last_message_time)))
                                    break

                                # Читаем сообщение с таймаутом
                                try:
                                    raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
                                    message = None
                                    try:
                                        message = json.loads(raw)
                                    except json.JSONDecodeError as je:
                                        logger.error(f"Bitget: ошибка декодирования JSON: {je}, сообщение: {raw[:200]}...")
                                        self.error_counts['bitget'] += 1
                                        continue
                                    
                                    # Логируем первые несколько сообщений для отладки
                                    if self.message_counts['bitget'] < 10:  # Увеличиваем лимит для лучшей отладки
                                        logger.info(f"Bitget сообщение #{self.message_counts['bitget'] + 1}: {str(message)[:300]}")
                                        self.message_counts['bitget'] += 1
                                    
                                    # Обработка ошибки rate limit (30016)
                                    if isinstance(message, dict) and 'code' in message and str(message.get('code')) == '30016':
                                        current_time = time.time()
                                        time_since_last_rate_limit = current_time - last_rate_limit_time
                                        
                                        # Если с прошлого rate limit прошло больше 5 минут, сбрасываем задержку
                                        if time_since_last_rate_limit > 300:  # 5 минут
                                            rate_limit_delay = 5
                                            logger.info("Bitget: сброс задержки rate limit (прошло более 5 минут)")
                                        else:
                                            # Экспоненциальная задержка с ограничением
                                            rate_limit_delay = min(rate_limit_delay * 1.5, max_rate_limit_delay)
                                            
                                        last_rate_limit_time = current_time
                                        logger.warning(f"Bitget: превышен лимит запросов (30016). Увеличиваем задержку до {rate_limit_delay:.1f} сек.")
                                        
                                        # Добавляем случайное отклонение, чтобы избежать синхронизации
                                        jitter = random.uniform(0.8, 1.2)
                                        delay = min(rate_limit_delay * jitter, max_rate_limit_delay)
                                        
                                        logger.info(f"Bitget: ожидание {delay:.1f} сек. перед продолжением...")
                                        await asyncio.sleep(delay)
                                        continue
                                        
                                    # Обработка успешных сообщений
                                    if isinstance(message, dict) and 'data' in message:
                                        # Логируем успешное сообщение
                                        logger.debug(f"Bitget: получено сообщение: {message.get('arg', {}).get('channel', 'unknown')}")
                                        
                                    # Сбрасываем счетчики ошибок
                                    error_count = 0
                                    consecutive_errors = 0
                                    last_message_time = time.time()
                                        
                                    # Обработка тикеров (формат Bitget v2)
                                    if 'data' in message and 'action' in message and message['action'] == 'update':
                                        for item in message.get('data', []):
                                            try:
                                                symbol = item.get('instId', '')
                                                if not symbol:
                                                    continue
                                                    
                                                # Нормализуем символ (BTCUSDT -> BTC/USDT)
                                                if len(symbol) > 4 and symbol.endswith('USDT'):
                                                    symbol = f"{symbol[:-4]}/USDT"
                                                
                                                # Обновляем тикер
                                                bid = float(item.get('bidPr', 0))
                                                ask = float(item.get('askPr', 0))
                                                
                                                if bid > 0 and ask > 0:
                                                    # Создаем или обновляем стакан
                                                    if symbol not in self.orderbooks:
                                                        self.orderbooks[symbol] = {'bids': {}, 'asks': {}}
                                                    
                                                    # Обновляем лучшие цены
                                                    self.orderbooks[symbol]['bids'] = {bid: 0.1}  # Используем минимальный объем
                                                    self.orderbooks[symbol]['asks'] = {ask: 0.1}
                                                    
                                                    # Обновляем время последнего обновления
                                                    self.last_update_time[symbol] = time.time()
                                                    
                                                    # Вызываем колбэк, если он задан
                                                    if self.on_ticker_update:
                                                        ticker_data = {
                                                            'symbol': symbol,
                                                            'bid': bid,
                                                            'ask': ask,
                                                            'exchange': 'bitget',
                                                            'timestamp': time.time()
                                                        }
                                                        await self.on_ticker_update(ticker_data)
                                            
                                            except Exception as e:
                                                logger.error(f"Bitget ticker error: {e}")
                                                continue
                                        
                                except Exception as e:
                                    logger.error(f"Bitget message error: {e}")
                                    continue
                                        
                            except asyncio.TimeoutError:
                                # Отправляем пинг при таймауте
                                try:
                                    await ws.ping()
                                    logger.debug("Bitget: отправлен ping")
                                    continue
                                except Exception as e:
                                    logger.error(f"Bitget ping error: {e}")
                                    break
                                    
                            except Exception as e:
                                logger.error(f"Bitget connection error: {e}")
                                break
                            
                    except Exception as e:
                        logger.error(f"Bitget: ошибка при получении сообщения: {e}")
                        error_count += 1
                        consecutive_errors += 1
                        if error_count >= max_errors or consecutive_errors >= 3:
                            logger.error(f"Bitget: слишком много ошибок ({error_count}), переподключение...")
                            break
                        await asyncio.sleep(1)  # Пауза перед повторной попыткой
                        continue
                        
            except Exception as e:
                logger.error(f"Bitget: критическая ошибка: {e}")
                await asyncio.sleep(5)
                continue
                
    async def _handle_phemex_message(self, raw_msg: str, ws_instance):
        """Обработка сообщений от Phemex WebSocket."""
        try:
            data = json.loads(raw_msg)
            if 'book' in data and 'symbol' in data:
                symbol = data['symbol']  
                formatted_symbol = normalize_symbol(symbol)
                
                book_data = data['book']
                bids = [(float(bid[0]), float(bid[1])) for bid in book_data.get('bids', [])]
                asks = [(float(ask[0]), float(ask[1])) for ask in book_data.get('asks', [])]
                
                if bids and asks:
                    if formatted_symbol not in self.orderbooks:
                        self.orderbooks[formatted_symbol] = {}
                        
                    self.orderbooks[formatted_symbol]['phemex'] = OrderBook(
                        symbol=formatted_symbol,
                        exchange='phemex',
                        bids=bids[:10],
                        asks=asks[:10],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        try:
                            self.on_orderbook_update(self.orderbooks[formatted_symbol]['phemex'])
                        except Exception as e:
                            logger.error(f"Ошибка в on_orderbook_update: {e}")
                            
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения Phemex: {e}")
            
    def get_orderbook(self, symbol: str, exchange: str) -> Optional[OrderBook]:
        """Получить стакан заявок для символа и биржи."""
        if symbol in self.orderbooks and exchange in self.orderbooks[symbol]:
            return self.orderbooks[symbol][exchange]
        return None
    
    def get_all_orderbooks(self) -> Dict[str, Dict[str, OrderBook]]:
        """Получить все стаканы заявок."""
        return self.orderbooks
        
    async def stop(self):
        """Остановить WebSocket менеджер."""
        logger.info("Остановка WebSocket менеджера...")
        self.should_stop = True
        
        for task in self.active_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        self.active_tasks.clear()
        self.orderbooks.clear()
        logger.info("WebSocket менеджер остановлен")
    
    async def _connect_phemex(self):
        """Подключение к Phemex WebSocket с поддержкой прокси/VPN (aiohttp)"""
        while self.running:
            try:
                from production_config import PROXY_CONFIG
                url = "wss://ws.phemex.com/ws"

                # Формируем список попыток подключения (прокси-ротация + прямое подключение)
                attempts = []
                use_proxy = EXCHANGES_CONFIG.get('phemex', {}).get('use_proxy', False)
                if PROXY_CONFIG.get('enabled', False) and use_proxy:
                    for region, endpoints in PROXY_CONFIG.items():
                        if region == 'enabled':
                            continue
                        if isinstance(endpoints, dict):
                            # Порядок: SOCKS5 -> HTTPS -> HTTP
                            for key in ['socks5', 'https', 'http']:
                                val = endpoints.get(key)
                                if val:
                                    attempts.append((region, val))
                    logger.info(f"Phemex: найдено {len(attempts)} прокси-эндпоинтов")
                elif not use_proxy:
                    logger.info("Phemex: use_proxy=False — подключение напрямую без прокси")
                # Добавляем прямое подключение как запасной вариант
                attempts.append(("direct", None))

                connected = False
                last_error = None

                for region, proxy in attempts:
                    if not self.running:
                        break
                    try:
                        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=30)
                        headers = {
                            "User-Agent": "Mozilla/5.0 (compatible; WSBot/1.0)",
                            "Origin": "https://phemex.com",
                        }
                        # Настройка прокси-коннектора и аутентификации
                        connector = None
                        use_ws_proxy_param = True
                        proxy_auth = None
                        scheme = ''
                        if proxy:
                            try:
                                parts = urlsplit(proxy)
                                scheme = parts.scheme.lower()
                                if parts.username or parts.password:
                                    proxy_auth = aiohttp.BasicAuth(parts.username or '', parts.password or '')
                            except Exception:
                                scheme = ''
                                proxy_auth = None

                            if scheme.startswith('socks'):
                                try:
                                    from aiohttp_socks import ProxyConnector  # type: ignore
                                    connector = ProxyConnector.from_url(proxy)
                                    use_ws_proxy_param = False  # коннектор берет на себя проксирование
                                except Exception as e:
                                    logger.error(f"Phemex: aiohttp_socks недоступен для {proxy}: {e}")
                                    connector = None
                            elif scheme == 'https':
                                # Отключаем SSL-проверку к прокси-хосту во избежание ошибок сертификата
                                connector = aiohttp.TCPConnector(ssl=False)

                        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
                            logger.info(f"Phemex WS подключение ({region}) {'через прокси' if proxy else 'напрямую'}: {proxy or url}")
                            if use_ws_proxy_param and proxy:
                                ws = await session.ws_connect(
                                    url,
                                    proxy=proxy,
                                    proxy_auth=proxy_auth,
                                    autoping=True,
                                    heartbeat=WEBSOCKET_CONFIG['ping_interval'],
                                    # compression disabled: do not pass 'compress' to aiohttp ws_connect
                                )
                            else:
                                ws = await session.ws_connect(
                                    url,
                                    autoping=True,
                                    heartbeat=WEBSOCKET_CONFIG['ping_interval'],
                                    # compression disabled: do not pass 'compress' to aiohttp ws_connect
                                )
                            self.connections['phemex'] = ws
                            connected = True
                            logger.info(f"Phemex WebSocket подключен ({region})")

                            # Инициализация счетчиков при необходимости
                            if 'phemex' not in self.message_counts:
                                self.message_counts['phemex'] = 0
                            if 'phemex' not in self.error_counts:
                                self.error_counts['phemex'] = 0

                            # Подписка
                            symbols_to_subscribe = [s.replace('/', '').upper() for s in self.symbols if 'USDT' in s][:30]
                            if not symbols_to_subscribe:
                                symbols_to_subscribe = ['BTCUSDT']

                            for symbol in symbols_to_subscribe:
                                sub_msg = {
                                    "id": int(time.time() * 1000),
                                    "method": "orderbook.subscribe",
                                    "params": [f"{symbol}.L20"]
                                }
                                await ws.send_json(sub_msg)
                                await asyncio.sleep(0.05)

                            # Подписка на market24h (один раз)
                            ticker_msg = {
                                "id": int(time.time() * 1000) + 1,
                                "method": "market24h.subscribe",
                                "params": []
                            }
                            await ws.send_json(ticker_msg)

                            # Обработка сообщений
                            async for msg in ws:
                                try:
                                    if msg.type == aiohttp.WSMsgType.TEXT:
                                        data = json.loads(msg.data)
                                    elif msg.type == aiohttp.WSMsgType.BINARY:
                                        try:
                                            text = gzip.decompress(msg.data).decode('utf-8')
                                            data = json.loads(text)
                                        except Exception:
                                            try:
                                                data = json.loads(msg.data.decode('utf-8', errors='ignore'))
                                            except Exception:
                                                continue
                                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                        raise ConnectionError(f"WS closed/error: {msg.type}")
                                    else:
                                        continue

                                    # Обработка ошибок
                                    if isinstance(data, dict) and data.get('error'):
                                        logger.error(f"Phemex error: {data.get('error')}")
                                        self.error_counts['phemex'] += 1
                                        continue

                                    # Вариант с полем 'book'
                                    if isinstance(data, dict) and 'book' in data:
                                        book = data.get('book', {})
                                        sym = data.get('symbol', 'UNKNOWN')
                                        symbol_fmt = sym.replace('USDT', '/USDT') if 'USDT' in sym else sym
                                        bids = [(float(b[0]), float(b[1])) for b in book.get('bids', [])[:5]]
                                        asks = [(float(a[0]), float(a[1])) for a in book.get('asks', [])[:5]]
                                        if bids and asks:
                                            ob = OrderBook(
                                                symbol=normalize_symbol(symbol_fmt),
                                                exchange='phemex',
                                                bids=bids,
                                                asks=asks,
                                                timestamp=time.time()
                                            )
                                            if self.on_orderbook_update:
                                                await self.on_orderbook_update(ob)
                                            self.message_counts['phemex'] += 1
                                            continue

                                    # Вариант с 'market24h'
                                    if isinstance(data, dict) and 'market24h' in data:
                                        markets = data.get('market24h', [])
                                        for market in markets:
                                            sym = market.get('symbol', 'UNKNOWN')
                                            symbol_fmt = sym.replace('USDT', '/USDT') if 'USDT' in sym else sym
                                            bid = float(market.get('bidEp', 0)) / 10000
                                            ask = float(market.get('askEp', 0)) / 10000
                                            if bid > 0 and ask > 0:
                                                ob = OrderBook(
                                                    symbol=normalize_symbol(symbol_fmt),
                                                    exchange='phemex',
                                                    bids=[(bid, 1.0)],
                                                    asks=[(ask, 1.0)],
                                                    timestamp=time.time()
                                                )
                                                if self.on_orderbook_update:
                                                    await self.on_orderbook_update(ob)
                                                self.message_counts['phemex'] += 1
                                        continue

                                    # Считаем прочие сообщения
                                    self.message_counts['phemex'] += 1

                                except Exception as e:
                                    logger.error(f"Ошибка обработки Phemex сообщения: {e}")
                                    self.error_counts['phemex'] += 1

                            logger.warning("Phemex WebSocket поток завершен, переподключение...")
                            break

                    except aiohttp.WSServerHandshakeError as e:
                        last_error = e
                        logger.error(f"Phemex handshake failed ({region}): HTTP {getattr(e, 'status', '?')} {str(e)}")
                        continue
                    except Exception as e:
                        last_error = e
                        logger.error(f"Phemex подключение не удалось ({region}): {e}")
                        continue

                if not connected:
                    raise last_error or ConnectionError("Не удалось подключиться к Phemex через все прокси/напрямую")

            except Exception as e:
                logger.error(f"Ошибка подключения Phemex: {e}")
                await asyncio.sleep(5)
                if not self.running:
                    break
    
    async def stop(self):
        """Остановка всех соединений"""
        logger.info("Остановка WebSocket соединений...")
        self.running = False
        
        for exchange_id, ws in list(self.connections.items()):
            try:
                if ws:  # Проверяем что соединение существует
                    await ws.close()
                    logger.info(f"{exchange_id} WebSocket закрыт")
            except Exception as e:
                logger.debug(f"Ошибка при закрытии WebSocket для {exchange_id}: {e}")
        
        self.connections.clear()
    
    async def _connect_mexc(self):
        """MEXC WebSocket подключение"""
        url = EXCHANGES_CONFIG['mexc']['ws_url']
        
        async with websockets.connect(
            url,
            ping_interval=WEBSOCKET_CONFIG['ping_interval'],
            ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
        ) as ws:
            self.connections['mexc'] = ws
            self.reconnect_delays['mexc'] = WEBSOCKET_CONFIG['reconnect_delay']
            logger.info("MEXC WebSocket подключен")
            
            # Подписка на символы - используем правильный формат MEXC v3 API
            symbols_to_subscribe = [s.replace('/', '').upper() for s in self.symbols 
                                   if 'USDT' in s][:30]
            
            # Правильный формат подписки MEXC v3 API
            for symbol in symbols_to_subscribe:
                # Подписка на miniTickers для получения цен bid/ask
                sub_msg = {
                    "method": "SUBSCRIPTION",
                    "params": [f"spot@public.miniTickers.v3.api@{symbol}"]
                }
                await ws.send(json.dumps(sub_msg))
                await asyncio.sleep(0.05)  # Небольшая задержка между подписками
            
            # Обработка сообщений
            async for message in ws:
                try:
                    data = json.loads(message)
                    self.message_counts['mexc'] += 1
                    
                    if 'd' in data:
                        await self._process_mexc_message(data)
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки MEXC: {e}")
    
    async def _process_mexc_message(self, data: Dict):
        """Обработка сообщения MEXC"""
        try:
            # Обработка miniTickers v3 API
            if 'miniTickers' in str(data.get('c', '')):
                ticker = data['d']
                
                # Извлекаем символ из канала
                channel = data.get('c', '')
                if '@' in channel:
                    symbol = channel.split('@')[-1]
                else:
                    return
                
                # Создаем OrderBook из miniTicker данных
                if 'b' in ticker and 'a' in ticker:  # bid и ask цены
                    orderbook = OrderBook(
                        symbol=normalize_symbol(f"{symbol[:-4]}/USDT"),  # Конвертируем BTCUSDT -> BTC/USDT
                        exchange='mexc',
                        bids=[(float(ticker['b']), float(ticker.get('B', 1)))],  # bid price и volume
                        asks=[(float(ticker['a']), float(ticker.get('A', 1)))],  # ask price и volume  
                        timestamp=time.time()
                    )
                    
                    # Сохраняем в локальный кэш
                    if 'mexc' not in self.orderbooks:
                        self.orderbooks['mexc'] = {}
                    self.orderbooks['mexc'][orderbook.symbol] = orderbook
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга MEXC: {e}")
    
    async def _connect_bybit(self):
        """Bybit WebSocket подключение с поддержкой прокси (aiohttp)"""
        logger.error("🔥🔥🔥 МЕТОД _connect_bybit ЗАПУЩЕН!")
        while self.running:
            try:
                url = EXCHANGES_CONFIG['bybit']['ws_url']
                logger.error(f"🔄 ПОПЫТКА подключения к Bybit WebSocket: {url}")

                # Формируем список попыток подключения (ротация прокси + прямое)
                attempts = []
                if PROXY_CONFIG.get('enabled', False):
                    for region, endpoints in PROXY_CONFIG.items():
                        if region == 'enabled':
                            continue
                        if isinstance(endpoints, dict):
                            for key in ['socks5', 'https', 'http']:
                                val = endpoints.get(key)
                                if val:
                                    attempts.append((region, val))
                    logger.info(f"🔄 Bybit: найдено {len(attempts)} прокси-эндпоинтов")
                attempts.append(("direct", None))

                connected = False
                last_error = None

                for region, proxy in attempts:
                    if not self.running:
                        break
                    try:
                        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=30)
                        headers = {
                            "User-Agent": "Mozilla/5.0 (compatible; WSBot/1.0)",
                            "Origin": "https://bybit.com",
                        }

                        connector = None
                        use_ws_proxy_param = True
                        proxy_auth = None
                        scheme = ''
                        if proxy:
                            try:
                                parts = urlsplit(proxy)
                                scheme = parts.scheme.lower()
                                if parts.username or parts.password:
                                    proxy_auth = aiohttp.BasicAuth(parts.username or '', parts.password or '')
                            except Exception:
                                scheme = ''
                                proxy_auth = None

                            if scheme.startswith('socks'):
                                try:
                                    from aiohttp_socks import ProxyConnector  # type: ignore
                                    connector = ProxyConnector.from_url(proxy)
                                    use_ws_proxy_param = False
                                except Exception as e:
                                    logger.error(f"Bybit: aiohttp_socks недоступен для {proxy}: {e}")
                                    connector = None
                            elif scheme == 'https':
                                # Отключаем SSL-проверку для HTTPS прокси
                                connector = aiohttp.TCPConnector(ssl=False)

                        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
                            logger.info(f"🌐 Bybit WS подключение ({region}) {'через прокси' if proxy else 'напрямую'}: {proxy or url}")
                            if use_ws_proxy_param and proxy:
                                ws = await session.ws_connect(
                                    url,
                                    proxy=proxy,
                                    proxy_auth=proxy_auth,
                                    autoping=True,
                                    heartbeat=WEBSOCKET_CONFIG['ping_interval']
                                )
                            else:
                                ws = await session.ws_connect(
                                    url,
                                    autoping=True,
                                    heartbeat=WEBSOCKET_CONFIG['ping_interval']
                                )

                            self.connections['bybit'] = ws
                            self.reconnect_delays['bybit'] = WEBSOCKET_CONFIG['reconnect_delay']
                            connected = True
                            logger.info(f"✅ Bybit WebSocket подключен ({region})")

                            # Инициализация счетчиков
                            if 'bybit' not in self.message_counts:
                                self.message_counts['bybit'] = 0
                            if 'bybit' not in self.error_counts:
                                self.error_counts['bybit'] = 0

                            # Подписка на символы (orderbook и tickers)
                            symbols_to_subscribe = []
                            for symbol in self.symbols[:30]:
                                bybit_symbol = symbol.replace('/', '').upper()
                                symbols_to_subscribe.append(f"orderbook.1.{bybit_symbol}")
                                symbols_to_subscribe.append(f"tickers.{bybit_symbol}")

                            sub_msg = {
                                "op": "subscribe",
                                "args": symbols_to_subscribe
                            }
                            await ws.send_json(sub_msg)

                            # Обработка сообщений
                            async for msg in ws:
                                try:
                                    if msg.type == aiohttp.WSMsgType.TEXT:
                                        data = json.loads(msg.data)
                                    elif msg.type == aiohttp.WSMsgType.BINARY:
                                        # Bybit, как правило, отправляет текст, но пытаемся декодировать при необходимости
                                        try:
                                            text = gzip.decompress(msg.data).decode('utf-8')
                                        except Exception:
                                            text = msg.data.decode('utf-8', errors='ignore')
                                        data = json.loads(text)
                                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                        raise ConnectionError(f"WS closed/error: {msg.type}")
                                    else:
                                        continue

                                    # ping/pong по протоколу Bybit
                                    if isinstance(data, dict) and data.get('op') == 'ping':
                                        await ws.send_json({"op": "pong"})
                                        continue

                                    if isinstance(data, dict) and 'topic' in data:
                                        await self._process_bybit_message(data)

                                    # инкрементируем счетчик для всех валидных сообщений
                                    self.message_counts['bybit'] += 1

                                except json.JSONDecodeError as e:
                                    logger.error(f"Ошибка парсинга JSON Bybit: {e}")
                                    self.error_counts['bybit'] += 1
                                except Exception as e:
                                    logger.error(f"Ошибка обработки Bybit: {e}")
                                    self.error_counts['bybit'] += 1

                            logger.warning("Bybit WebSocket поток завершен, переподключение...")
                            break

                    except aiohttp.WSServerHandshakeError as e:
                        last_error = e
                        logger.error(f"❌ Bybit handshake failed ({region}): HTTP {getattr(e, 'status', '?')} {str(e)}")
                        continue
                    except Exception as e:
                        last_error = e
                        logger.error(f"❌ Bybit подключение не удалось ({region}): {e}")
                        continue

                if not connected:
                    raise last_error or ConnectionError("Не удалось подключиться к Bybit через все прокси/напрямую")

            except Exception as e:
                logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА Bybit: {e}")
                logger.error(f"   URL: {EXCHANGES_CONFIG['bybit']['ws_url']}")
                logger.error(f"   Тип ошибки: {type(e).__name__}")
                await asyncio.sleep(5)
                if self.running:
                    continue
    
    async def _process_bybit_message(self, data: Dict):
        """Обработка сообщения Bybit"""
        try:
            topic = data['topic']
            
            if 'orderbook' in topic:
                symbol = topic.split('.')[-1]
                depth = data['data']
                
                bids = [(float(b[0]), float(b[1])) for b in depth.get('b', [])]
                asks = [(float(a[0]), float(a[1])) for a in depth.get('a', [])]
                
                if bids and asks:
                    # Конвертируем символ обратно
                    for base_curr in ['USDT', 'USDC', 'BUSD']:
                        if symbol.endswith(base_curr):
                            formatted_symbol = f"{symbol[:-len(base_curr)]}/{base_curr}"
                            break
                    else:
                        formatted_symbol = symbol
                    
                    orderbook = OrderBook(
                        symbol=normalize_symbol(formatted_symbol),
                        exchange='bybit',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
            elif 'tickers' in topic:
                ticker = data['data']
                symbol = ticker['symbol']
                
                # Конвертируем символ
                for base_curr in ['USDT', 'USDC', 'BUSD']:
                    if symbol.endswith(base_curr):
                        formatted_symbol = f"{symbol[:-len(base_curr)]}/{base_curr}"
                        break
                else:
                    formatted_symbol = symbol
                
                orderbook = OrderBook(
                    symbol=normalize_symbol(formatted_symbol),
                    exchange='bybit',
                    bids=[(float(ticker.get('bid1Price', 0)), float(ticker.get('bid1Size', 0)))],
                    asks=[(float(ticker.get('ask1Price', 0)), float(ticker.get('ask1Size', 0)))],
                    timestamp=time.time()
                )
                
                if self.on_orderbook_update:
                    await self.on_orderbook_update(orderbook)
                    
        except Exception as e:
            logger.error(f"Ошибка парсинга Bybit: {e}")
    
    async def _connect_huobi(self):
        """Huobi WebSocket подключение"""
        logger.info("🔥🔥🔥 МЕТОД _connect_huobi ЗАПУЩЕН!")
        while self.running:
            try:
                url = EXCHANGES_CONFIG['huobi']['ws_url']
                logger.info(f"🔄 Подключение к Huobi WebSocket: {url}")
                
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as ws:
                    self.connections['huobi'] = ws
                    self.reconnect_delays['huobi'] = WEBSOCKET_CONFIG['reconnect_delay']
                    logger.info("✅ Huobi WebSocket подключен")
                    
                    # Инициализация счетчиков если не существует
                    if 'huobi' not in self.message_counts:
                        self.message_counts['huobi'] = 0
                    if 'huobi' not in self.error_counts:
                        self.error_counts['huobi'] = 0
                    
                    # Подписка на символы - Huobi формат (исправлена логика)
                    symbols_to_subscribe = []
                    for symbol in self.symbols[:30]:  # Ограничиваем количество
                        if 'USDT' in symbol:
                            huobi_symbol = symbol.replace('/', '').lower()
                            symbols_to_subscribe.append(huobi_symbol)
                    
                    logger.info(f"📡 Huobi подписывается на {len(symbols_to_subscribe)} символов")
                    
                    for symbol in symbols_to_subscribe:
                        try:
                            # Подписка на тикер
                            sub_msg = {
                                "sub": f"market.{symbol}.ticker",
                                "id": f"ticker_{symbol}"
                            }
                            await ws.send(json.dumps(sub_msg))
                            await asyncio.sleep(0.1)  # Небольшая задержка
                        except Exception as e:
                            logger.error(f"Ошибка подписки Huobi на {symbol}: {e}")
                    
                    # Обработка сообщений
                    async for message in ws:
                        try:
                            # Huobi использует gzip сжатие
                            if isinstance(message, bytes):
                                try:
                                    message = gzip.decompress(message).decode('utf-8')
                                except Exception as e:
                                    logger.error(f"Ошибка декомпрессии gzip: {e}")
                                    continue
                            
                            data = json.loads(message)
                            self.message_counts['huobi'] += 1
                            
                            # Ответ на ping
                            if 'ping' in data:
                                pong_msg = {"pong": data['ping']}
                                await ws.send(json.dumps(pong_msg))
                                continue
                            
                            # Обработка подтверждений подписки
                            if 'status' in data:
                                if data.get('status') == 'ok':
                                    logger.info(f"Huobi подписка успешна: {data.get('id', 'unknown')}")
                                else:
                                    logger.error(f"Huobi ошибка подписки: {data}")
                                continue
                            
                            # Обработка данных
                            if 'ch' in data and 'tick' in data:
                                await self._process_huobi_message(data)
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"Ошибка парсинга JSON Huobi: {e}")
                            self.error_counts['huobi'] += 1
                        except Exception as e:
                            logger.error(f"Ошибка обработки Huobi: {e}")
                            self.error_counts['huobi'] += 1
                            
            except Exception as e:
                logger.error(f"❌ Критическая ошибка подключения Huobi: {e}")
                if 'huobi' in self.connections:
                    del self.connections['huobi']
                await asyncio.sleep(10)
                if not self.running:
                    break
    
    async def _process_huobi_message(self, data: Dict):
        """Обработка сообщения Huobi"""
        try:
            channel = data['ch']
            
            if 'ticker' in channel:
                parts = channel.split('.')
                symbol = parts[1].upper()
                ticker = data['tick']
                
                # Конвертируем символ
                for base_curr in ['USDT', 'USDC', 'BUSD']:
                    if symbol.endswith(base_curr.lower()):
                        formatted_symbol = f"{symbol[:-len(base_curr)]}/{base_curr}"
                        break
                else:
                    formatted_symbol = symbol
                
                orderbook = OrderBook(
                    symbol=normalize_symbol(formatted_symbol),
                    exchange='huobi',
                    bids=[(ticker['bid'], ticker['bidSize'])],
                    asks=[(ticker['ask'], ticker['askSize'])],
                    timestamp=time.time()
                )
                
                if self.on_orderbook_update:
                    await self.on_orderbook_update(orderbook)
                    
            elif 'depth' in channel:
                parts = channel.split('.')
                symbol = parts[1].upper()
                depth = data['tick']
                
                bids = [(float(b[0]), float(b[1])) for b in depth.get('bids', [])]
                asks = [(float(a[0]), float(a[1])) for a in depth.get('asks', [])]
                
                if bids and asks:
                    # Конвертируем символ
                    for base_curr in ['USDT', 'USDC', 'BUSD']:
                        if symbol.endswith(base_curr.lower()):
                            formatted_symbol = f"{symbol[:-len(base_curr)]}/{base_curr}"
                            break
                    else:
                        formatted_symbol = symbol
                    
                    orderbook = OrderBook(
                        symbol=normalize_symbol(formatted_symbol),
                        exchange='huobi',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга Huobi: {e}")
    
    async def _connect_binance(self):
        """Binance WebSocket подключение (обход геоблокировки)"""
        logger.info("🔥🔥🔥 МЕТОД _connect_binance ЗАПУЩЕН!")
        
        while self.running:
            try:
                url = EXCHANGES_CONFIG['binance']['ws_url']
                logger.info(f"🔄 Попытка подключения к Binance WebSocket: {url}")
                
                # Инициализация счетчиков
                if 'binance' not in self.message_counts:
                    self.message_counts['binance'] = 0
                if 'binance' not in self.error_counts:
                    self.error_counts['binance'] = 0
                
                # Binance работает без API ключей для публичных данных
                # Используем альтернативный endpoint для обхода блокировки
                alternative_urls = [
                    'wss://stream.binance.com:9443/ws',
                    'wss://stream.binance.com:443/ws',
                    'wss://stream.binancezh.com:9443/ws'  # Китайский сервер
                ]
                
                connection_successful = False
                for attempt_url in alternative_urls:
                    try:
                        logger.info(f"Попытка подключения к {attempt_url}")
                        async with websockets.connect(
                            attempt_url,
                            ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                            ping_timeout=WEBSOCKET_CONFIG['ping_timeout'],
                            close_timeout=10
                        ) as ws:
                            self.connections['binance'] = ws
                            self.reconnect_delays['binance'] = WEBSOCKET_CONFIG['reconnect_delay']
                            logger.info("✅ Binance WebSocket подключен")
                            connection_successful = True
                            
                            # Подписка на символы - Binance формат (расширено количество, добавлен depth)
                            ticker_streams = []
                            for symbol in self.symbols[:100]:
                                binance_symbol = symbol.replace('/', '').lower()
                                ticker_streams.append(f"{binance_symbol}@ticker")

                            # Дополнительно подписываемся на глубину стакана для топ-20
                            depth_streams = []
                            for symbol in self.symbols[:20]:
                                binance_symbol = symbol.replace('/', '').lower()
                                depth_streams.append(f"{binance_symbol}@depth5@100ms")

                            streams = ticker_streams + depth_streams
                            sub_msg = {
                                "method": "SUBSCRIBE",
                                "params": streams,
                                "id": 1
                            }
                            await ws.send(json.dumps(sub_msg))
                            logger.info(f"📡 Binance подписался на {len(streams)} потоков ({len(ticker_streams)} тикеров, {len(depth_streams)} depth)")
                            
                            # Обработка сообщений
                            async for message in ws:
                                try:
                                    data = json.loads(message)
                                    self.message_counts['binance'] += 1
                                    
                                    # Обработка подтверждения подписки
                                    if 'result' in data and data.get('id') == 1:
                                        logger.info("Binance подписка подтверждена")
                                        continue
                                        
                                    if 'stream' in data:
                                        await self._process_binance_message(data)
                                        
                                except json.JSONDecodeError as e:
                                    logger.error(f"Ошибка парсинга JSON Binance: {e}")
                                    self.error_counts['binance'] += 1
                                except Exception as e:
                                    logger.error(f"Ошибка обработки Binance: {e}")
                                    self.error_counts['binance'] += 1
                            break
                    except Exception as e:
                        logger.warning(f"Не удалось подключиться к {attempt_url}: {e}")
                        continue
                        
                if not connection_successful:
                    raise Exception("Все попытки подключения к Binance WebSocket неудачны")
                        
            except Exception as e:
                logger.error(f"❌ Binance WebSocket критическая ошибка: {e}")
                if 'binance' in self.connections:
                    del self.connections['binance']
                await asyncio.sleep(15)
                if not self.running:
                    break
    
    async def _connect_okx(self):
        """OKX WebSocket подключение"""
        # Выбираем эндпоинт в зависимости от режима
        if TRADING_CONFIG.get('mode') == 'demo':
            url = EXCHANGES_CONFIG['okx'].get('demo_ws_url', EXCHANGES_CONFIG['okx']['ws_url'])
            logger.info("OKX: используем демо WebSocket эндпоинт")
        else:
            url = EXCHANGES_CONFIG['okx']['ws_url']
        
        try:
            # OKX работает без API ключей для публичных данных
            async with websockets.connect(
                url,
                ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
            ) as ws:
                self.connections['okx'] = ws
                self.reconnect_delays['okx'] = WEBSOCKET_CONFIG['reconnect_delay']
                logger.info("✅ OKX WebSocket подключен")
                
                # Инициализация счетчиков если не существует
                if 'okx' not in self.message_counts:
                    self.message_counts['okx'] = 0
                if 'okx' not in self.error_counts:
                    self.error_counts['okx'] = 0
                
                # Подписка на символы - OKX формат (увеличено и отправляется батчами)
                args = []
                for symbol in self.symbols[:60]:
                    okx_symbol = symbol.replace('/', '-').upper()
                    args.append({"channel": "tickers", "instId": okx_symbol})
                    args.append({"channel": "books5", "instId": okx_symbol})

                # Отправляем подписки батчами по 40 аргументов для устойчивости
                for i in range(0, len(args), 40):
                    sub_msg = {
                        "op": "subscribe",
                        "args": args[i:i+40]
                    }
                    await ws.send(json.dumps(sub_msg))
                    await asyncio.sleep(0.1)
                logger.info(f"📡 OKX подписался на {len(args)} каналов (батчами)")
                
                # Обработка сообщений
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self.message_counts['okx'] += 1
                        
                        # Логируем первые несколько сообщений для отладки
                        if self.message_counts['okx'] <= 5:
                            logger.info(f"OKX сообщение #{self.message_counts['okx']}: {str(data)[:200]}")
                        
                        if 'data' in data and 'arg' in data:
                            await self._process_okx_message(data)
                        elif 'event' in data:
                            # Обработка служебных сообщений OKX (подтверждения подписки)
                            if data.get('event') == 'subscribe':
                                logger.info(f"OKX подписка подтверждена: {data.get('arg', {}).get('channel', 'unknown')}")
                            elif data.get('event') == 'error':
                                logger.error(f"OKX ошибка подписки: {data}")
                        else:
                            # Логируем неизвестные сообщения для анализа
                            if self.message_counts['okx'] <= 10:
                                logger.warning(f"OKX неизвестное сообщение: {str(data)[:150]}")
                            pass
                            
                    except Exception as e:
                        logger.error(f"Ошибка обработки OKX: {e}")
                        
        except Exception as e:
            logger.error(f"❌ OKX WebSocket ошибка: {e}")
            raise
    
    async def _connect_gate(self):
        """Gate.io WebSocket подключение"""
        while self.running:
            try:
                url = EXCHANGES_CONFIG['gate']['ws_url']
                logger.info(f"🔄 Подключение к Gate.io WebSocket: {url}")
                
                async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                    self.connections['gate'] = ws
                    logger.info("✅ Gate.io WebSocket подключен")
                    
                    # Подписка на символы - Gate.io формат (увеличено и с троттлингом)
                    for idx, symbol in enumerate(self.symbols[:80]):
                        gate_symbol = symbol.replace('/', '_').upper()
                        
                        # Подписка на тикер
                        ticker_sub = {
                            "time": int(time.time()),
                            "channel": "spot.tickers",
                            "event": "subscribe",
                            "payload": [gate_symbol]
                        }
                        await ws.send(json.dumps(ticker_sub))
                        
                        # Подписка на orderbook
                        book_sub = {
                            "time": int(time.time()),
                            "channel": "spot.order_book",
                            "event": "subscribe", 
                            "payload": [gate_symbol, "5", "100ms"]
                        }
                        await ws.send(json.dumps(book_sub))
                        if idx % 10 == 0:
                            await asyncio.sleep(0.1)
                    
                    logger.info(f"📡 Gate.io подписался на {len(self.symbols[:80])} пар с батч-троттлингом")
                    
                    # Обработка сообщений
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if 'event' in data and data['event'] == 'update':
                                await self._process_gate_message(data)
                        except Exception as e:
                            logger.error(f"Ошибка обработки Gate.io: {e}")
                            
            except Exception as e:
                logger.error(f"Ошибка подключения Gate.io: {e}")
                await asyncio.sleep(5)
                if self.running:
                    continue
    
    async def _connect_kucoin(self):
        """KuCoin WebSocket подключение"""
        try:
            # Сначала получаем WebSocket endpoint от KuCoin API
            async with aiohttp.ClientSession() as session:
                endpoint_url = f"{EXCHANGES_CONFIG['kucoin']['rest_url']}/api/v1/bullet-public"
                async with session.post(endpoint_url) as resp:
                    if resp.status == 200:
                        bullet_data = await resp.json()
                        ws_endpoint = bullet_data['data']['instanceServers'][0]['endpoint']
                        ws_token = bullet_data['data']['token']
                        ws_url = f"{ws_endpoint}?token={ws_token}&[connectId=1]"
                    else:
                        raise Exception(f"Не удалось получить KuCoin WebSocket endpoint: {resp.status}")
            
            async with websockets.connect(
                ws_url,
                ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
            ) as ws:
                self.connections['kucoin'] = ws
                self.reconnect_delays['kucoin'] = WEBSOCKET_CONFIG['reconnect_delay']
                logger.info("✅ KuCoin WebSocket подключен")
                
                # Подписка на символы - KuCoin формат
                for symbol in self.symbols[:80]:
                    kucoin_symbol = symbol.replace('/', '-').upper()
                    
                    # Ticker subscription
                    ticker_msg = {
                        "id": int(time.time() * 1000),
                        "type": "subscribe",
                        "topic": f"/market/ticker:{kucoin_symbol}",
                        "response": True
                    }
                    await ws.send(json.dumps(ticker_msg))
                    
                    # OrderBook subscription
                    book_msg = {
                        "id": int(time.time() * 1000) + 1,
                        "type": "subscribe",
                        "topic": f"/market/level2:{kucoin_symbol}",
                        "response": True
                    }
                    await ws.send(json.dumps(book_msg))
                    await asyncio.sleep(0.1)
                
                logger.info(f"📡 KuCoin подписался на {len(self.symbols[:80]) * 2} топиков")
                
                # Обработка сообщений
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self.message_counts['kucoin'] += 1
                        
                        if 'subject' in data:
                            await self._process_kucoin_message(data)
                            
                    except Exception as e:
                        logger.error(f"Ошибка обработки KuCoin: {e}")
                        
        except Exception as e:
            logger.error(f"❌ KuCoin WebSocket ошибка: {e}")
            raise
    
    async def _connect_kraken(self):
        """Kraken WebSocket подключение"""
        url = EXCHANGES_CONFIG['kraken']['ws_url']
        
        try:
            # Kraken работает без API ключей для публичных данных
            async with websockets.connect(
                url,
                ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
            ) as ws:
                self.connections['kraken'] = ws
                self.reconnect_delays['kraken'] = WEBSOCKET_CONFIG['reconnect_delay']
                logger.info("✅ Kraken WebSocket подключен")
                
                # Подписка на символы - Kraken формат
                pairs = []
                for symbol in self.symbols[:50]:
                    # Kraken использует специальные названия пар
                    if symbol == 'BTC/USDT':
                        pairs.append('XBT/USDT')
                    else:
                        pairs.append(symbol.replace('/', ''))
                
                # Ticker subscription
                ticker_msg = {
                    "event": "subscribe",
                    "pair": pairs,
                    "subscription": {"name": "ticker"}
                }
                await ws.send(json.dumps(ticker_msg))
                
                # Book subscription
                book_msg = {
                    "event": "subscribe",
                    "pair": pairs,
                    "subscription": {"name": "book", "depth": 5}
                }
                await ws.send(json.dumps(book_msg))
                
                logger.info(f"📡 Kraken подписался на {len(pairs)} пар")
                
                # Обработка сообщений
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self.message_counts['kraken'] += 1
                        
                        # Kraken отправляет массивы данных
                        if isinstance(data, list) and len(data) >= 3:
                            await self._process_kraken_message(data)
                        elif isinstance(data, dict) and data.get('event') == 'heartbeat':
                            # Отвечаем на heartbeat
                            pass
                            
                    except Exception as e:
                        logger.error(f"Ошибка обработки Kraken: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Kraken WebSocket ошибка: {e}")
            raise
    
    async def _process_binance_message(self, data: Dict):
        """Обработка сообщения Binance"""
        try:
            stream_data = data['data']
            stream = data['stream']
            
            if '@ticker' in stream:
                symbol = stream.split('@')[0].upper()
                # Конвертируем символ обратно
                formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
                
                orderbook = OrderBook(
                    symbol=normalize_symbol(formatted_symbol),
                    exchange='binance',
                    bids=[(float(stream_data['b']), float(stream_data['B']))],
                    asks=[(float(stream_data['a']), float(stream_data['A']))],
                    timestamp=time.time()
                )
                
                if self.on_orderbook_update:
                    await self.on_orderbook_update(orderbook)
                    
            elif '@depth' in stream:
                symbol = stream.split('@')[0].upper()
                formatted_symbol = f"{symbol[:-4]}/{symbol[-4:]}" if len(symbol) > 4 else symbol
                
                bids = [(float(b[0]), float(b[1])) for b in stream_data.get('bids', [])]
                asks = [(float(a[0]), float(a[1])) for a in stream_data.get('asks', [])]
                
                if bids and asks:
                    orderbook = OrderBook(
                        symbol=normalize_symbol(formatted_symbol),
                        exchange='binance',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга Binance: {e}")
    
    async def _process_kucoin_message(self, data: Dict):
        """Обработка сообщения KuCoin"""
        try:
            subject = data['subject']
            topic = data['topic']
            msg_data = data['data']
            
            if 'ticker' in subject:
                symbol = topic.split(':')[1].replace('-', '/')
                
                orderbook = OrderBook(
                    symbol=symbol,
                    exchange='kucoin',
                    bids=[(float(msg_data['bestBid']), float(msg_data['bestBidSize']))],
                    asks=[(float(msg_data['bestAsk']), float(msg_data['bestAskSize']))],
                    timestamp=time.time()
                )
                
                if self.on_orderbook_update:
                    await self.on_orderbook_update(orderbook)
                    
            elif 'level2' in subject:
                symbol = topic.split(':')[1].replace('-', '/')
                
                bids = [(float(b[0]), float(b[1])) for b in msg_data.get('bids', [])]
                asks = [(float(a[0]), float(a[1])) for a in msg_data.get('asks', [])]
                
                if bids and asks:
                    orderbook = OrderBook(
                        symbol=symbol,
                        exchange='kucoin',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга KuCoin: {e}")
    
    async def _process_okx_message(self, data: dict):
        """Обработка сообщения OKX"""
        try:
            if isinstance(data, dict) and 'data' in data and 'arg' in data:
                arg = data['arg']
                channel = arg.get('channel', '')
                inst_id = arg.get('instId', '')
                symbol = inst_id.replace('-', '/')
                
                for item in data['data']:
                    if channel == 'tickers' and 'last' in item:
                        # Создаем OrderBook из тикера
                        bid_price = float(item.get('bidPx', 0))
                        ask_price = float(item.get('askPx', 0))
                        
                        if bid_price > 0 and ask_price > 0:
                            orderbook = OrderBook(
                                symbol=symbol,
                                exchange='okx',
                                bids=[(bid_price, float(item.get('bidSz', 1)))],
                                asks=[(ask_price, float(item.get('askSz', 1)))],
                                timestamp=time.time()
                            )
                            
                            if self.on_orderbook_update:
                                await self.on_orderbook_update(orderbook)
                    
                    elif channel == 'books5' and 'bids' in item and 'asks' in item:
                        bids = [(float(b[0]), float(b[1])) for b in item['bids'] if len(b) >= 2]
                        asks = [(float(a[0]), float(a[1])) for a in item['asks'] if len(a) >= 2]
                        
                        if bids and asks:
                            orderbook = OrderBook(
                                symbol=symbol,
                                exchange='okx',
                                bids=bids[:5],
                                asks=asks[:5],
                                timestamp=time.time()
                            )
                            
                            if self.on_orderbook_update:
                                await self.on_orderbook_update(orderbook)
                                    
        except Exception as e:
            logger.error(f"Ошибка парсинга OKX: {e} | Data: {str(data)[:200]}")
    
    async def _process_gate_message(self, data: dict):
        """Обработка сообщения Gate.io"""
        try:
            if isinstance(data, dict) and data.get('event') == 'update':
                channel = data.get('channel', '')
                result = data.get('result', {})
                
                if channel == 'spot.tickers' and isinstance(result, dict):
                    symbol = result.get('currency_pair', '').replace('_', '/')
                    if symbol and 'last' in result:
                        ticker = {
                            'symbol': symbol,
                            'last': float(result['last']),
                            'volume': float(result.get('base_volume', 0)),
                            'timestamp': time.time()
                        }
                        
                        if self.on_ticker_update:
                            await self.on_ticker_update(ticker, 'gate')
                
                elif channel == 'spot.order_book' and isinstance(result, dict):
                    symbol = result.get('s', '').replace('_', '/')
                    if symbol and 'bids' in result and 'asks' in result:
                        bids = [(float(b[0]), float(b[1])) for b in result['bids'] if len(b) >= 2]
                        asks = [(float(a[0]), float(a[1])) for a in result['asks'] if len(a) >= 2]
                        
                        if bids and asks:
                            orderbook = OrderBook(
                                symbol=symbol,
                                exchange='gate',
                                bids=bids[:5],
                                asks=asks[:5],
                                timestamp=time.time()
                            )
                            
                            if self.on_orderbook_update:
                                await self.on_orderbook_update(orderbook)
                                    
        except Exception as e:
            logger.error(f"Ошибка парсинга Gate.io: {e} | Data: {str(data)[:200]}")
    
    async def _process_kraken_message(self, data: List):
        """Обработка сообщения Kraken"""
        try:
            if len(data) >= 4:
                msg_data = data[1]
                pair = data[3]
                channel = data[2]
                
                # Конвертируем пару обратно
                if pair == 'XBT/USDT':
                    symbol = 'BTC/USDT'
                else:
                    symbol = pair
                
                if channel == 'ticker':
                    ticker = msg_data
                    
                    orderbook = OrderBook(
                        symbol=symbol,
                        exchange='kraken',
                        bids=[(float(ticker['b'][0]), float(ticker['b'][1]))],
                        asks=[(float(ticker['a'][0]), float(ticker['a'][1]))],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
                elif channel == 'book-5':
                    book_data = msg_data
                    
                    bids = []
                    asks = []
                    
                    if 'b' in book_data:
                        bids = [(float(b[0]), float(b[1])) for b in book_data['b']]
                    if 'a' in book_data:
                        asks = [(float(a[0]), float(a[1])) for a in book_data['a']]
                        
                    if bids and asks:
                        orderbook = OrderBook(
                            symbol=symbol,
                            exchange='kraken',
                            bids=bids[:5],
                            asks=asks[:5],
                            timestamp=time.time()
                        )
                        
                        if self.on_orderbook_update:
                            await self.on_orderbook_update(orderbook)
                            
        except Exception as e:
            logger.error(f"Ошибка парсинга Kraken: {e}")
    
    def get_statistics(self) -> Dict:
        """Получить статистику WebSocket"""
        stats = {
            'connected': list(self.connections.keys()),
            'message_counts': dict(self.message_counts),
            'error_counts': dict(self.error_counts),
            'last_ping': dict(self.last_ping),
            'reconnect_delays': dict(self.reconnect_delays)
        }
        return stats
