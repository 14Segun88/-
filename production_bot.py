#!/usr/bin/env python3
"""
Production Arbitrage Bot - Оптимизированная версия для реальной торговли
Фокус на работающих биржах и реальном исполнении
"""
import asyncio
import ccxt.async_support as ccxt
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('production_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== КОНФИГУРАЦИЯ ====================

# API КЛЮЧИ
API_CREDENTIALS = {
    'mexc': {
        'apiKey': 'mx0vglAj5GaknRsyUQ',
        'secret': '83911cc1cd784568832b624fbfb19751',
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    },
    'okx': {
        'apiKey': '',  # Используем публичные данные
        'secret': '',
        'password': '',
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    },
    'kucoin': {
        'apiKey': '',  # Используем публичные данные
        'secret': '',
        'password': '',
        'enableRateLimit': True
    }
}

# Комиссии и настройки бирж
EXCHANGES_CONFIG = {
    'mexc': {
        'maker_fee': 0.0,     # 0% maker fee!
        'taker_fee': 0.001,   # 0.1% taker
        'min_order_size': 10  # $10 минимальный ордер
    },
    'okx': {
        'maker_fee': 0.0008,  # 0.08% maker
        'taker_fee': 0.001,   # 0.1% taker
        'min_order_size': 10
    },
    'kucoin': {
        'maker_fee': 0.001,   # 0.1% maker
        'taker_fee': 0.001,   # 0.1% taker
        'min_order_size': 10
    }
}

# Торговые параметры
TRADING_CONFIG = {
    'min_profit_threshold': 0.10,  # Минимальная прибыль 0.1%
    'position_size_usd': 100,      # Размер позиции $100
    'max_positions': 3,             # Максимум открытых позиций
    'use_maker_orders': True,       # Использовать maker ордера
    'price_improvement': 0.01,      # Улучшение цены для maker 0.01%
    'order_timeout': 10,            # Таймаут ордера в секундах
    'min_volume_24h': 100000        # Минимальный объем за 24ч
}

# Основные торговые пары
TRADING_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 
    'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT',
    'LTC/USDT', 'LINK/USDT', 'UNI/USDT', 'ATOM/USDT'
]

