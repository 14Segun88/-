#!/usr/bin/env python3
"""
Multi-Exchange Arbitrage Bot with 7 Exchanges
WebSocket + Proxy support for geo-blocking bypass
"""

import asyncio
import ccxt.pro as ccxt
import logging
import json
import time
from datetime import datetime
from typing import Dict, List, Optional
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('multi_exchange_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация прокси для обхода геоблокировки
PROXY_CONFIG = {
    'http': 'http://172.31.128.1:2080',  # NekoBox proxy
    'https': 'http://172.31.128.1:2080'
}

# Конфигурация 7 бирж с депозитами по $100
EXCHANGE_CONFIG = {
    'MEXC': {
        'apiKey': '',  # Работа в режиме публичных данных
        'secret': '',
        'enableWS': True,
        'useProxy': False,  # MEXC не требует прокси
        'deposit': 100,
        'fees': {'maker': 0.0, 'taker': 0.001}  # 0% maker, 0.1% taker
    },
    'binance': {
        'apiKey': 'MvV3eNsenTdNinmtt1hXVOjNg1VsmjtNY4iZpqddN6f03DuX1GB8DuuKPOiUSOEy',
        'secret': 'XcDJGf39tlsl4G8qUu86wQqpEoqZgRfrl5yS8j7yiampncgrJ05PxQYUJYdUyPmG',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.00075, 'taker': 0.00075}  # С BNB скидкой
    },
    'bybit': {
        'apiKey': 'YOUR_BYBIT_API_KEY',  # TODO: Добавьте ключ
        'secret': 'YOUR_BYBIT_SECRET',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.0001, 'taker': 0.0006}
    },
    'gateio': {
        'apiKey': 'YOUR_GATEIO_API_KEY',  # TODO: Добавьте ключ
        'secret': 'YOUR_GATEIO_SECRET',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.002, 'taker': 0.002}
    },
    'bitget': {
        'apiKey': 'YOUR_BITGET_API_KEY',  # TODO: Добавьте ключ
        'secret': 'YOUR_BITGET_SECRET',
        'passphrase': 'YOUR_BITGET_PASSPHRASE',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.001, 'taker': 0.001}
    },
    'okx': {
        'apiKey': 'YOUR_OKX_API_KEY',  # TODO: Добавьте ключ
        'secret': 'YOUR_OKX_SECRET',
        'passphrase': 'YOUR_OKX_PASSPHRASE',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.0008, 'taker': 0.001}
    },
    'kucoin': {
        'apiKey': 'YOUR_KUCOIN_API_KEY',  # TODO: Добавьте ключ
        'secret': 'YOUR_KUCOIN_SECRET',
        'password': 'YOUR_KUCOIN_PASSWORD',
        'enableWS': True,
        'useProxy': True,  # Обход геоблокировки
        'deposit': 100,
        'fees': {'maker': 0.001, 'taker': 0.001}
    }
}

# Параметры арбитража
ARBITRAGE_CONFIG = {
    'min_profit_threshold': 0.0001,  # 0.01% минимальная прибыль (пониженный порог для тестирования) 0.05%
    'position_size': 50,  # $50 на сделку (для 7 бирж)
    'max_positions': 14,  # До 2 позиций на биржу
    'cooldown_seconds': 30,  # Кулдаун между сделками
    'total_capital': 700,  # $100 * 7 бирж
    'check_liquidity': True,
    'min_volume_24h': 10000
}

# Торговые пары (добавлены волатильные мем-токены)
TRADING_PAIRS = [
    'BTC/USDT',
    'ETH/USDT', 
    'BNB/USDT',
    'SOL/USDT',
    'XRP/USDT',
    'DOGE/USDT',
    'ADA/USDT',
    'AVAX/USDT',
    'SHIB/USDT',
    'DOT/USDT',
    'TRX/USDT',
    'POL/USDT',  # Заменили MATIC на POL
    'UNI/USDT',
    'LTC/USDT',
    'PEPE/USDT',  # Мем-токен с высокой волатильностью
    'WIF/USDT',   # Dogwifhat - волатильный
    'BONK/USDT',  # Bonk - волатильный
    'FLOKI/USDT', # Floki - волатильный
    'ARB/USDT',   # Arbitrum
    'OP/USDT',    # Optimism
    'INJ/USDT',   # Injective
    'SEI/USDT',   # Sei
    'SUI/USDT',   # Sui
    'APT/USDT'    # Aptos
]

