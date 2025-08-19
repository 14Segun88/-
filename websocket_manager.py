#!/usr/bin/env python3
"""
🌐 WEBSOCKET MANAGER
Управление WebSocket соединениями для всех бирж
"""

import asyncio
import json
import time
import gzip
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
import websockets
import aiohttp
from collections import defaultdict
import hashlib
import hmac
import base64
from urllib.parse import urlencode

from production_config import EXCHANGES_CONFIG, WEBSOCKET_CONFIG, PROXY_CONFIG, API_KEYS

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
    
    def __init__(self, on_orderbook_update: Optional[Callable] = None):
        self.connections = {}
        self.subscriptions = defaultdict(set)
        self.reconnect_delays = defaultdict(lambda: WEBSOCKET_CONFIG['reconnect_delay'])
        self.running = False
        self.on_orderbook_update = on_orderbook_update
        self.last_ping = defaultdict(float)
        self.message_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.orderbooks = {}  # Кэш ордербуков
        # Список активных бирж
        self.exchanges = [ex for ex, conf in EXCHANGES_CONFIG.items() if conf['enabled']]
        
    async def start(self, symbols: List[str]):
        """Запуск WebSocket соединений"""
        self.running = True
        self.symbols = symbols
        logger.info(f"🚀 Запуск WebSocket для {len(symbols)} символов")
        
        # Запуск подключений для активных бирж
        tasks = []
        for exchange in self.exchanges:
            if exchange == 'mexc':
                # MEXC WebSocket v3 API не работает - используем REST API
                logger.warning("⚠️ MEXC WebSocket отключен - используется REST API")
                self.connections['mexc'] = None  # Помечаем как неактивный
                # Запускаем REST API polling для MEXC
                asyncio.create_task(self._poll_mexc_rest())
                continue
            elif exchange == 'bybit':
                tasks.append(self._connect_bybit())
            elif exchange == 'huobi':
                tasks.append(self._connect_huobi())
            elif exchange == 'binance':
                tasks.append(self._connect_binance())
            elif exchange == 'okx':
                tasks.append(self._connect_okx())
            elif exchange == 'kucoin':
                tasks.append(self._connect_kucoin())
            elif exchange == 'kraken':
                tasks.append(self._connect_kraken())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _poll_mexc_rest(self):
        """Получение данных MEXC через REST API"""
        logger.info("🔄 Запуск REST API polling для MEXC")
        
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
                                        formatted_symbol = f"{base}/USDT"
                                        
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
                            
                            self.message_counts['mexc'] += len(mexc_symbols)
                            logger.debug(f"📊 MEXC REST: Обновлено {len(mexc_symbols)} пар")
                
                # Пауза между запросами (учитываем rate limits)
                await asyncio.sleep(2)  # Обновляем каждые 2 секунды
                
            except Exception as e:
                logger.error(f"Ошибка MEXC REST API: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        """Остановка всех соединений"""
        logger.info("Остановка WebSocket соединений...")
        self.running = False
        
        for exchange_id, ws in self.connections.items():
            try:
                if ws:  # Проверяем что соединение существует
                    await ws.close()
                    logger.info(f"✅ {exchange_id} WebSocket закрыт")
            except:
                pass
        
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
            logger.info("✅ MEXC WebSocket подключен")
            
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
                        symbol=f"{symbol[:-4]}/USDT",  # Конвертируем BTCUSDT -> BTC/USDT
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
        """Bybit WebSocket подключение"""
        url = EXCHANGES_CONFIG['bybit']['ws_url']
        
        async with websockets.connect(
            url,
            ping_interval=WEBSOCKET_CONFIG['ping_interval'],
            ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
        ) as ws:
            self.connections['bybit'] = ws
            self.reconnect_delays['bybit'] = WEBSOCKET_CONFIG['reconnect_delay']
            logger.info("✅ Bybit WebSocket подключен")
            
            # Подписка на символы
            symbols_to_subscribe = []
            for symbol in self.symbols[:30]:
                bybit_symbol = symbol.replace('/', '').upper()
                symbols_to_subscribe.append(f"orderbook.1.{bybit_symbol}")
                symbols_to_subscribe.append(f"tickers.{bybit_symbol}")
            
            sub_msg = {
                "op": "subscribe",
                "args": symbols_to_subscribe
            }
            await ws.send(json.dumps(sub_msg))
            
            # Обработка сообщений
            async for message in ws:
                try:
                    data = json.loads(message)
                    self.message_counts['bybit'] += 1
                    
                    # Обработка ping/pong
                    if data.get('op') == 'ping':
                        pong = {"op": "pong"}
                        await ws.send(json.dumps(pong))
                    
                    elif 'topic' in data:
                        await self._process_bybit_message(data)
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки Bybit: {e}")
    
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
                        symbol=formatted_symbol,
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
                    symbol=formatted_symbol,
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
        url = EXCHANGES_CONFIG['huobi']['ws_url']
        
        async with websockets.connect(url) as ws:
            self.connections['huobi'] = ws
            self.reconnect_delays['huobi'] = WEBSOCKET_CONFIG['reconnect_delay']
            logger.info("✅ Huobi WebSocket подключен")
            
            # Подписка на символы
            for symbol in self.symbols[:30]:
                huobi_symbol = symbol.replace('/', '').lower()
                
                # BBO (Best Bid Offer)
                sub_msg = {
                    "sub": f"market.{huobi_symbol}.bbo",
                    "id": f"bbo_{huobi_symbol}"
                }
                await ws.send(json.dumps(sub_msg))
                
                # Depth
                depth_msg = {
                    "sub": f"market.{huobi_symbol}.depth.step0",
                    "id": f"depth_{huobi_symbol}"
                }
                await ws.send(json.dumps(depth_msg))
                await asyncio.sleep(0.1)
            
            # Обработка сообщений
            async for message in ws:
                try:
                    # Huobi использует gzip сжатие
                    data = gzip.decompress(message)
                    data = json.loads(data)
                    self.message_counts['huobi'] += 1
                    
                    # Отвечаем на ping
                    if 'ping' in data:
                        pong = {'pong': data['ping']}
                        await ws.send(json.dumps(pong))
                        self.last_ping['huobi'] = time.time()
                    
                    elif 'ch' in data:
                        await self._process_huobi_message(data)
                        
                except Exception as e:
                    logger.error(f"Ошибка обработки Huobi: {e}")
    
    async def _process_huobi_message(self, data: Dict):
        """Обработка сообщения Huobi"""
        try:
            channel = data['ch']
            
            if 'bbo' in channel:
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
                    symbol=formatted_symbol,
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
                        symbol=formatted_symbol,
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
        """Binance WebSocket подключение (с прокси)"""
        url = EXCHANGES_CONFIG['binance']['ws_url']
        
        try:
            # Binance работает без API ключей для публичных данных
            async with websockets.connect(
                url,
                ping_interval=WEBSOCKET_CONFIG['ping_interval'],
                ping_timeout=WEBSOCKET_CONFIG['ping_timeout']
            ) as ws:
                self.connections['binance'] = ws
                self.reconnect_delays['binance'] = WEBSOCKET_CONFIG['reconnect_delay']
                logger.info("✅ Binance WebSocket подключен")
                
                # Подписка на символы - Binance формат
                symbols_to_subscribe = []
                for symbol in self.symbols[:30]:
                    binance_symbol = symbol.replace('/', '').lower()
                    symbols_to_subscribe.append(f"{binance_symbol}@ticker")
                    symbols_to_subscribe.append(f"{binance_symbol}@depth5@100ms")
                
                sub_msg = {
                    "method": "SUBSCRIBE",
                    "params": symbols_to_subscribe,
                    "id": 1
                }
                await ws.send(json.dumps(sub_msg))
                logger.info(f"📡 Binance подписался на {len(symbols_to_subscribe)} потоков")
                
                # Обработка сообщений
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self.message_counts['binance'] += 1
                        
                        if 'stream' in data:
                            await self._process_binance_message(data)
                            
                    except Exception as e:
                        logger.error(f"Ошибка обработки Binance: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Binance WebSocket ошибка: {e}")
            raise
    
    async def _connect_okx(self):
        """OKX WebSocket подключение"""
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
                
                # Подписка на символы - OKX формат
                args = []
                for symbol in self.symbols[:30]:
                    okx_symbol = symbol.replace('/', '-').upper()
                    args.append({"channel": "tickers", "instId": okx_symbol})
                    args.append({"channel": "books5", "instId": okx_symbol})
                
                sub_msg = {
                    "op": "subscribe",
                    "args": args
                }
                await ws.send(json.dumps(sub_msg))
                logger.info(f"📡 OKX подписался на {len(args)} каналов")
                
                # Обработка сообщений
                async for message in ws:
                    try:
                        data = json.loads(message)
                        self.message_counts['okx'] += 1
                        
                        if 'data' in data:
                            await self._process_okx_message(data)
                            
                    except Exception as e:
                        logger.error(f"Ошибка обработки OKX: {e}")
                        
        except Exception as e:
            logger.error(f"❌ OKX WebSocket ошибка: {e}")
            raise
    
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
                for symbol in self.symbols[:30]:
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
                
                logger.info(f"📡 KuCoin подписался на {len(self.symbols[:30]) * 2} топиков")
                
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
                for symbol in self.symbols[:30]:
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
                    symbol=formatted_symbol,
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
                        symbol=formatted_symbol,
                        exchange='binance',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга Binance: {e}")
    
    async def _process_okx_message(self, data: Dict):
        """Обработка сообщения OKX"""
        try:
            for item in data['data']:
                channel = data['arg']['channel']
                symbol = data['arg']['instId'].replace('-', '/')
                
                if channel == 'tickers':
                    orderbook = OrderBook(
                        symbol=symbol,
                        exchange='okx',
                        bids=[(float(item['bidPx']), float(item['bidSz']))],
                        asks=[(float(item['askPx']), float(item['askSz']))],
                        timestamp=time.time()
                    )
                    
                    if self.on_orderbook_update:
                        await self.on_orderbook_update(orderbook)
                        
                elif channel == 'books5':
                    bids = [(float(b[0]), float(b[1])) for b in item.get('bids', [])]
                    asks = [(float(a[0]), float(a[1])) for a in item.get('asks', [])]
                    
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
            logger.error(f"Ошибка парсинга OKX: {e}")
    
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
