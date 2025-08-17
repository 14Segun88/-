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
        
    async def start(self, symbols: List[str]):
        """Запуск WebSocket соединений"""
        self.running = True
        self.symbols = symbols
        logger.info(f"🚀 Запуск WebSocket для {len(symbols)} символов")
        
        tasks = []
        for exchange_id, config in EXCHANGES_CONFIG.items():
            if config['enabled']:
                tasks.append(self._connect_exchange(exchange_id))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop(self):
        """Остановка всех соединений"""
        logger.info("Остановка WebSocket соединений...")
        self.running = False
        
        for exchange_id, ws in self.connections.items():
            try:
                await ws.close()
                logger.info(f"✅ {exchange_id} WebSocket закрыт")
            except:
                pass
        
        self.connections.clear()
    
    async def _connect_exchange(self, exchange_id: str):
        """Подключение к конкретной бирже"""
        config = EXCHANGES_CONFIG[exchange_id]
        
        while self.running:
            try:
                logger.info(f"🔌 Подключение к {config['name']} WebSocket...")
                
                # Выбор метода подключения
                if exchange_id == 'mexc':
                    await self._connect_mexc()
                elif exchange_id == 'bybit':
                    await self._connect_bybit()
                elif exchange_id == 'huobi':
                    await self._connect_huobi()
                elif exchange_id == 'binance':
                    await self._connect_binance()
                elif exchange_id == 'okx':
                    await self._connect_okx()
                elif exchange_id == 'kucoin':
                    await self._connect_kucoin()
                elif exchange_id == 'kraken':
                    await self._connect_kraken()
                    
            except Exception as e:
                self.error_counts[exchange_id] += 1
                logger.error(f"❌ Ошибка WebSocket {config['name']}: {e}")
                
                delay = self.reconnect_delays[exchange_id]
                logger.info(f"🔄 Переподключение через {delay} сек...")
                await asyncio.sleep(delay)
                
                # Экспоненциальная задержка
                self.reconnect_delays[exchange_id] = min(
                    delay * 2, 
                    WEBSOCKET_CONFIG['max_reconnect_delay']
                )
    
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
            
            # Подписка на символы
            symbols_to_subscribe = [s.replace('/', '').upper() for s in self.symbols 
                                   if 'USDT' in s][:30]
            
            for symbol in symbols_to_subscribe:
                sub_msg = {
                    "method": "SUBSCRIPTION",
                    "params": [
                        f"spot@public.bookTicker.v3.api@{symbol}",
                        f"spot@public.depth.v3.api@{symbol}@5"
                    ]
                }
                await ws.send(json.dumps(sub_msg))
                await asyncio.sleep(0.1)  # Избегаем спама
            
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
            if 'bookTicker' in str(data.get('c', '')):
                ticker = data['d']
                symbol = ticker['s']
                
                orderbook = OrderBook(
                    symbol=f"{symbol[:-4]}/USDT",  # Конвертируем обратно
                    exchange='mexc',
                    bids=[(float(ticker['b']), float(ticker['B']))],
                    asks=[(float(ticker['a']), float(ticker['A']))],
                    timestamp=time.time()
                )
                
                if self.on_orderbook_update:
                    await self.on_orderbook_update(orderbook)
                    
            elif 'depth' in str(data.get('c', '')):
                depth = data['d']
                symbol = data['s'] if 's' in data else data['c'].split('@')[3]
                
                bids = [(float(b[0]), float(b[1])) for b in depth.get('bids', [])]
                asks = [(float(a[0]), float(a[1])) for a in depth.get('asks', [])]
                
                if bids and asks:
                    orderbook = OrderBook(
                        symbol=f"{symbol[:-4]}/USDT",
                        exchange='mexc',
                        bids=bids[:5],
                        asks=asks[:5],
                        timestamp=time.time()
                    )
                    
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
        if not API_KEYS['binance']['apiKey']:
            logger.warning("⚠️ Binance API ключи отсутствуют")
            return
            
        url = EXCHANGES_CONFIG['binance']['ws_url']
        
        # Настройка прокси если нужно
        connector = None
        if EXCHANGES_CONFIG['binance']['use_proxy'] and PROXY_CONFIG['enabled']:
            # Используем aiohttp с прокси для WebSocket
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(PROXY_CONFIG['ws'])
        
        # TODO: Реализовать подключение через прокси
        logger.info("⚠️ Binance WebSocket требует прокси настройки")
    
    async def _connect_okx(self):
        """OKX WebSocket подключение"""
        if not API_KEYS['okx']['apiKey']:
            logger.warning("⚠️ OKX API ключи отсутствуют")
            return
            
        # TODO: Реализовать OKX WebSocket
        logger.info("⚠️ OKX WebSocket будет добавлен")
    
    async def _connect_kucoin(self):
        """KuCoin WebSocket подключение"""
        if not API_KEYS['kucoin']['apiKey']:
            logger.warning("⚠️ KuCoin API ключи отсутствуют")
            return
            
        # TODO: Реализовать KuCoin WebSocket
        logger.info("⚠️ KuCoin WebSocket будет добавлен")
    
    async def _connect_kraken(self):
        """Kraken WebSocket подключение"""
        if not API_KEYS['kraken']['apiKey']:
            logger.warning("⚠️ Kraken API ключи отсутствуют")
            return
            
        # TODO: Реализовать Kraken WebSocket
        logger.info("⚠️ Kraken WebSocket будет добавлен")
    
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