class MultiExchangeArbitrageBot:
    def __init__(self):
        self.exchanges = {}
        self.prices = {}
        self.balances = {}
        self.opportunities = []
        self.trades = []
        self.last_trades = {}
        self.ws_connections = {}
        self.running = False
        
    async def initialize(self):
        """Инициализация всех 7 бирж"""
        logger.info("=" * 70)
        logger.info("🚀 ЗАПУСК MULTI-EXCHANGE ARBITRAGE BOT")
        logger.info("=" * 70)
        
        total_deposit = 0
        active_exchanges = []
        
        for exchange_id, config in EXCHANGE_CONFIG.items():
            try:
                logger.info(f"\n📡 Подключение к {exchange_id.upper()}...")
                
                exchange_config = {
                    'enableRateLimit': True,
                    'rateLimit': 50,
                    'options': {
                        'defaultType': 'spot',
                        'adjustForTimeDifference': True
                    }
                }
                
                # Настройка прокси для обхода геоблокировки
                if config.get('useProxy'):
                    exchange_config['proxies'] = PROXY_CONFIG
                    exchange_config['options']['createMarketBuyOrderRequiresPrice'] = False
                    logger.info(f"   🌐 Используется proxy для обхода геоблокировки")
                
                # Добавление API ключей
                has_api_keys = False
                if config.get('apiKey') and not config['apiKey'].startswith('YOUR_'):
                    exchange_config['apiKey'] = config['apiKey']
                    exchange_config['secret'] = config['secret']
                    has_api_keys = True
                    
                    # Специфичные параметры для бирж
                    if exchange_id == 'okx' and config.get('passphrase'):
                        exchange_config['password'] = config['passphrase']
                    elif exchange_id == 'kucoin' and config.get('password'):
                        exchange_config['password'] = config['password']
                    elif exchange_id == 'bitget' and config.get('passphrase'):
                        exchange_config['password'] = config['passphrase']
                    
                    logger.info(f"   🔑 API ключи установлены")
                else:
                    logger.info(f"   ⚠️  Работа в режиме публичных данных (нет API ключей)")
                
                # Создание экземпляра биржи
                exchange_class = getattr(ccxt, exchange_id)
                exchange = exchange_class(exchange_config)
                
                # Проверка подключения
                await exchange.load_markets()
                
                self.exchanges[exchange_id] = exchange
                self.balances[exchange_id] = config.get('deposit', 0)
                total_deposit += config.get('deposit', 0)
                active_exchanges.append(exchange_id)
                
                logger.info(f"   ✅ Успешно подключено!")
                logger.info(f"   💰 Депозит: ${config.get('deposit', 0)}")
                logger.info(f"   📊 Комиссии: Maker {config['fees']['maker']*100:.3f}%, Taker {config['fees']['taker']*100:.3f}%")
                logger.info(f"   🔌 WebSocket: {'Включен' if config.get('enableWS') else 'Выключен'}")
                
                # Инициализация WebSocket если включен
                if config.get('enableWS') and has_api_keys:
                    self.ws_connections[exchange_id] = True
                    logger.info(f"   📡 WebSocket готов к подключению")
                
            except Exception as e:
                logger.error(f"   ❌ Ошибка подключения к {exchange_id}: {e}")
                if "451" in str(e):
                    logger.error(f"   🚫 Геоблокировка! Проверьте настройки proxy")
                continue
        
        logger.info("\n" + "=" * 70)
        logger.info(f"📊 ИТОГОВАЯ СТАТИСТИКА:")
        logger.info(f"   ✅ Активных бирж: {len(active_exchanges)}/7")
        logger.info(f"   💰 Общий капитал: ${total_deposit}")
        logger.info(f"   📈 Торговых пар: {len(TRADING_PAIRS)}")
        logger.info(f"   🎯 Минимальная прибыль: {ARBITRAGE_CONFIG['min_profit_threshold']}%")
        logger.info(f"   💵 Размер позиции: ${ARBITRAGE_CONFIG['position_size']}")
        logger.info("=" * 70 + "\n")
        
        if len(active_exchanges) < 2:
            logger.error("⚠️  Недостаточно активных бирж для арбитража!")
            return False
            
        return True
    
    async def watch_ticker_ws(self, exchange_id: str, symbol: str):
        """Подписка на тикеры через WebSocket"""
        if exchange_id not in self.ws_connections:
            return
            
        exchange = self.exchanges[exchange_id]
        
        while self.running:
            try:
                ticker = await exchange.watch_ticker(symbol)
                
                if symbol not in self.prices:
                    self.prices[symbol] = {}
                
                self.prices[symbol][exchange_id] = {
                    'bid': ticker.get('bid'),
                    'ask': ticker.get('ask'),
                    'volume': ticker.get('quoteVolume', 0),
                    'timestamp': time.time()
                }
                
            except Exception as e:
                if "not supported" in str(e).lower():
                    # Fallback на REST API
                    await self.fetch_ticker_rest(exchange_id, symbol)
                else:
                    logger.error(f"WS ошибка {exchange_id} {symbol}: {e}")
                await asyncio.sleep(1)
    
    async def fetch_ticker_rest(self, exchange_id: str, symbol: str):
        """Получение тикера через REST API"""
        try:
            exchange = self.exchanges[exchange_id]
            ticker = await exchange.fetch_ticker(symbol)
            
            if symbol not in self.prices:
                self.prices[symbol] = {}
            
            self.prices[symbol][exchange_id] = {
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'volume': ticker.get('quoteVolume', 0),
                'timestamp': time.time()
            }
            
        except Exception as e:
            logger.debug(f"REST ошибка {exchange_id} {symbol}: {e}")
    
    async def collect_prices(self):
        """Сбор цен со всех бирж"""
        while self.running:
            tasks = []
            
            for symbol in TRADING_PAIRS:
                for exchange_id in self.exchanges:
                    if exchange_id in self.ws_connections:
                        # WebSocket подписка
                        tasks.append(self.watch_ticker_ws(exchange_id, symbol))
                    else:
                        # REST API запрос
                        tasks.append(self.fetch_ticker_rest(exchange_id, symbol))
            
            # Запускаем все задачи параллельно
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Проверяем арбитражные возможности
            await self.check_arbitrage_opportunities()
            
            # Ждем перед следующим циклом
            await asyncio.sleep(1)
    
    async def check_arbitrage_opportunities(self):
        """Поиск арбитражных возможностей между 7 биржами"""
        opportunities = []
        
        for symbol in TRADING_PAIRS:
            if symbol not in self.prices:
                continue
            
            prices = self.prices[symbol]
            active_exchanges = [(ex, p) for ex, p in prices.items() 
                              if p.get('bid') and p.get('ask') and 
                              time.time() - p.get('timestamp', 0) < 5]
            
            if len(active_exchanges) < 2:
                continue
            
            # Находим лучшие цены для покупки и продажи
            for buy_ex, buy_price in active_exchanges:
                for sell_ex, sell_price in active_exchanges:
                    if buy_ex == sell_ex:
                        continue
                    
                    # Проверяем баланс на бирже покупки
                    if self.balances.get(buy_ex, 0) < ARBITRAGE_CONFIG['position_size']:
                        continue
                    
                    # Расчет прибыли
                    buy_total = buy_price['ask']
                    sell_total = sell_price['bid']
                    
                    if sell_total <= buy_total:
                        continue
                    
                    # Учитываем комиссии
                    buy_fee = EXCHANGE_CONFIG[buy_ex]['fees']['taker']
                    sell_fee = EXCHANGE_CONFIG[sell_ex]['fees']['maker']
                    
                    gross_profit = ((sell_total / buy_total) - 1) * 100
                    net_profit = gross_profit - (buy_fee + sell_fee) * 100
                    
                    if net_profit >= ARBITRAGE_CONFIG['min_profit_threshold']:
                        # Проверяем cooldown
                        route_key = f"{symbol}:{buy_ex}->{sell_ex}"
                        if route_key in self.last_trades:
                            if time.time() - self.last_trades[route_key] < ARBITRAGE_CONFIG['cooldown_seconds']:
                                continue
                        
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': buy_ex,
                            'sell_exchange': sell_ex,
                            'buy_price': buy_total,
                            'sell_price': sell_total,
                            'gross_profit': gross_profit,
                            'net_profit': net_profit,
                            'position_size': ARBITRAGE_CONFIG['position_size'],
                            'expected_profit_usd': net_profit * ARBITRAGE_CONFIG['position_size'] / 100,
                            'timestamp': datetime.now()
                        })
        
        # Сортируем по прибыли
        opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
        
        # Обновляем список возможностей
        self.opportunities = opportunities[:ARBITRAGE_CONFIG['max_positions']]
        
        # Выполняем лучшие сделки
        for opp in self.opportunities[:3]:  # Топ-3 возможности
            await self.execute_arbitrage(opp)
    
    async def execute_arbitrage(self, opportunity: dict):
        """Исполнение арбитражной сделки"""
        symbol = opportunity['symbol']
        buy_ex = opportunity['buy_exchange']
        sell_ex = opportunity['sell_exchange']
        amount = opportunity['position_size']
        
        logger.info("\n" + "🎯" * 30)
        logger.info(f"🚀 АРБИТРАЖ: {symbol}")
        logger.info(f"   📍 Маршрут: {buy_ex.upper()} → {sell_ex.upper()}")
        logger.info(f"   💰 Чистая прибыль: {opportunity['net_profit']:.3f}%")
        logger.info(f"   💵 Ожидаемая прибыль: ${opportunity['expected_profit_usd']:.2f}")
        logger.info(f"   📊 Размер позиции: ${amount}")
        
        # Обновляем cooldown
        route_key = f"{symbol}:{buy_ex}->{sell_ex}"
        self.last_trades[route_key] = time.time()
        
        # Симулируем исполнение (для реальной торговли раскомментируйте)
        """
        # РЕАЛЬНОЕ ИСПОЛНЕНИЕ:
        try:
            # Покупка на первой бирже
            buy_order = await self.exchanges[buy_ex].create_market_buy_order(
                symbol, amount / opportunity['buy_price']
            )
            logger.info(f"   ✅ Куплено на {buy_ex}: {buy_order['id']}")
            
            # Продажа на второй бирже
            sell_order = await self.exchanges[sell_ex].create_market_sell_order(
                symbol, amount / opportunity['buy_price']
            )
            logger.info(f"   ✅ Продано на {sell_ex}: {sell_order['id']}")
            
            # Обновляем балансы
            self.balances[buy_ex] -= amount
            self.balances[sell_ex] += amount * (1 + opportunity['net_profit']/100)
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка исполнения: {e}")
            return False
        """
        
        # Симуляция для демо
        self.balances[buy_ex] -= amount
        self.balances[sell_ex] += amount * (1 + opportunity['net_profit']/100)
        
        # Сохраняем сделку
        trade = {
            **opportunity,
            'status': 'simulated',  # Измените на 'executed' для реальной торговли
            'execution_time': datetime.now()
        }
        self.trades.append(trade)
        
        logger.info(f"   ✅ Сделка выполнена (симуляция)")
        logger.info("🎯" * 30 + "\n")
        
        # Сохраняем в файл
        await self.save_trades()
        
        return True
    
    async def save_trades(self):
        """Сохранение сделок в файл"""
        try:
            with open('multi_exchange_trades.json', 'w') as f:
                json.dump([{
                    'symbol': t['symbol'],
                    'route': f"{t['buy_exchange']} → {t['sell_exchange']}",
                    'net_profit': f"{t['net_profit']:.3f}%",
                    'profit_usd': f"${t['expected_profit_usd']:.2f}",
                    'timestamp': t['timestamp'].isoformat() if isinstance(t['timestamp'], datetime) else t['timestamp']
                } for t in self.trades], f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения сделок: {e}")
    
    async def print_status(self):
        """Вывод статуса бота"""
        while self.running:
            await asyncio.sleep(30)
            
            active_prices = sum(1 for s in self.prices.values() 
                              for p in s.values() 
                              if time.time() - p.get('timestamp', 0) < 10)
            
            total_profit = sum(t.get('expected_profit_usd', 0) for t in self.trades)
            
            logger.info("\n" + "=" * 70)
            logger.info("📊 СТАТУС БОТА:")
            logger.info(f"   ⏱️  Время работы: {datetime.now()}")
            logger.info(f"   📡 Активных цен: {active_prices}")
            logger.info(f"   🎯 Возможностей: {len(self.opportunities)}")
            logger.info(f"   📈 Сделок: {len(self.trades)}")
            logger.info(f"   💰 Общая прибыль: ${total_profit:.2f}")
            
            # Балансы по биржам
            logger.info("   💼 Балансы:")
            for ex, balance in self.balances.items():
                if ex in self.exchanges:
                    logger.info(f"      {ex.upper()}: ${balance:.2f}")
            
            # Лучшие возможности
            if self.opportunities:
                logger.info("   🏆 Топ возможности:")
                for i, opp in enumerate(self.opportunities[:3], 1):
                    logger.info(f"      {i}. {opp['symbol']}: {opp['buy_exchange']}→{opp['sell_exchange']} ({opp['net_profit']:.3f}%)")
            
            logger.info("=" * 70 + "\n")
    
    async def run(self):
        """Главный цикл бота"""
        # Инициализация
        if not await self.initialize():
            logger.error("Не удалось инициализировать бота")
            return
        
        self.running = True
        
        # Запускаем задачи
        tasks = [
            self.collect_prices(),
            self.print_status()
        ]
        
        try:
            logger.info("🚀 Бот запущен! Нажмите Ctrl+C для остановки\n")
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("\n⏹️  Остановка бота...")
        finally:
            self.running = False
            
            # Закрываем соединения
            for exchange in self.exchanges.values():
                await exchange.close()
            
            # Финальная статистика
            total_profit = sum(t.get('expected_profit_usd', 0) for t in self.trades)
            logger.info("\n" + "=" * 70)
            logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА:")
            logger.info(f"   📈 Всего сделок: {len(self.trades)}")
            logger.info(f"   💰 Общая прибыль: ${total_profit:.2f}")
            logger.info(f"   ⏱️  Завершено: {datetime.now()}")
            logger.info("=" * 70)

async def main():
    bot = MultiExchangeArbitrageBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
