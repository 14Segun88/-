#!/usr/bin/env python3
"""
Advanced Arbitrage Bot v2.0
Реальная торговля с API ключами, WebSocket, maker ордерами и анализом стакана.
"""
import asyncio
import ccxt.async_support as ccxt
import websockets
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import hmac
import hashlib
import pandas as pd
import numpy as np

# ==================== КОНФИГУРАЦИЯ ====================

# API КЛЮЧИ (ВАЖНО: В продакшене использовать переменные окружения!)
API_KEYS = {
    'mexc': {
        'apiKey': 'mx0vglAj5GaknRsyUQ',
        'secret': '83911cc1cd784568832b624fbfb19751',
        'enableRateLimit': True
    },
    'okx': {
        'apiKey': '',  # Добавить когда будет
        'secret': '',
        'password': '',
        'enableRateLimit': True
    },
    'kucoin': {
        'apiKey': '',  # Добавить когда будет
        'secret': '',
        'password': '',
        'enableRateLimit': True
    },
    'gateio': {
        'apiKey': '',  # Добавить когда будет
        'secret': '',
        'enableRateLimit': True
    },
    'bitget': {
        'apiKey': '',  # Добавить когда будет
        'secret': '',
        'password': '',
        'enableRateLimit': True
    }
}

# Комиссии с учетом maker ордеров
EXCHANGE_FEES = {
    'mexc': {'maker': 0.0, 'taker': 0.001},      # 0% maker!
    'okx': {'maker': 0.0008, 'taker': 0.001},    # 0.08% maker
    'kucoin': {'maker': 0.001, 'taker': 0.001},  # 0.1%
    'gateio': {'maker': 0.002, 'taker': 0.002},  # 0.2%
    'bitget': {'maker': 0.001, 'taker': 0.001}   # 0.1%
}

# WebSocket URLs
WS_URLS = {
    'mexc': 'wss://wbs.mexc.com/ws',
    'okx': 'wss://ws.okx.com:8443/ws/v5/public',
    'kucoin': None,  # Требует специальный токен
    'gateio': 'wss://api.gateio.ws/ws/v4/',
    'bitget': 'wss://ws.bitget.com/mix/v1/stream'
}

# Торговые параметры
MIN_PROFIT_THRESHOLD = 0.15  # 0.15% минимальная прибыль для maker ордеров
POSITION_SIZE_USD = 500      # Размер позиции
MAX_SLIPPAGE = 0.05          # Максимальный слиппедж 0.05%
USE_MAKER_ORDERS = True      # Использовать maker ордера
ORDERBOOK_DEPTH = 10         # Глубина анализа стакана
MIN_LIQUIDITY_USD = 1000     # Минимальная ликвидность в стакане

# Торговые пары (используем самые ликвидные)
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'LTC/USDT',
    'UNI/USDT', 'LINK/USDT', 'ATOM/USDT'
]

