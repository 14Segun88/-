#!/usr/bin/env python3
"""
🚀 REST API ARBITRAGE BOT
Стабильная версия арбитражного бота на REST API
Версия: 1.0.0
"""

import asyncio
import aiohttp
import json
import time
import sys
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
import logging

# ============================================
# 📊 КОНФИГУРАЦИЯ
# ============================================
CONFIG = {
    # Торговые параметры
    'MIN_PROFIT_THRESHOLD': 0.15,  # Минимальная прибыль 0.15% (снижено)
    'SLIPPAGE_TOLERANCE': 0.03,    # Допустимый слиппедж 0.03% (снижено)
    'POSITION_SIZE_USD': 100,      # Размер позиции $100
    'SCAN_INTERVAL': 1,             # Интервал сканирования 1 сек (ускорено)
    
    # Биржи и комиссии (без скидок)
    'EXCHANGES': {
        'mexc': {
            'enabled': True,
            'fees': 0.20,  # 0.20% стандартная комиссия
            'api_url': 'https://api.mexc.com',
        },
        'huobi': {
            'enabled': True,
            'fees': 0.20,  # 0.20% стандартная комиссия  
            'api_url': 'https://api.huobi.pro',
        },
        'binance': {
            'enabled': True,
            'fees': 0.10,  # 0.10% стандартная комиссия
            'api_url': 'https://api.binance.com',
        },
        'okx': {
            'enabled': True,
            'fees': 0.15,  # 0.15% стандартная комиссия
            'api_url': 'https://www.okx.com',
        },
        'kucoin': {
            'enabled': True,
            'fees': 0.10,  # 0.10% стандартная комиссия
            'api_url': 'https://api.kucoin.com',
        },
        'bybit': {
            'enabled': False,  # Отключен из-за 403
            'fees': 0.08,
            'api_url': 'https://api.bybit.com',
            'proxy': 'http://172.31.128.1:2080'  # Прокси для обхода блокировки
        }
    },
    
    # Торговые пары для мониторинга (добавлены волатильные пары)
    'TRADING_PAIRS': [
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'SOL/USDT',
        'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'MATIC/USDT',
        'AVAX/USDT', 'DOT/USDT', 'LINK/USDT', 'UNI/USDT',
        'SHIB/USDT', 'LTC/USDT', 'TRX/USDT', 'ATOM/USDT',
        'APT/USDT', 'ARB/USDT', 'OP/USDT', 'INJ/USDT',
        'PEPE/USDT', 'WIF/USDT', 'BONK/USDT', 'FLOKI/USDT'
    ],
    
    # Режим работы
    'MODE': 'demo',  # 'demo', 'paper', 'real'
}

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('RESTBot')

class PriceData:
    """Структура данных для цены"""
    def __init__(self, exchange: str, symbol: str, bid: float, ask: float, timestamp: float):
        self.exchange = exchange
        self.symbol = symbol
        self.bid = bid
        self.ask = ask
        self.spread = (ask - bid) / bid * 100
        self.timestamp = timestamp
        self.age = time.time() - timestamp

class ArbitrageOpportunity:
    """Арбитражная возможность"""
    def __init__(self, symbol: str, buy_exchange: str, sell_exchange: str,
                 buy_price: float, sell_price: float):
        self.symbol = symbol
        self.buy_exchange = buy_exchange
        self.sell_exchange = sell_exchange
        self.buy_price = buy_price
        self.sell_price = sell_price
        self.spread_pct = (sell_price - buy_price) / buy_price * 100
        
        # Расчет комиссий
        buy_fee = CONFIG['EXCHANGES'][buy_exchange]['fees']
        sell_fee = CONFIG['EXCHANGES'][sell_exchange]['fees']
        self.total_fees = buy_fee + sell_fee
        
        # Чистая прибыль
        self.net_profit = self.spread_pct - self.total_fees - CONFIG['SLIPPAGE_TOLERANCE']
        self.is_profitable = self.net_profit >= CONFIG['MIN_PROFIT_THRESHOLD']
        
        self.timestamp = time.time()

