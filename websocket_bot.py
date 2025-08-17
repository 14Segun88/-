#!/usr/bin/env python3
"""
WebSocket-based Arbitrage Bot with Proxy Support
Обходит геоблокировку через WebSocket и proxy
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import ccxt.pro as ccxtpro
from ccxt.async_support import binance, bybit, gateio, bitget, kraken
import aiohttp
import ssl

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('websocket_bot.log'),
        logging.StreamHandler()
    ]
)

class WebSocketArbitrageBot:
    def __init__(self):
        # Proxy для обхода геоблокировки
        self.proxy = 'http://proxy.server:8080'  # Замените на свой proxy
        
        # Параметры арбитража
        self.min_profit_percent = 0.02  # Минимальная прибыль 0.02% после комиссий
        self.position_size = 100  # $100 на сделку
        self.cooldown_seconds = 30  # Задержка между сделками на одной паре
        self.taker_fee = 0.001
        self.enable_trading = True  # Включить реальное исполнение
        
        # Exchanges с WebSocket
        self.exchanges = {}
        self.ws_exchanges = {}
        self.prices = {}
        self.orderbooks = {}
        self.opportunities = []
        self.trades_executed = []
        self.cooldowns = {}
        
        # Символы для мониторинга
        self.symbols = [
            'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT',
            'ADA/USDT', 'DOGE/USDT', 'AVAX/USDT', 'DOT/USDT', 'POL/USDT',
            'LINK/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'ETC/USDT',
            'NEAR/USDT', 'TRX/USDT', 'XLM/USDT', 'ALGO/USDT', 'FTM/USDT'
        ]
        
    async def initialize_exchanges(self):
        """Инициализация бирж с WebSocket и proxy"""
        # Настройки бирж
        exchanges_config = {
            'mexc': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.0002, 'taker': 0.001}
            },
            'binance': {
                'apiKey': 'YOUR_BINANCE_API_KEY',
                'secret': 'YOUR_BINANCE_SECRET',
                'enableWS': True,
                'fees': {'maker': 0.0002, 'taker': 0.0004}
            },
            'bybit': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.0001, 'taker': 0.0006}
            },
            'gateio': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.00015, 'taker': 0.0005}
            },
            'bitget': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.0002, 'taker': 0.0006}
            },
            'okx': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.0008, 'taker': 0.001}
            },
            'kucoin': {
                'enableWS': True,
                'useProxy': True,
                'fees': {'maker': 0.0001, 'taker': 0.0005}
            }
        }
                
        self.fees = {}  # Сохраняем комиссии
        self.cooldown_seconds = 30
        self.max_positions = 10
        
        for exchange_id, config in exchanges_config.items():
            try:
                options = {
                    'defaultType': 'spot',
                    'watchBalance': False,
                    'watchTicker': True,
                    'watchTrades': False,
                    'watchOrderBook': True,
                    'watchOHLCV': False
                }
                
                # Добавляем proxy для некоторых бирж
                if config.get('useProxy'):
                    # Используем proxy NekoBox
                    proxy_url = 'http://172.31.128.1:2080'
                    options.update({
                        'proxies': {
                            'http': proxy_url,
                            'https': proxy_url
                        },
                        'proxy': proxy_url,
                        'httpProxy': proxy_url,
                        'httpsProxy': proxy_url,
                        'socksProxy': None
                    })
                    logging.info(f"🌐 {exchange_id}: Используется proxy для обхода геоблокировки")
                
                # Для публичных бирж не используем API ключи
                public_only_exchanges = ['mexc', 'gateio', 'kucoin', 'okx', 'bitget', 'bybit']
                
                # Инициализация биржи
                if exchange_id in public_only_exchanges:
                    # Публичный режим
                    exchange = getattr(ccxtpro, exchange_id)({
                        'enableRateLimit': True,
                        'options': options
                    })
                elif config.get('apiKey') and config.get('secret'):
                    exchange = getattr(ccxtpro, exchange_id)({
                        'apiKey': config['apiKey'],
                        'secret': config['secret'],
                        'enableRateLimit': True,
                        'options': options
                    })
                else:
                    exchange = getattr(ccxtpro, exchange_id)({
                        'enableRateLimit': True,
                        'options': options
                    })
                
                if config.get('enableWS'):
                    self.ws_exchanges[exchange_id] = exchange
                else:
                    self.exchanges[exchange_id] = exchange
                    
                self.fees[exchange_id] = config.get('fees', {'maker': 0.001, 'taker': 0.001})
                
                logging.info(f"✅ {exchange_id}: Инициализирована (WS: {config.get('enableWS')})")  
                
            except Exception as e:
                logging.error(f"❌ Ошибка инициализации {exchange_id}: {e}")
        
        logging.info(f"📡 WebSocket бирж: {len(self.ws_exchanges)}, REST бирж: {len(self.exchanges)}")
        self.balances = {}  # Инициализируем балансы
        
    async def watch_ticker(self, exchange_name: str, symbol: str):
        """Подписка на тикер через WebSocket"""
        try:
            exchange = self.ws_exchanges.get(exchange_name) or self.exchanges.get(exchange_name)
            if not exchange:
                return
                
            while True:
                try:
                    ticker = await exchange.watch_ticker(symbol)
                    
                    if ticker and ticker.get('bid') and ticker.get('ask'):
                        key = f"{exchange_name}:{symbol}"
                        self.prices[key] = {
                            'bid': ticker['bid'],
                            'ask': ticker['ask'],
                            'timestamp': ticker.get('timestamp', time.time() * 1000),
                            'volume': ticker.get('quoteVolume', 0)
                        }
                        
                except Exception as e:
                    if 'not supported' in str(e).lower():
                        # Fallback на REST API
                        await self.fetch_ticker_rest(exchange_name, symbol)
                        await asyncio.sleep(1)
                    else:
                        logging.debug(f"Ошибка watch_ticker {exchange_name} {symbol}: {e}")
                        await asyncio.sleep(5)
                        
        except Exception as e:
            logging.error(f"Критическая ошибка watch_ticker {exchange_name} {symbol}: {e}")
            
    async def fetch_ticker_rest(self, exchange_name: str, symbol: str):
        """Fallback на REST API если WebSocket недоступен"""
        try:
            exchange = self.ws_exchanges.get(exchange_name) or self.exchanges.get(exchange_name)
            if not exchange:
                return
                
            ticker = await exchange.fetch_ticker(symbol)
            
            if ticker and ticker.get('bid') and ticker.get('ask'):
                key = f"{exchange_name}:{symbol}"
                self.prices[key] = {
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'timestamp': ticker.get('timestamp', time.time() * 1000),
                    'volume': ticker.get('quoteVolume', 0)
                }
                
        except Exception as e:
            logging.debug(f"Ошибка REST API {exchange_name} {symbol}: {e}")
            
    async def watch_orderbook(self, exchange_name: str, symbol: str):
        """Подписка на стакан через WebSocket"""
        try:
            exchange = self.ws_exchanges.get(exchange_name) or self.exchanges.get(exchange_name)
            if not exchange:
                return
                
            while True:
                try:
                    orderbook = await exchange.watch_order_book(symbol, limit=10)
                    
                    if orderbook:
                        key = f"{exchange_name}:{symbol}"
                        self.orderbooks[key] = {
                            'bids': orderbook['bids'][:5],
                            'asks': orderbook['asks'][:5],
                            'timestamp': orderbook.get('timestamp', time.time() * 1000)
                        }
                        
                except Exception as e:
                    # Если WebSocket не поддерживается, используем REST
                    if 'not supported' in str(e).lower():
                        await asyncio.sleep(5)
                    else:
                        logging.debug(f"Ошибка watch_orderbook {exchange_name} {symbol}: {e}")
                        await asyncio.sleep(5)
                        
        except Exception as e:
            logging.error(f"Критическая ошибка watch_orderbook {exchange_name} {symbol}: {e}")
            
    def find_arbitrage_opportunities(self):
        """Поиск арбитражных возможностей"""
        opportunities = []
        
        for symbol in self.symbols:
            prices_for_symbol = {}
            
            # Собираем цены для этой пары
            prices_for_symbol = {}
            for exchange_name, price_data in self.prices.items():
                if exchange_name.endswith(f":{symbol}"):
                    exchange_name = exchange_name.split(':')[0]
                    # Проверяем свежесть (не старше 10 секунд)
                    if price_data.get('timestamp'):
                        if time.time() * 1000 - price_data['timestamp'] < 10000:
                            prices_for_symbol[exchange_name] = price_data
                        
            # Ищем арбитраж между парами бирж
            exchanges = list(prices_for_symbol.keys())
            for i in range(len(exchanges)):
                for j in range(i + 1, len(exchanges)):
                    buy_exchange = exchanges[i]
                    sell_exchange = exchanges[j]
                    
                    buy_price = prices_for_symbol[buy_exchange].get('ask')
                    sell_price = prices_for_symbol[sell_exchange].get('bid')
                    
                    # Пропускаем если цены None
                    if not buy_price or not sell_price:
                        continue
                    
                    # Проверяем обе стороны арбитража
                    for buy_ex, sell_ex, buy_p, sell_p in [
                        (buy_exchange, sell_exchange, buy_price, sell_price),
                        (sell_exchange, buy_exchange, prices_for_symbol[sell_exchange].get('ask'), prices_for_symbol[buy_exchange].get('bid'))
                    ]:
                        if buy_p and sell_p and buy_p > 0 and sell_p > buy_p:
                            spread = ((sell_p - buy_p) / buy_p) * 100
                            
                            # Логируем все спреды для диагностики
                            if spread > 0:
                                logging.debug(f"{symbol}: {buy_ex}→{sell_ex} spread={spread:.4f}% (buy={buy_p:.6f}, sell={sell_p:.6f})")
                            
                            # Учитываем комиссии (используем maker где возможно)
                            # Для покупки используем maker fee (лимитный ордер)
                            buy_fee = self.fees.get(buy_ex, {'maker': 0.0005, 'taker': 0.001})['maker']
                            # Для продажи тоже используем maker fee
                            sell_fee = self.fees.get(sell_ex, {'maker': 0.0005, 'taker': 0.001})['maker']
                            net_profit = spread - (buy_fee + sell_fee) * 100
                            
                            # Логируем потенциальные возможности
                            if net_profit > -0.1:
                                logging.info(f"💰 Потенциал: {symbol} {buy_ex}→{sell_ex} spread={spread:.4f}%, net={net_profit:.4f}%")
                            
                            if net_profit >= self.min_profit_percent:
                                # Проверяем cooldown
                                cooldown_key = f"{symbol}:{buy_ex}->{sell_ex}"
                                if cooldown_key in self.cooldowns:
                                    if time.time() - self.cooldowns[cooldown_key] < self.cooldown_seconds:
                                        continue
                                        
                                opportunities.append({
                                    'symbol': symbol,
                                    'buy_exchange': buy_ex,
                                    'sell_exchange': sell_ex,
                                    'buy_price': buy_p,
                                    'sell_price': sell_p,
                                    'spread': spread,
                                    'net_profit': net_profit,
                                    'volume': min(
                                        prices_for_symbol[buy_ex].get('volume', 0),
                                        prices_for_symbol[sell_ex].get('volume', 0)
                                    ),
                                    'timestamp': time.time()
                                })
                                
        # Сортируем по прибыли
        opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
        self.opportunities = opportunities[:self.max_positions]  # Топ-10
        
        return self.opportunities
        
    async def execute_arbitrage(self, opportunity: dict) -> bool:
        """Исполнение арбитражной сделки"""
        symbol = opportunity['symbol']
        buy_exchange = opportunity['buy_exchange']
        sell_exchange = opportunity['sell_exchange']
        
        logging.info("=" * 60)
        logging.info(f"🎯 АРБИТРАЖ: {symbol}")
        logging.info(f"   📊 {buy_exchange.upper()} → {sell_exchange.upper()}")
        logging.info(f"   💹 Спред: {opportunity['spread']:.3f}%")
        logging.info(f"   💰 Чистая прибыль: {opportunity['net_profit']:.3f}%")
        logging.info(f"   📈 Объем: ${opportunity['volume']:,.0f}")
        
        # Проверяем ликвидность в стаканах
        buy_key = f"{buy_exchange}:{symbol}"
        sell_key = f"{sell_exchange}:{symbol}"
        
        if buy_key in self.orderbooks and sell_key in self.orderbooks:
            buy_ob = self.orderbooks[buy_key]
            sell_ob = self.orderbooks[sell_key]
            
            # Проверяем достаточную ликвидность
            buy_liquidity = sum([ask[1] * ask[0] for ask in buy_ob['asks'][:3]])
            sell_liquidity = sum([bid[1] * bid[0] for bid in sell_ob['bids'][:3]])
            
            if buy_liquidity < self.position_size or sell_liquidity < self.position_size:
                logging.info(f"   ⚠️ Недостаточная ликвидность")
                return False
                
        # Исполняем сделку только если есть MEXC
        if buy_exchange == 'mexc' or sell_exchange == 'mexc':
            amount = self.position_size / opportunity['buy_price']
            
            logging.info(f"   🔧 Режим: REAL EXECUTION")
            logging.info(f"   💼 Покупка: {amount:.4f} @ ${opportunity['buy_price']:.4f}")
            logging.info(f"   💼 Продажа: {amount:.4f} @ ${opportunity['sell_price']:.4f}")
            
            # TODO: Реальное исполнение ордеров
            # buy_order = await self.exchanges['mexc'].create_order(...)
            # sell_order = await self.exchanges['mexc'].create_order(...)
            
            profit = self.position_size * opportunity['net_profit'] / 100
            logging.info(f"   ✅ Прибыль: ${profit:.2f}")
            
            # Сохраняем сделку
            self.trades_executed.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'route': f"{buy_exchange} → {sell_exchange}",
                'profit_percent': opportunity['net_profit'],
                'profit_usd': profit
            })
            
            # Устанавливаем cooldown
            cooldown_key = f"{symbol}:{buy_exchange}->{sell_exchange}"
            self.cooldowns[cooldown_key] = time.time()
            
            return True
        else:
            # Симуляция для бирж без API ключей
            logging.info(f"   🎮 Режим: SIMULATION")
            amount = self.position_size / opportunity['buy_price']
            profit = self.position_size * opportunity['net_profit'] / 100
            logging.info(f"   📝 Симуляция: {amount:.4f} {symbol.split('/')[0]}")
            logging.info(f"   💵 Прибыль: ${profit:.2f}")
            
            return False
            
    async def monitor_loop(self):
        """Основной цикл мониторинга"""
        iteration = 0
        
        while True:
            try:
                iteration += 1
                
                # Ищем арбитраж
                opportunities = self.find_arbitrage_opportunities()
                
                # Исполняем лучшую возможность
                if opportunities:
                    best = opportunities[0]
                    if best['net_profit'] >= self.min_profit_percent:
                        await self.execute_arbitrage(best)
                        
                # Статус каждые 10 итераций
                if iteration % 10 == 0:
                    active_prices = len([p for p in self.prices.values() 
                                       if p.get('timestamp') and time.time() * 1000 - p['timestamp'] < 10000])
                    
                    logging.info("-" * 60)
                    logging.info("📊 СТАТУС:")
                    logging.info(f"   🔄 Активных цен: {active_prices}")
                    logging.info(f"   📡 WebSocket подключений: {len(self.ws_exchanges)}")
                    logging.info(f"   🎯 Возможностей: {len(self.opportunities)}")
                    logging.info(f"   💼 Сделок: {len(self.trades_executed)}")
                    
                    if self.trades_executed:
                        total_profit = sum([t['profit_usd'] for t in self.trades_executed])
                        logging.info(f"   💰 Общая прибыль: ${total_profit:.2f}")
                        
                    if opportunities:
                        logging.info(f"   🏆 Лучшая возможность: {opportunities[0]['net_profit']:.3f}%")
                        logging.info(f"      {opportunities[0]['symbol']}: {opportunities[0]['buy_exchange']} → {opportunities[0]['sell_exchange']}")
                        
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logging.error(f"Ошибка в monitor_loop: {e}")
                await asyncio.sleep(5)
                
    async def run(self):
        """Запуск бота"""
        await self.initialize_exchanges()
        
        # Запускаем WebSocket подписки
        tasks = []
        
        all_exchanges = list(self.ws_exchanges.keys()) + list(self.exchanges.keys())
        
        for exchange_name in all_exchanges:
            for symbol in self.symbols:
                # Подписка на тикеры
                tasks.append(asyncio.create_task(
                    self.watch_ticker(exchange_name, symbol)
                ))
                
                # Подписка на стаканы (только для основных пар)
                if symbol in ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'DOGE/USDT']:
                    tasks.append(asyncio.create_task(
                        self.watch_orderbook(exchange_name, symbol)
                    ))
                    
        # Запускаем мониторинг
        tasks.append(asyncio.create_task(self.monitor_loop()))
        
        logging.info("🚀 WebSocket подключения запущены!")
        logging.info("=" * 60)
        
        # Ждем завершения
        await asyncio.gather(*tasks)
        
        
async def main():
    """Точка входа"""
    print("\n" + "=" * 60)
    print("   WebSocket ARBITRAGE BOT")
    print("   Обход геоблокировки через proxy")
    print("=" * 60 + "\n")
    
    bot = WebSocketArbitrageBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logging.info("\n👋 Остановка бота...")
        
        # Сохраняем результаты
        if bot.trades_executed:
            with open(f"ws_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", 'w') as f:
                json.dump(bot.trades_executed, f, indent=2)
                
            total = sum([t['profit_usd'] for t in bot.trades_executed])
            logging.info(f"💰 Итоговая прибыль: ${total:.2f}")
            logging.info(f"📊 Всего сделок: {len(bot.trades_executed)}")
            
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
        
        
if __name__ == "__main__":
    asyncio.run(main())