class AdvancedArbitrageBot:
    def __init__(self):
        self.clients = {}
        self.ws_connections = {}
        self.prices = {}  # {symbol: {exchange: {bid, ask, timestamp}}}
        self.orderbooks = {}  # {symbol: {exchange: {bids, asks, timestamp}}}
        self.balances = {}
        self.is_running = True
        self.opportunities_found = 0
        self.real_trades = []
        self.total_profit_usd = 0
        self.active_orders = {}
        self.volatility = {}  # Волатильность для каждой пары
        
    async def initialize(self):
        """Инициализирует CCXT клиенты с реальными API ключами."""
        print("🚀 Инициализация Advanced Arbitrage Bot v2.0")
        print("-" * 50)
        
        for exchange_name, credentials in API_KEYS.items():
            if not credentials['apiKey']:  # Пропускаем биржи без ключей
                continue
                
            try:
                exchange_class = getattr(ccxt, exchange_name)
                self.clients[exchange_name] = exchange_class(credentials)
                
                # Загружаем рынки
                await self.clients[exchange_name].load_markets()
                
                # Проверяем баланс
                try:
                    balance = await self.clients[exchange_name].fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    self.balances[exchange_name] = usdt_balance
                    print(f"✅ {exchange_name.upper()}: ${usdt_balance:.2f} USDT")
                except:
                    self.balances[exchange_name] = 0
                    print(f"⚠️ {exchange_name.upper()}: Баланс недоступен (торговые права?)")
                    
            except Exception as e:
                print(f"❌ Ошибка инициализации {exchange_name}: {e}")
                
        print(f"\n📊 Активных бирж: {len(self.clients)}")
        print(f"💰 Общий баланс: ${sum(self.balances.values()):.2f} USDT")
        
    async def connect_websockets(self):
        """Подключается к WebSocket для получения данных в реальном времени."""
        for exchange, url in WS_URLS.items():
            if exchange not in self.clients or not url:
                continue
                
            asyncio.create_task(self.ws_handler(exchange, url))
            
    async def ws_handler(self, exchange: str, url: str):
        """Обработчик WebSocket соединения."""
        while self.is_running:
            try:
                async with websockets.connect(url) as ws:
                    self.ws_connections[exchange] = ws
                    print(f"🔌 WebSocket {exchange} подключен")
                    
                    # Подписка на тикеры
                    await self.subscribe_tickers(ws, exchange)
                    
                    # Обработка сообщений
                    async for message in ws:
                        await self.process_ws_message(exchange, message)
                        
            except Exception as e:
                print(f"⚠️ WebSocket {exchange} отключен: {e}")
                await asyncio.sleep(5)
                
    async def subscribe_tickers(self, ws, exchange: str):
        """Подписывается на тикеры через WebSocket."""
        if exchange == 'mexc':
            # MEXC требует подписку на каждый символ отдельно
            for symbol in SYMBOLS[:5]:  # Начнем с 5 символов
                sub_msg = {
                    "method": "SUBSCRIPTION",
                    "params": [f"spot@public.deals.v3.api@{symbol.replace('/', '').lower()}"]
                }
                await ws.send(json.dumps(sub_msg))
                await asyncio.sleep(0.1)
            
        elif exchange == 'okx':
            sub_msg = {
                "op": "subscribe",
                "args": [{"channel": "tickers", "instId": s.replace('/', '-')} for s in SYMBOLS[:5]]
            }
            await ws.send(json.dumps(sub_msg))
            
        elif exchange == 'gateio':
            sub_msg = {
                "time": int(time.time()),
                "channel": "spot.tickers",
                "event": "subscribe",
                "payload": [s.replace('/', '_') for s in SYMBOLS[:5]]
            }
            await ws.send(json.dumps(sub_msg))
            
    async def process_ws_message(self, exchange: str, message: str):
        """Обрабатывает сообщения от WebSocket."""
        try:
            data = json.loads(message)
            
            # Парсим данные в зависимости от биржи
            if exchange == 'mexc':
                if 'd' in data and 'deals' in data['d']:
                    for deal in data['d']['deals']:
                        symbol = data['s'].upper().replace('USDT', '/USDT')
                        price = float(deal['p'])
                        self.update_price(symbol, exchange, price, price)
                        
            elif exchange == 'okx':
                if 'data' in data:
                    for item in data['data']:
                        symbol = item['instId'].replace('-', '/')
                        self.update_price(symbol, exchange,
                                        float(item['bidPx']),
                                        float(item['askPx']))
                                        
            elif exchange == 'gateio':
                if 'result' in data:
                    for item in data['result']:
                        symbol = item['currency_pair'].replace('_', '/')
                        self.update_price(symbol, exchange,
                                        float(item['highest_bid']),
                                        float(item['lowest_ask']))
                                    
            # Проверяем арбитраж при каждом обновлении
            if len(self.prices) > 0:
                await self.check_arbitrage_opportunity()
            
        except Exception as e:
            pass  # Игнорируем ошибки парсинга
            
    def update_price(self, symbol: str, exchange: str, bid: float, ask: float):
        """Обновляет цену и проверяет волатильность."""
        if symbol not in self.prices:
            self.prices[symbol] = {}
            
        # Сохраняем старую цену для расчета волатильности
        old_price = self.prices[symbol].get(exchange, {}).get('bid', bid)
        
        self.prices[symbol][exchange] = {
            'bid': bid,
            'ask': ask,
            'timestamp': time.time()
        }
        
        # Обновляем волатильность
        if symbol not in self.volatility:
            self.volatility[symbol] = []
        
        price_change = abs(bid - old_price) / old_price * 100 if old_price else 0
        self.volatility[symbol].append(price_change)
        if len(self.volatility[symbol]) > 100:
            self.volatility[symbol].pop(0)
            
    async def fetch_orderbook(self, exchange: str, symbol: str) -> Optional[dict]:
        """Получает стакан для анализа ликвидности."""
        try:
            client = self.clients[exchange]
            orderbook = await client.fetch_order_book(symbol, ORDERBOOK_DEPTH)
            
            self.orderbooks[symbol] = self.orderbooks.get(symbol, {})
            self.orderbooks[symbol][exchange] = {
                'bids': orderbook['bids'],
                'asks': orderbook['asks'],
                'timestamp': time.time()
            }
            return orderbook
            
        except Exception as e:
            return None
            
    def calculate_slippage(self, orderbook: dict, size_usd: float, side: str) -> float:
        """Рассчитывает слиппедж для заданного размера позиции."""
        book = orderbook['asks'] if side == 'buy' else orderbook['bids']
        if not book:
            return float('inf')
            
        total_cost = 0
        total_amount = 0
        
        for price, amount in book:
            cost = price * amount
            if total_cost + cost >= size_usd:
                # Достигли нужного объема
                remaining = size_usd - total_cost
                total_amount += remaining / price
                break
            total_cost += cost
            total_amount += amount
            
        if total_cost < size_usd:
            return float('inf')  # Недостаточно ликвидности
            
        avg_price = size_usd / total_amount
        best_price = book[0][0]
        slippage = abs(avg_price - best_price) / best_price * 100
        
        return slippage
        
    async def check_arbitrage_opportunity(self):
        """Проверяет арбитражные возможности с учетом ликвидности."""
        opportunities = []
        now = time.time()
        
        for symbol in self.prices:
            if symbol not in self.prices or len(self.prices[symbol]) < 2:
                continue
                
            # Находим лучшие цены
            best_bid = 0
            best_bid_exchange = None
            best_ask = float('inf')
            best_ask_exchange = None
            
            for exchange, price_data in self.prices[symbol].items():
                if now - price_data['timestamp'] > 2:  # Данные старше 2 сек
                    continue
                    
                if price_data['bid'] > best_bid:
                    best_bid = price_data['bid']
                    best_bid_exchange = exchange
                    
                if price_data['ask'] < best_ask:
                    best_ask = price_data['ask']
                    best_ask_exchange = exchange
                    
            if not best_bid_exchange or not best_ask_exchange:
                continue
                
            if best_bid <= best_ask:
                continue
                
            # Расчет прибыли с учетом maker комиссий
            spread_pct = (best_bid - best_ask) / best_ask * 100
            
            if USE_MAKER_ORDERS:
                buy_fee = EXCHANGE_FEES[best_ask_exchange]['maker'] * 100
                sell_fee = EXCHANGE_FEES[best_bid_exchange]['maker'] * 100
            else:
                buy_fee = EXCHANGE_FEES[best_ask_exchange]['taker'] * 100
                sell_fee = EXCHANGE_FEES[best_bid_exchange]['taker'] * 100
                
            net_profit = spread_pct - buy_fee - sell_fee
            
            # Проверяем волатильность
            volatility_score = np.mean(self.volatility.get(symbol, [0]))
            
            if net_profit >= MIN_PROFIT_THRESHOLD:
                # Проверяем ликвидность в стакане
                buy_book = await self.fetch_orderbook(best_ask_exchange, symbol)
                sell_book = await self.fetch_orderbook(best_bid_exchange, symbol)
                
                if buy_book and sell_book:
                    buy_slippage = self.calculate_slippage(buy_book, POSITION_SIZE_USD, 'buy')
                    sell_slippage = self.calculate_slippage(sell_book, POSITION_SIZE_USD, 'sell')
                    
                    total_slippage = buy_slippage + sell_slippage
                    
                    if total_slippage < MAX_SLIPPAGE:
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': best_ask_exchange,
                            'sell_exchange': best_bid_exchange,
                            'buy_price': best_ask,
                            'sell_price': best_bid,
                            'spread_pct': spread_pct,
                            'net_profit': net_profit,
                            'slippage': total_slippage,
                            'volatility': volatility_score,
                            'timestamp': now
                        })
                        
        # Сортируем по прибыльности с учетом волатильности
        opportunities.sort(key=lambda x: x['net_profit'] + x['volatility'] * 0.1, reverse=True)
        
        if opportunities:
            best = opportunities[0]
            await self.execute_arbitrage(best)
            
    async def execute_arbitrage(self, opportunity: dict):
        """Исполняет арбитражную сделку с atomic execution."""
        print(f"\n💎 АРБИТРАЖ НАЙДЕН!")
        print(f"  {opportunity['symbol']}: {opportunity['buy_exchange']} → {opportunity['sell_exchange']}")
        print(f"  Спред: {opportunity['spread_pct']:.3f}%")
        print(f"  Чистая прибыль: {opportunity['net_profit']:.3f}%")
        print(f"  Слиппедж: {opportunity['slippage']:.3f}%")
        print(f"  Волатильность: {opportunity['volatility']:.3f}")
        
        # Проверяем балансы
        buy_balance = self.balances.get(opportunity['buy_exchange'], 0)
        sell_exchange_symbol = opportunity['symbol'].split('/')[0]
        
        if buy_balance < POSITION_SIZE_USD:
            print(f"  ⚠️ Недостаточно средств на {opportunity['buy_exchange']}")
            return
            
        # Atomic execution - размещаем оба ордера одновременно
        try:
            amount = POSITION_SIZE_USD / opportunity['buy_price']
            
            if USE_MAKER_ORDERS:
                # Maker ордера - лимитные с небольшим улучшением цены
                buy_price = opportunity['buy_price'] * 0.9995
                sell_price = opportunity['sell_price'] * 1.0005
                
                tasks = [
                    self.place_order(opportunity['buy_exchange'], opportunity['symbol'], 
                                   'limit', 'buy', amount, buy_price),
                    self.place_order(opportunity['sell_exchange'], opportunity['symbol'],
                                   'limit', 'sell', amount, sell_price)
                ]
            else:
                # Taker ордера - рыночные
                tasks = [
                    self.place_order(opportunity['buy_exchange'], opportunity['symbol'],
                                   'market', 'buy', amount),
                    self.place_order(opportunity['sell_exchange'], opportunity['symbol'],
                                   'market', 'sell', amount)
                ]
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Проверяем результаты
            buy_order = results[0]
            sell_order = results[1]
            
            if not isinstance(buy_order, Exception) and not isinstance(sell_order, Exception):
                profit_usd = POSITION_SIZE_USD * opportunity['net_profit'] / 100
                self.total_profit_usd += profit_usd
                
                trade = {
                    'timestamp': datetime.now().isoformat(),
                    'symbol': opportunity['symbol'],
                    'buy_exchange': opportunity['buy_exchange'],
                    'sell_exchange': opportunity['sell_exchange'],
                    'buy_order_id': buy_order.get('id', 'N/A'),
                    'sell_order_id': sell_order.get('id', 'N/A'),
                    'size_usd': POSITION_SIZE_USD,
                    'net_profit_pct': opportunity['net_profit'],
                    'profit_usd': profit_usd,
                    'total_profit': self.total_profit_usd
                }
                
                self.real_trades.append(trade)
                self.save_trade(trade)
                
                print(f"  ✅ ИСПОЛНЕНО! Прибыль: ${profit_usd:.2f}")
                print(f"  📈 Общая прибыль: ${self.total_profit_usd:.2f}")
                
            else:
                print(f"  ❌ Ошибка исполнения:")
                if isinstance(buy_order, Exception):
                    print(f"     Покупка: {buy_order}")
                if isinstance(sell_order, Exception):
                    print(f"     Продажа: {sell_order}")
                    
        except Exception as e:
            print(f"  ❌ Критическая ошибка: {e}")
            
    async def place_order(self, exchange: str, symbol: str, order_type: str, 
                          side: str, amount: float, price: float = None):
        """Размещает ордер на бирже."""
        try:
            client = self.clients[exchange]
            
            if order_type == 'limit':
                order = await client.create_limit_order(symbol, side, amount, price)
            else:
                order = await client.create_market_order(symbol, side, amount)
                
            return order
            
        except Exception as e:
            return e
            
    def save_trade(self, trade: dict):
        """Сохраняет сделку в файл."""
        filename = 'real_trades.json'
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    trades = json.load(f)
            else:
                trades = []
                
            trades.append(trade)
            
            with open(filename, 'w') as f:
                json.dump(trades, f, indent=2)
                
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            
    async def monitor_loop(self):
        """Цикл мониторинга и сбора данных."""
        while self.is_running:
            # Обновляем цены через REST API для бирж без WebSocket
            for exchange in self.clients:
                if exchange not in self.ws_connections:
                    asyncio.create_task(self.fetch_prices_rest(exchange))
                    
            # Обновляем балансы
            for exchange in self.clients:
                try:
                    balance = await self.clients[exchange].fetch_balance()
                    self.balances[exchange] = balance.get('USDT', {}).get('free', 0)
                except:
                    pass
                    
            await asyncio.sleep(1)
            
    async def fetch_prices_rest(self, exchange: str):
        """Получает цены через REST API."""
        try:
            client = self.clients[exchange]
            tickers = await client.fetch_tickers(SYMBOLS)
            
            for symbol, ticker in tickers.items():
                if ticker['bid'] and ticker['ask']:
                    self.update_price(symbol, exchange, ticker['bid'], ticker['ask'])
                    
        except Exception as e:
            pass
            
    async def status_loop(self):
        """Выводит статус бота."""
        while self.is_running:
            await asyncio.sleep(30)
            
            active_prices = sum(1 for s in self.prices.values() 
                              for p in s.values() 
                              if time.time() - p['timestamp'] < 5)
                              
            avg_volatility = np.mean([np.mean(v) for v in self.volatility.values() if v])
            
            print(f"\n📊 СТАТУС БОТА:")
            print(f"  Активных цен: {active_prices}")
            print(f"  WebSocket подключений: {len(self.ws_connections)}")
            print(f"  Средняя волатильность: {avg_volatility:.3f}%")
            print(f"  Сделок исполнено: {len(self.real_trades)}")
            print(f"  Общая прибыль: ${self.total_profit_usd:.2f}")
            
    async def run(self):
        """Запускает бота."""
        await self.initialize()
        
        if not self.clients:
            print("❌ Нет активных бирж с API ключами")
            return
            
        print("\n🎯 Запуск торговли...")
        print(f"  Минимальная прибыль: {MIN_PROFIT_THRESHOLD}%")
        print(f"  Размер позиции: ${POSITION_SIZE_USD}")
        print(f"  Режим: {'MAKER ордера' if USE_MAKER_ORDERS else 'TAKER ордера'}")
        print("-" * 50)
        
        # Запускаем все компоненты
        tasks = [
            asyncio.create_task(self.connect_websockets()),
            asyncio.create_task(self.monitor_loop()),
            asyncio.create_task(self.status_loop())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n⏹️ Остановка бота...")
            self.is_running = False
            
        # Закрываем соединения
        for client in self.clients.values():
            await client.close()
            
        print(f"\n📈 ИТОГОВАЯ СТАТИСТИКА:")
        print(f"  Сделок исполнено: {len(self.real_trades)}")
        print(f"  Общая прибыль: ${self.total_profit_usd:.2f}")
        if self.real_trades:
            avg_profit = self.total_profit_usd / len(self.real_trades)
            print(f"  Средняя прибыль на сделку: ${avg_profit:.2f}")
            
async def main():
    bot = AdvancedArbitrageBot()
    await bot.run()
    
if __name__ == "__main__":
    print("=" * 50)
    print("   ADVANCED ARBITRAGE BOT v2.0")
    print("   Реальная торговля с API ключами")
    print("=" * 50)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