class RESTArbitrageBot:
    """Основной класс арбитражного бота на REST API"""
    
    def __init__(self):
        self.prices = defaultdict(dict)  # {symbol: {exchange: PriceData}}
        self.opportunities = []
        self.executed_trades = []
        self.running = False
        self.session = None
        self.statistics = {
            'scans': 0,
            'opportunities_found': 0,
            'profitable_opportunities': 0,
            'trades_executed': 0,
            'total_profit_pct': 0,
            'errors': 0
        }
        
    async def start(self):
        """Запуск бота"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК REST API ARBITRAGE BOT")
        logger.info("=" * 60)
        logger.info(f"Режим: {CONFIG['MODE'].upper()}")
        logger.info(f"Минимальная прибыль: {CONFIG['MIN_PROFIT_THRESHOLD']}%")
        logger.info(f"Размер позиции: ${CONFIG['POSITION_SIZE_USD']}")
        
        # Активные биржи
        active_exchanges = [ex for ex, conf in CONFIG['EXCHANGES'].items() if conf['enabled']]
        logger.info(f"Активные биржи: {', '.join(active_exchanges)}")
        logger.info(f"Торговые пары: {len(CONFIG['TRADING_PAIRS'])}")
        
        self.session = aiohttp.ClientSession()
        self.running = True
        
        try:
            # Запускаем основные задачи
            await asyncio.gather(
                self._price_fetcher_loop(),
                self._arbitrage_scanner_loop(),
                self._statistics_loop(),
                self._signal_handler()
            )
        except KeyboardInterrupt:
            logger.info("⚠️ Получен сигнал остановки")
        finally:
            await self.stop()
    
    async def stop(self):
        """Остановка бота"""
        self.running = False
        if self.session:
            await self.session.close()
        
        logger.info("\n" + "=" * 60)
        logger.info("📊 ФИНАЛЬНАЯ СТАТИСТИКА")
        logger.info("=" * 60)
        self._print_statistics()
        logger.info("✅ Бот остановлен")
    
    async def _price_fetcher_loop(self):
        """Цикл получения цен"""
        while self.running:
            try:
                # Получаем цены со всех активных бирж
                tasks = []
                for exchange, config in CONFIG['EXCHANGES'].items():
                    if config['enabled']:
                        tasks.append(self._fetch_prices(exchange))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Обработка результатов
                for result in results:
                    if isinstance(result, Exception):
                        logger.debug(f"Ошибка получения цен: {result}")
                        self.statistics['errors'] += 1
                
                await asyncio.sleep(CONFIG['SCAN_INTERVAL'])
                
            except Exception as e:
                logger.error(f"Ошибка в price_fetcher: {e}")
                await asyncio.sleep(5)
    
    async def _fetch_prices(self, exchange: str) -> Dict:
        """Получение цен с биржи"""
        try:
            if exchange == 'mexc':
                return await self._fetch_mexc_prices()
            elif exchange == 'huobi':
                return await self._fetch_huobi_prices()
            elif exchange == 'binance':
                return await self._fetch_binance_prices()
            elif exchange == 'okx':
                return await self._fetch_okx_prices()
            elif exchange == 'kucoin':
                return await self._fetch_kucoin_prices()
            elif exchange == 'bybit':
                return await self._fetch_bybit_prices()
        except Exception as e:
            logger.debug(f"Ошибка {exchange}: {e}")
            raise
    
    async def _fetch_mexc_prices(self):
        """Получение цен с MEXC"""
        url = f"{CONFIG['EXCHANGES']['mexc']['api_url']}/api/v3/ticker/bookTicker"
        
        async with self.session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                timestamp = time.time()
                
                for item in data:
                    symbol = item['symbol']
                    # Конвертируем в наш формат
                    if symbol.endswith('USDT'):
                        pair = symbol[:-4] + '/USDT'
                        if pair in CONFIG['TRADING_PAIRS']:
                            self.prices[pair]['mexc'] = PriceData(
                                'mexc', pair,
                                float(item['bidPrice']),
                                float(item['askPrice']),
                                timestamp
                            )
                
                return {'status': 'ok', 'exchange': 'mexc'}
    
    async def _fetch_huobi_prices(self):
        """Получение цен с Huobi"""
        url = f"{CONFIG['EXCHANGES']['huobi']['api_url']}/market/tickers"
        
        async with self.session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                timestamp = time.time()
                
                if data.get('status') == 'ok':
                    for item in data.get('data', []):
                        symbol = item['symbol'].upper()
                        # Конвертируем в наш формат
                        if symbol.endswith('USDT'):
                            pair = symbol[:-4] + '/USDT'
                            if pair in CONFIG['TRADING_PAIRS']:
                                self.prices[pair]['huobi'] = PriceData(
                                    'huobi', pair,
                                    float(item['bid']),
                                    float(item['ask']),
                                    timestamp
                                )
                
                return {'status': 'ok', 'exchange': 'huobi'}
    
    async def _fetch_binance_prices(self):
        """Получение цен с Binance"""
        url = f"{CONFIG['EXCHANGES']['binance']['api_url']}/api/v3/ticker/bookTicker"
        
        async with self.session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                timestamp = time.time()
                
                for item in data:
                    symbol = item['symbol']
                    if symbol.endswith('USDT'):
                        pair = symbol[:-4] + '/USDT'
                        if pair in CONFIG['TRADING_PAIRS']:
                            self.prices[pair]['binance'] = PriceData(
                                'binance', pair,
                                float(item['bidPrice']),
                                float(item['askPrice']),
                                timestamp
                            )
                
                return {'status': 'ok', 'exchange': 'binance'}
    
    async def _fetch_okx_prices(self):
        """Получение цен с OKX"""
        url = f"{CONFIG['EXCHANGES']['okx']['api_url']}/api/v5/market/tickers?instType=SPOT"
        
        async with self.session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                timestamp = time.time()
                
                if data.get('code') == '0':
                    for item in data.get('data', []):
                        inst_id = item['instId']
                        if inst_id.endswith('-USDT'):
                            pair = inst_id.replace('-', '/') 
                            if pair in CONFIG['TRADING_PAIRS']:
                                self.prices[pair]['okx'] = PriceData(
                                    'okx', pair,
                                    float(item['bidPx']),
                                    float(item['askPx']),
                                    timestamp
                                )
                
                return {'status': 'ok', 'exchange': 'okx'}
    
    async def _fetch_kucoin_prices(self):
        """Получение цен с KuCoin"""
        url = f"{CONFIG['EXCHANGES']['kucoin']['api_url']}/api/v1/market/allTickers"
        
        async with self.session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                timestamp = time.time()
                
                if data.get('code') == '200000':
                    for item in data.get('data', {}).get('ticker', []):
                        symbol = item['symbol']
                        if symbol.endswith('-USDT'):
                            pair = symbol.replace('-', '/')
                            if pair in CONFIG['TRADING_PAIRS']:
                                self.prices[pair]['kucoin'] = PriceData(
                                    'kucoin', pair,
                                    float(item.get('buy', 0)),
                                    float(item.get('sell', 0)),
                                    timestamp
                                )
                
                return {'status': 'ok', 'exchange': 'kucoin'}
    
    async def _fetch_bybit_prices(self):
        """Получение цен с Bybit (с прокси)"""
        # TODO: Реализовать с прокси
        return {'status': 'disabled', 'exchange': 'bybit'}
    
    async def _arbitrage_scanner_loop(self):
        """Цикл поиска арбитражных возможностей"""
        await asyncio.sleep(5)  # Даем время на первое получение цен
        
        while self.running:
            try:
                self.statistics['scans'] += 1
                opportunities_found = 0
                
                # Сканируем все пары
                for symbol in CONFIG['TRADING_PAIRS']:
                    if symbol not in self.prices:
                        continue
                    
                    exchanges_with_price = list(self.prices[symbol].keys())
                    if len(exchanges_with_price) < 2:
                        continue
                    
                    # Находим лучшие цены
                    best_bid = None
                    best_ask = None
                    
                    for exchange in exchanges_with_price:
                        price_data = self.prices[symbol][exchange]
                        
                        # Пропускаем устаревшие данные (старше 10 сек)
                        if price_data.age > 10:
                            continue
                        
                        if best_bid is None or price_data.bid > best_bid[1]:
                            best_bid = (exchange, price_data.bid)
                        
                        if best_ask is None or price_data.ask < best_ask[1]:
                            best_ask = (exchange, price_data.ask)
                    
                    # Проверяем арбитраж
                    if best_bid and best_ask and best_bid[0] != best_ask[0]:
                        opportunity = ArbitrageOpportunity(
                            symbol,
                            best_ask[0],  # Покупаем по ask
                            best_bid[0],  # Продаем по bid
                            best_ask[1],
                            best_bid[1]
                        )
                        
                        if opportunity.spread_pct > 0:
                            opportunities_found += 1
                            self.statistics['opportunities_found'] += 1
                            
                            if opportunity.is_profitable:
                                self.statistics['profitable_opportunities'] += 1
                                await self._execute_arbitrage(opportunity)
                                
                                logger.info(f"💰 ПРИБЫЛЬНАЯ ВОЗМОЖНОСТЬ:")
                                logger.info(f"  {symbol}: {opportunity.buy_exchange} → {opportunity.sell_exchange}")
                                logger.info(f"  Спред: {opportunity.spread_pct:.3f}%")
                                logger.info(f"  Комиссии: {opportunity.total_fees:.2f}%")
                                logger.info(f"  Чистая прибыль: {opportunity.net_profit:.3f}%")
                
                await asyncio.sleep(CONFIG['SCAN_INTERVAL'])
                
            except Exception as e:
                logger.error(f"Ошибка в scanner: {e}")
                await asyncio.sleep(5)
    
    async def _execute_arbitrage(self, opportunity: ArbitrageOpportunity):
        """Исполнение арбитражной сделки"""
        if CONFIG['MODE'] == 'demo':
            # В demo режиме просто логируем
            self.statistics['trades_executed'] += 1
            self.statistics['total_profit_pct'] += opportunity.net_profit
            self.executed_trades.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': opportunity.symbol,
                'route': f"{opportunity.buy_exchange}→{opportunity.sell_exchange}",
                'spread': opportunity.spread_pct,
                'net_profit': opportunity.net_profit,
                'size': CONFIG['POSITION_SIZE_USD']
            })
            
            logger.info(f"✅ DEMO сделка исполнена: +{opportunity.net_profit:.3f}%")
        
        elif CONFIG['MODE'] == 'paper':
            # Paper trading - симуляция с задержкой
            await asyncio.sleep(0.5)
            self.statistics['trades_executed'] += 1
            self.statistics['total_profit_pct'] += opportunity.net_profit
            logger.info(f"📝 PAPER сделка исполнена: +{opportunity.net_profit:.3f}%")
        
        elif CONFIG['MODE'] == 'real':
            # Реальная торговля - TODO: реализовать
            logger.warning("⚠️ Реальная торговля еще не реализована")
    
    async def _statistics_loop(self):
        """Периодический вывод статистики"""
        while self.running:
            await asyncio.sleep(30)  # Каждые 30 секунд
            self._print_statistics()
    
    def _print_statistics(self):
        """Вывод статистики"""
        logger.info("\n📊 СТАТИСТИКА:")
        logger.info(f"  Сканирований: {self.statistics['scans']}")
        logger.info(f"  Найдено возможностей: {self.statistics['opportunities_found']}")
        logger.info(f"  Прибыльных: {self.statistics['profitable_opportunities']}")
        logger.info(f"  Исполнено сделок: {self.statistics['trades_executed']}")
        
        if self.statistics['trades_executed'] > 0:
            avg_profit = self.statistics['total_profit_pct'] / self.statistics['trades_executed']
            total_profit_usd = CONFIG['POSITION_SIZE_USD'] * self.statistics['total_profit_pct'] / 100
            logger.info(f"  Средняя прибыль: {avg_profit:.3f}%")
            logger.info(f"  Общая прибыль: ${total_profit_usd:.2f}")
        
        # Активные цены
        active_prices = sum(1 for symbol_prices in self.prices.values() 
                          for price in symbol_prices.values() 
                          if price.age < 10)
        logger.info(f"  Активных цен: {active_prices}")
        logger.info(f"  Ошибок: {self.statistics['errors']}")
    
    async def _signal_handler(self):
        """Обработка сигналов остановки"""
        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            self.running = False

async def main():
    """Главная функция"""
    bot = RESTArbitrageBot()
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Остановлено пользователем")