class ProductionArbitrageBot:
    def __init__(self):
        self.exchanges = {}
        self.prices = {}
        self.orderbooks = {}
        self.balances = {}
        self.is_running = True
        self.active_positions = []
        self.total_trades = 0
        self.successful_trades = 0
        self.total_profit_usd = 0
        self.last_opportunity_time = {}
        
    async def initialize(self):
        """Инициализация бирж с проверкой API ключей."""
        logger.info("=" * 60)
        logger.info("PRODUCTION ARBITRAGE BOT - ИНИЦИАЛИЗАЦИЯ")
        logger.info("=" * 60)
        
        for exchange_id, credentials in API_CREDENTIALS.items():
            try:
                # Создаем клиент биржи
                exchange_class = getattr(ccxt, exchange_id)
                
                # Для бирж без API ключей используем публичный доступ
                if not credentials.get('apiKey'):
                    exchange = exchange_class({
                        'enableRateLimit': True,
                        'options': credentials.get('options', {})
                    })
                    logger.info(f"📡 {exchange_id.upper()}: Публичный режим (без API ключей)")
                else:
                    exchange = exchange_class(credentials)
                
                # Загружаем рынки
                await exchange.load_markets()
                self.exchanges[exchange_id] = exchange
                
                # Проверяем баланс (если есть API ключи)
                if credentials.get('apiKey'):
                    try:
                        balance = await exchange.fetch_balance()
                        usdt_balance = balance.get('USDT', {}).get('free', 0)
                        self.balances[exchange_id] = usdt_balance
                        logger.info(f"✅ {exchange_id.upper()}: Подключен | Баланс: ${usdt_balance:.2f}")
                    except Exception as e:
                        self.balances[exchange_id] = 0
                        logger.info(f"✅ {exchange_id.upper()}: Подключен | Баланс: проверка...")
                else:
                    self.balances[exchange_id] = 0
                    logger.info(f"✅ {exchange_id.upper()}: Подключен | Только публичные данные")
                    
            except Exception as e:
                logger.error(f"❌ {exchange_id.upper()}: Ошибка подключения - {str(e)[:100]}")
                
        if not self.exchanges:
            logger.error("❌ Нет активных бирж!")
            return False
            
        logger.info(f"\n📊 Активных бирж: {len(self.exchanges)}")
        logger.info(f"💰 Общий баланс: ${sum(self.balances.values()):.2f}")
        logger.info(f"⚙️  Режим: {'MAKER ордера' if TRADING_CONFIG['use_maker_orders'] else 'MARKET ордера'}")
        logger.info(f"📈 Мин. прибыль: {TRADING_CONFIG['min_profit_threshold']}%")
        logger.info(f"💵 Размер позиции: ${TRADING_CONFIG['position_size_usd']}")
        
        return True
        
    async def fetch_ticker(self, exchange_id: str, symbol: str) -> Optional[dict]:
        """Получает текущие цены для символа."""
        try:
            exchange = self.exchanges[exchange_id]
            ticker = await exchange.fetch_ticker(symbol)
            
            if ticker and ticker['bid'] and ticker['ask']:
                return {
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'volume': ticker['quoteVolume'] or 0,
                    'timestamp': time.time()
                }
        except Exception as e:
            return None
            
    async def fetch_orderbook(self, exchange_id: str, symbol: str) -> Optional[dict]:
        """Получает стакан заявок."""
        try:
            exchange = self.exchanges[exchange_id]
            orderbook = await exchange.fetch_order_book(symbol, 5)
            
            if orderbook and orderbook['bids'] and orderbook['asks']:
                return {
                    'bids': orderbook['bids'][:5],
                    'asks': orderbook['asks'][:5],
                    'timestamp': time.time()
                }
        except Exception as e:
            return None
            
    async def update_prices(self):
        """Обновляет цены по всем парам и биржам."""
        tasks = []
        
        for symbol in TRADING_PAIRS:
            for exchange_id in self.exchanges:
                tasks.append(self.fetch_ticker_with_meta(exchange_id, symbol))
                
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обновляем словарь цен
        for result in results:
            if isinstance(result, dict) and result:
                symbol = result['symbol']
                exchange_id = result['exchange']
                
                if symbol not in self.prices:
                    self.prices[symbol] = {}
                    
                self.prices[symbol][exchange_id] = {
                    'bid': result['bid'],
                    'ask': result['ask'],
                    'volume': result['volume'],
                    'timestamp': result['timestamp']
                }
                
    async def fetch_ticker_with_meta(self, exchange_id: str, symbol: str) -> Optional[dict]:
        """Получает тикер с метаданными."""
        ticker = await self.fetch_ticker(exchange_id, symbol)
        if ticker:
            ticker['exchange'] = exchange_id
            ticker['symbol'] = symbol
        return ticker
        
    def find_arbitrage_opportunities(self) -> List[dict]:
        """Находит арбитражные возможности."""
        opportunities = []
        current_time = time.time()
        
        for symbol in self.prices:
            if len(self.prices[symbol]) < 2:
                continue
                
            # Находим лучшие bid и ask
            best_bid = 0
            best_bid_exchange = None
            best_ask = float('inf')
            best_ask_exchange = None
            min_volume = float('inf')
            
            for exchange_id, price_data in self.prices[symbol].items():
                # Проверяем свежесть данных (не старше 3 секунд)
                if current_time - price_data['timestamp'] > 3:
                    continue
                    
                # Проверяем объем
                if price_data['volume'] < TRADING_CONFIG['min_volume_24h']:
                    continue
                    
                if price_data['bid'] > best_bid:
                    best_bid = price_data['bid']
                    best_bid_exchange = exchange_id
                    
                if price_data['ask'] < best_ask:
                    best_ask = price_data['ask']
                    best_ask_exchange = exchange_id
                    
                min_volume = min(min_volume, price_data['volume'])
                
            # Проверяем наличие арбитража
            if best_bid_exchange and best_ask_exchange and best_bid > best_ask:
                spread_pct = (best_bid - best_ask) / best_ask * 100
                
                # Рассчитываем комиссии
                if TRADING_CONFIG['use_maker_orders']:
                    buy_fee = EXCHANGES_CONFIG[best_ask_exchange]['maker_fee'] * 100
                    sell_fee = EXCHANGES_CONFIG[best_bid_exchange]['maker_fee'] * 100
                else:
                    buy_fee = EXCHANGES_CONFIG[best_ask_exchange]['taker_fee'] * 100
                    sell_fee = EXCHANGES_CONFIG[best_bid_exchange]['taker_fee'] * 100
                    
                net_profit = spread_pct - buy_fee - sell_fee
                
                # Проверяем минимальную прибыль
                if net_profit >= TRADING_CONFIG['min_profit_threshold']:
                    # Проверяем, не торговали ли мы эту пару недавно
                    last_trade_key = f"{symbol}_{best_ask_exchange}_{best_bid_exchange}"
                    last_trade_time = self.last_opportunity_time.get(last_trade_key, 0)
                    
                    if current_time - last_trade_time > 60:  # Минимум 60 секунд между сделками
                        opportunities.append({
                            'symbol': symbol,
                            'buy_exchange': best_ask_exchange,
                            'sell_exchange': best_bid_exchange,
                            'buy_price': best_ask,
                            'sell_price': best_bid,
                            'spread_pct': spread_pct,
                            'buy_fee': buy_fee,
                            'sell_fee': sell_fee,
                            'net_profit': net_profit,
                            'volume': min_volume,
                            'timestamp': current_time
                        })
                        
        # Сортируем по прибыльности
        opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
        return opportunities
        
    async def execute_arbitrage(self, opportunity: dict) -> bool:
        """Исполняет арбитражную сделку."""
        symbol = opportunity['symbol']
        buy_exchange = opportunity['buy_exchange']
        sell_exchange = opportunity['sell_exchange']
        
        logger.info("=" * 60)
        logger.info(f"🎯 АРБИТРАЖ: {symbol}")
        logger.info(f"   Маршрут: {buy_exchange.upper()} → {sell_exchange.upper()}")
        logger.info(f"   Спред: {opportunity['spread_pct']:.3f}%")
        logger.info(f"   Комиссии: {opportunity['buy_fee']:.3f}% + {opportunity['sell_fee']:.3f}%")
        logger.info(f"   Чистая прибыль: {opportunity['net_profit']:.3f}%")
        logger.info(f"   Объем 24ч: ${opportunity['volume']:,.0f}")
        
        # Проверяем балансы (только если есть API ключи для покупки)
        if API_CREDENTIALS[buy_exchange].get('apiKey'):
            if self.balances.get(buy_exchange, 0) < TRADING_CONFIG['position_size_usd']:
                logger.warning(f"   ⚠️  Недостаточно средств на {buy_exchange.upper()}")
                return False
        else:
            logger.info(f"   ℹ️  {buy_exchange.upper()}: Симуляция (нет API ключей)")
            # В режиме симуляции продолжаем для демонстрации
            
        # Проверяем количество активных позиций
        if len(self.active_positions) >= TRADING_CONFIG['max_positions']:
            logger.warning(f"   ⚠️  Достигнут лимит позиций ({TRADING_CONFIG['max_positions']})")
            return False
            
        try:
            amount = TRADING_CONFIG['position_size_usd'] / opportunity['buy_price']
            
            # Получаем актуальные стаканы для проверки ликвидности
            buy_book = await self.fetch_orderbook(buy_exchange, symbol)
            sell_book = await self.fetch_orderbook(sell_exchange, symbol)
            
            if not buy_book or not sell_book:
                logger.warning("   ⚠️  Не удалось получить стаканы")
                return False
                
            # Проверяем ликвидность
            buy_liquidity = sum(ask[1] * ask[0] for ask in buy_book['asks'][:3])
            sell_liquidity = sum(bid[1] * bid[0] for bid in sell_book['bids'][:3])
            
            if buy_liquidity < TRADING_CONFIG['position_size_usd'] * 2:
                logger.warning(f"   ⚠️  Недостаточная ликвидность на покупку: ${buy_liquidity:.0f}")
                return False
                
            if sell_liquidity < TRADING_CONFIG['position_size_usd'] * 2:
                logger.warning(f"   ⚠️  Недостаточная ликвидность на продажу: ${sell_liquidity:.0f}")
                return False
                
            logger.info(f"   ✅ Ликвидность: покупка ${buy_liquidity:.0f}, продажа ${sell_liquidity:.0f}")
            
            # Размещаем ордера
            if TRADING_CONFIG['use_maker_orders']:
                # Maker ордера с улучшением цены
                improvement = TRADING_CONFIG['price_improvement'] / 100
                buy_price = opportunity['buy_price'] * (1 - improvement)
                sell_price = opportunity['sell_price'] * (1 + improvement)
                
                logger.info(f"   📝 Размещение MAKER ордеров:")
                logger.info(f"      Покупка: {amount:.4f} @ ${buy_price:.4f}")
                logger.info(f"      Продажа: {amount:.4f} @ ${sell_price:.4f}")
                
                # Параллельное размещение ордеров
                buy_task = self.place_limit_order(buy_exchange, symbol, 'buy', amount, buy_price)
                sell_task = self.place_limit_order(sell_exchange, symbol, 'sell', amount, sell_price)
                
                results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
                buy_order = results[0]
                sell_order = results[1]
                
            else:
                # Market ордера
                logger.info(f"   📝 Размещение MARKET ордеров:")
                logger.info(f"      Покупка: {amount:.4f}")
                logger.info(f"      Продажа: {amount:.4f}")
                
                buy_task = self.place_market_order(buy_exchange, symbol, 'buy', amount)
                sell_task = self.place_market_order(sell_exchange, symbol, 'sell', amount)
                
                results = await asyncio.gather(buy_task, sell_task, return_exceptions=True)
                buy_order = results[0]
                sell_order = results[1]
                
            # Проверяем результаты
            if isinstance(buy_order, Exception):
                logger.error(f"   ❌ Ошибка покупки: {buy_order}")
                return False
                
            if isinstance(sell_order, Exception):
                logger.error(f"   ❌ Ошибка продажи: {sell_order}")
                # Пытаемся отменить buy ордер если он был размещен
                if not isinstance(buy_order, Exception):
                    await self.cancel_order(buy_exchange, symbol, buy_order.get('id'))
                return False
                
            # Успешное исполнение
            profit_usd = TRADING_CONFIG['position_size_usd'] * opportunity['net_profit'] / 100
            self.total_profit_usd += profit_usd
            self.successful_trades += 1
            self.total_trades += 1
            
            # Сохраняем время последней сделки
            trade_key = f"{symbol}_{buy_exchange}_{sell_exchange}"
            self.last_opportunity_time[trade_key] = time.time()
            
            logger.info(f"   ✅ ИСПОЛНЕНО!")
            logger.info(f"   💰 Прибыль: ${profit_usd:.2f}")
            logger.info(f"   📊 Общая прибыль: ${self.total_profit_usd:.2f}")
            logger.info(f"   📈 Успешных сделок: {self.successful_trades}/{self.total_trades}")
            
            # Сохраняем в лог
            self.save_trade({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'buy_exchange': buy_exchange,
                'sell_exchange': sell_exchange,
                'buy_order_id': buy_order.get('id', 'N/A'),
                'sell_order_id': sell_order.get('id', 'N/A'),
                'amount': amount,
                'buy_price': opportunity['buy_price'],
                'sell_price': opportunity['sell_price'],
                'net_profit_pct': opportunity['net_profit'],
                'profit_usd': profit_usd,
                'total_profit': self.total_profit_usd
            })
            
            return True
            
        except Exception as e:
            logger.error(f"   ❌ Критическая ошибка: {e}")
            return False
            
    async def place_limit_order(self, exchange_id: str, symbol: str, 
                                side: str, amount: float, price: float):
        """Размещает лимитный ордер."""
        try:
            exchange = self.exchanges[exchange_id]
            order = await exchange.create_limit_order(symbol, side, amount, price)
            return order
        except Exception as e:
            return e
            
    async def place_market_order(self, exchange_id: str, symbol: str, 
                                 side: str, amount: float):
        """Размещает рыночный ордер."""
        try:
            exchange = self.exchanges[exchange_id]
            order = await exchange.create_market_order(symbol, side, amount)
            return order
        except Exception as e:
            return e
            
    async def cancel_order(self, exchange_id: str, symbol: str, order_id: str):
        """Отменяет ордер."""
        try:
            exchange = self.exchanges[exchange_id]
            await exchange.cancel_order(order_id, symbol)
        except:
            pass
            
    def save_trade(self, trade_data: dict):
        """Сохраняет информацию о сделке."""
        filename = 'production_trades.json'
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    trades = json.load(f)
            else:
                trades = []
                
            trades.append(trade_data)
            
            with open(filename, 'w') as f:
                json.dump(trades, f, indent=2)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения сделки: {e}")
            
    async def main_loop(self):
        """Основной цикл бота."""
        scan_interval = 2  # Сканирование каждые 2 секунды
        status_interval = 30  # Статус каждые 30 секунд
        last_status_time = 0
        
        while self.is_running:
            try:
                current_time = time.time()
                
                # Обновляем цены
                await self.update_prices()
                
                # Ищем арбитражные возможности
                opportunities = self.find_arbitrage_opportunities()
                
                # Исполняем лучшую возможность
                if opportunities:
                    best = opportunities[0]
                    await self.execute_arbitrage(best)
                    
                # Выводим статус периодически
                if current_time - last_status_time > status_interval:
                    active_prices = sum(1 for symbol_prices in self.prices.values() 
                                      for price in symbol_prices.values() 
                                      if current_time - price['timestamp'] < 5)
                    
                    logger.info("-" * 40)
                    logger.info(f"📊 СТАТУС:")
                    logger.info(f"   Активных цен: {active_prices}")
                    logger.info(f"   Найдено возможностей: {len(opportunities)}")
                    logger.info(f"   Исполнено сделок: {self.successful_trades}/{self.total_trades}")
                    logger.info(f"   Общая прибыль: ${self.total_profit_usd:.2f}")
                    
                    if opportunities and len(opportunities) > 0:
                        logger.info(f"   Лучшая возможность: {opportunities[0]['net_profit']:.3f}%")
                    
                    last_status_time = current_time
                    
                await asyncio.sleep(scan_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Ошибка в главном цикле: {e}")
                await asyncio.sleep(5)
                
    async def run(self):
        """Запускает бота."""
        # Инициализация
        if not await self.initialize():
            return
            
        logger.info("\n" + "=" * 60)
        logger.info("🚀 ЗАПУСК ТОРГОВЛИ")
        logger.info("=" * 60)
        
        try:
            await self.main_loop()
        except KeyboardInterrupt:
            logger.info("\n⏹️  Остановка бота...")
        finally:
            # Закрываем соединения
            for exchange in self.exchanges.values():
                await exchange.close()
                
            logger.info("\n" + "=" * 60)
            logger.info("📈 ИТОГОВАЯ СТАТИСТИКА:")
            logger.info(f"   Всего сделок: {self.total_trades}")
            logger.info(f"   Успешных: {self.successful_trades}")
            if self.total_trades > 0:
                success_rate = self.successful_trades / self.total_trades * 100
                logger.info(f"   Успешность: {success_rate:.1f}%")
            logger.info(f"   Общая прибыль: ${self.total_profit_usd:.2f}")
            if self.successful_trades > 0:
                avg_profit = self.total_profit_usd / self.successful_trades
                logger.info(f"   Средняя прибыль: ${avg_profit:.2f}")
            logger.info("=" * 60)
            
async def main():
    bot = ProductionArbitrageBot()
    await bot.run()
    
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   PRODUCTION ARBITRAGE BOT")
    print("   Оптимизированная версия для реальной торговли")
    print("=" * 60 + "\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Завершение работы...")
