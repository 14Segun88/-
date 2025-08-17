#!/usr/bin/env python3
"""
Упрощенный арбитражный бот для работы с доступными биржами.
Работает только с OKX, KuCoin и MEXC через публичные API.
"""
import asyncio
import ccxt.async_support as ccxt
import time
from datetime import datetime
import csv
import os

# Конфигурация
MIN_PROFIT_THRESHOLD = 0.05  # Минимальная прибыль 0.05% для тестирования
POSITION_SIZE_USD = 100      # Размер позиции
SCAN_INTERVAL = 2             # Интервал сканирования в секундах

# Биржи и комиссии
EXCHANGES = {
    'okx': {'taker_fee': 0.001},      # 0.1%
    'kucoin': {'taker_fee': 0.001},   # 0.1%  
    'mexc': {'taker_fee': 0.001}      # 0.1%
}

# Торговые пары (используем общие для всех бирж)
SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT',
    'ADA/USDT', 'AVAX/USDT', 'DOT/USDT', 'LTC/USDT',
    'UNI/USDT', 'LINK/USDT', 'ATOM/USDT', 'FIL/USDT', 'NEAR/USDT'
]

class SimpleArbitrageBot:
    def __init__(self):
        self.clients = {}
        self.prices = {}
        self.is_running = True
        self.opportunities_found = 0
        self.paper_trades = []
        self.total_profit = 0
        
    async def initialize(self):
        """Инициализирует CCXT клиенты."""
        for exchange_name in EXCHANGES.keys():
            try:
                exchange_class = getattr(ccxt, exchange_name)
                self.clients[exchange_name] = exchange_class({
                    'enableRateLimit': True,
                    'timeout': 10000
                })
                print(f"✅ Инициализирован {exchange_name}")
            except Exception as e:
                print(f"❌ Ошибка инициализации {exchange_name}: {e}")
                
    async def fetch_prices(self, exchange_name):
        """Получает цены с биржи."""
        client = self.clients.get(exchange_name)
        if not client:
            return
            
        try:
            tickers = await client.fetch_tickers(SYMBOLS)
            
            for symbol, ticker in tickers.items():
                if ticker['bid'] and ticker['ask']:
                    if symbol not in self.prices:
                        self.prices[symbol] = {}
                    
                    self.prices[symbol][exchange_name] = {
                        'bid': ticker['bid'],
                        'ask': ticker['ask'],
                        'timestamp': time.time()
                    }
                    
        except Exception as e:
            print(f"⚠️ Ошибка получения цен с {exchange_name}: {e}")
            
    async def collect_prices_loop(self):
        """Цикл сбора цен."""
        while self.is_running:
            tasks = [self.fetch_prices(ex) for ex in self.clients.keys()]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(1)
            
    async def find_arbitrage_opportunities(self):
        """Ищет арбитражные возможности."""
        opportunities = []
        now = time.time()
        
        for symbol, exchange_prices in self.prices.items():
            # Находим лучшие bid и ask
            best_bid = 0
            best_bid_exchange = None
            best_ask = float('inf')
            best_ask_exchange = None
            
            for exchange, price_data in exchange_prices.items():
                # Проверяем свежесть данных (не старше 5 секунд)
                if now - price_data['timestamp'] > 5:
                    continue
                    
                if price_data['bid'] > best_bid:
                    best_bid = price_data['bid']
                    best_bid_exchange = exchange
                    
                if price_data['ask'] < best_ask:
                    best_ask = price_data['ask']
                    best_ask_exchange = exchange
            
            # Проверяем арбитраж
            if best_bid > best_ask and best_bid_exchange and best_ask_exchange and best_bid_exchange != best_ask_exchange:
                # Расчет прибыли
                spread_pct = (best_bid - best_ask) / best_ask * 100
                
                # Учитываем комиссии
                buy_fee = EXCHANGES[best_ask_exchange]['taker_fee'] * 100
                sell_fee = EXCHANGES[best_bid_exchange]['taker_fee'] * 100
                total_fees = buy_fee + sell_fee
                
                net_profit = spread_pct - total_fees
                
                if net_profit >= MIN_PROFIT_THRESHOLD:
                    opportunities.append({
                        'symbol': symbol,
                        'buy_exchange': best_ask_exchange,
                        'sell_exchange': best_bid_exchange,
                        'buy_price': best_ask,
                        'sell_price': best_bid,
                        'spread_pct': spread_pct,
                        'net_profit': net_profit,
                        'timestamp': now
                    })
                elif net_profit > -0.1:  # Показываем близкие к прибыльным
                    print(f"  {symbol}: {best_ask_exchange}→{best_bid_exchange} spread:{spread_pct:.3f}% net:{net_profit:.3f}%", end="\r")
                    
        return opportunities
        
    async def execute_paper_trade(self, opportunity):
        """Исполняет бумажную сделку."""
        trade = {
            'timestamp': datetime.now().isoformat(),
            'symbol': opportunity['symbol'],
            'buy_exchange': opportunity['buy_exchange'],
            'sell_exchange': opportunity['sell_exchange'],
            'buy_price': opportunity['buy_price'],
            'sell_price': opportunity['sell_price'],
            'size_usd': POSITION_SIZE_USD,
            'gross_profit_pct': opportunity['spread_pct'],
            'net_profit_pct': opportunity['net_profit'],
            'net_profit_usd': POSITION_SIZE_USD * opportunity['net_profit'] / 100
        }
        
        self.paper_trades.append(trade)
        self.total_profit += trade['net_profit_usd']
        
        print(f"\n💰 СДЕЛКА #{len(self.paper_trades)}:")
        print(f"  {trade['symbol']}: {trade['buy_exchange']} → {trade['sell_exchange']}")
        print(f"  Купить: ${trade['buy_price']:.2f}, Продать: ${trade['sell_price']:.2f}")
        print(f"  Чистая прибыль: {trade['net_profit_pct']:.3f}% (${trade['net_profit_usd']:.2f})")
        print(f"  Общая прибыль: ${self.total_profit:.2f}")
        
        # Сохраняем в CSV
        self.save_trade_to_csv(trade)
        
    def save_trade_to_csv(self, trade):
        """Сохраняет сделку в CSV файл."""
        filename = 'paper_trades.csv'
        file_exists = os.path.exists(filename)
        
        with open(filename, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=trade.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(trade)
            
    async def scanner_loop(self):
        """Основной цикл сканирования."""
        while self.is_running:
            try:
                opportunities = await self.find_arbitrage_opportunities()
                
                if opportunities:
                    # Сортируем по прибыли
                    opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
                    
                    # Берем лучшую возможность
                    best = opportunities[0]
                    
                    print(f"\n🔍 Найдено {len(opportunities)} возможностей")
                    print(f"⚡ Лучшая: {best['symbol']} {best['buy_exchange']}→{best['sell_exchange']} +{best['net_profit']:.3f}%")
                    
                    # Исполняем сделку
                    await self.execute_paper_trade(best)
                    self.opportunities_found += 1
                    
                else:
                    print(f".", end="", flush=True)
                    
                await asyncio.sleep(SCAN_INTERVAL)
                
            except Exception as e:
                print(f"\n❌ Ошибка в сканере: {e}")
                await asyncio.sleep(5)
                
    async def print_status(self):
        """Печатает статус бота."""
        while self.is_running:
            await asyncio.sleep(30)
            
            print(f"\n📊 СТАТУС:")
            print(f"  Цены собраны: {len(self.prices)} пар")
            print(f"  Возможностей найдено: {self.opportunities_found}")
            print(f"  Сделок исполнено: {len(self.paper_trades)}")
            print(f"  Общая прибыль: ${self.total_profit:.2f}")
            
            # Показываем активные цены
            active_count = 0
            now = time.time()
            for symbol, exchanges in self.prices.items():
                for exchange, data in exchanges.items():
                    if now - data['timestamp'] < 5:
                        active_count += 1
                        
            print(f"  Активных котировок: {active_count}")
            
    async def run(self):
        """Запускает бота."""
        print("🚀 Запуск Simple Arbitrage Bot...")
        
        await self.initialize()
        
        if not self.clients:
            print("❌ Не удалось инициализировать ни одну биржу")
            return
            
        print(f"✅ Инициализировано {len(self.clients)} бирж")
        print(f"📋 Отслеживаем {len(SYMBOLS)} пар")
        print(f"💰 Минимальная прибыль: {MIN_PROFIT_THRESHOLD}%")
        print(f"📦 Размер позиции: ${POSITION_SIZE_USD}")
        print("-" * 50)
        
        # Запускаем задачи
        tasks = [
            asyncio.create_task(self.collect_prices_loop()),
            asyncio.create_task(self.scanner_loop()),
            asyncio.create_task(self.print_status())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n⏹️ Остановка бота...")
            self.is_running = False
            
        # Закрываем клиенты
        for client in self.clients.values():
            await client.close()
            
        print(f"\n📈 ИТОГИ:")
        print(f"  Сделок исполнено: {len(self.paper_trades)}")
        print(f"  Общая прибыль: ${self.total_profit:.2f}")
        print(f"  Средняя прибыль на сделку: ${self.total_profit/len(self.paper_trades):.2f}" if self.paper_trades else "")
        
async def main():
    bot = SimpleArbitrageBot()
    await bot.run()
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
