#!/usr/bin/env python3
"""
Hybrid Arbitrage Bot - Комбинированный режим работы
MEXC с API ключами + OKX/KuCoin через публичные данные
"""
import asyncio
import ccxt.async_support as ccxt
import json
import time
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('hybrid_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Режимы работы бирж
EXCHANGE_MODES = {
    'mexc': {
        'mode': 'trading',
        'apiKey': 'mx0vglAj5GaknRsyUQ',
        'secret': '83911cc1cd784568832b624fbfb19751',
        'maker_fee': 0.0,
        'taker_fee': 0.001,
        'min_order_size': 10
    },
    'okx': {
        'mode': 'public',
        'maker_fee': 0.0008,
        'taker_fee': 0.001,
        'min_order_size': 10
    },
    'kucoin': {
        'mode': 'public',
        'maker_fee': 0.001,
        'taker_fee': 0.001,
        'min_order_size': 10
    }
}

# Стратегия арбитража
ARBITRAGE_CONFIG = {
    'min_profit_threshold': 0.05,
    'position_size_usd': 100,
    'max_positions': 5,
    'use_maker_orders': True,
    'price_improvement': 0.005,
    'enable_simulation': True,
    'check_liquidity': True,
    'min_volume_24h': 50000,
    'cooldown_seconds': 30
}

# Торговые пары
TRADING_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT',
    'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'DOT/USDT',
    'MATIC/USDT', 'LTC/USDT', 'LINK/USDT', 'UNI/USDT',
    'ATOM/USDT', 'FIL/USDT', 'APT/USDT', 'ARB/USDT',
    'NEAR/USDT', 'FTM/USDT', 'GRT/USDT', 'SAND/USDT'
]

class HybridArbitrageBot:
    def __init__(self):
        self.exchanges = {}
        self.prices = {}
        self.orderbooks = {}
        self.balances = {}
        self.is_running = True
        self.statistics = {
            'total_opportunities': 0,
            'simulated_trades': 0,
            'real_trades': 0,
            'simulated_profit': 0,
            'real_profit': 0,
            'best_opportunity': {'profit': 0, 'route': None}
        }
        self.last_trade_time = {}
        self.price_history = {}
        
    async def initialize(self):
        """Инициализация бирж в гибридном режиме."""
        logger.info("=" * 60)
        logger.info("🚀 HYBRID ARBITRAGE BOT - ИНИЦИАЛИЗАЦИЯ")
        logger.info("=" * 60)
        
        for exchange_id, config in EXCHANGE_MODES.items():
            try:
                exchange_class = getattr(ccxt, exchange_id)
                
                if config['mode'] == 'trading':
                    credentials = {
                        'apiKey': config['apiKey'],
                        'secret': config['secret'],
                        'enableRateLimit': True,
                        'options': {'defaultType': 'spot'}
                    }
                    exchange = exchange_class(credentials)
                    await exchange.load_markets()
                    self.exchanges[exchange_id] = exchange
                    
                    try:
                        balance = await exchange.fetch_balance()
                        usdt_balance = balance.get('USDT', {}).get('free', 0)
                        self.balances[exchange_id] = usdt_balance
                        logger.info(f"✅ {exchange_id.upper()}: TRADING | Баланс: ${usdt_balance:.2f}")
                    except:
                        self.balances[exchange_id] = 0
                        logger.info(f"✅ {exchange_id.upper()}: TRADING | Баланс: проверка...")
                else:
                    exchange = exchange_class({
                        'enableRateLimit': True,
                        'options': {'defaultType': 'spot'}
                    })
                    await exchange.load_markets()
                    self.exchanges[exchange_id] = exchange
                    self.balances[exchange_id] = 0
                    logger.info(f"📡 {exchange_id.upper()}: PUBLIC (только чтение)")
                    
            except Exception as e:
                logger.error(f"❌ {exchange_id.upper()}: {str(e)[:100]}")
                
        if not self.exchanges:
            logger.error("❌ Нет активных бирж!")
            return False
            
        trading_exchanges = [e for e, c in EXCHANGE_MODES.items() 
                           if c['mode'] == 'trading' and e in self.exchanges]
        public_exchanges = [e for e, c in EXCHANGE_MODES.items() 
                          if c['mode'] == 'public' and e in self.exchanges]
        
        logger.info(f"\n📊 РЕЖИМЫ РАБОТЫ:")
        logger.info(f"   💼 Trading: {', '.join(trading_exchanges) if trading_exchanges else 'нет'}")
        logger.info(f"   📡 Public: {', '.join(public_exchanges) if public_exchanges else 'нет'}")
        logger.info(f"   💰 Баланс: ${sum(self.balances.values()):.2f}")
        logger.info(f"   📈 Мин. прибыль: {ARBITRAGE_CONFIG['min_profit_threshold']}%")
        logger.info(f"   🎯 Пар: {len(TRADING_PAIRS)}")
        
        return True
        
    async def collect_market_data(self):
        """Параллельный сбор данных."""
        tasks = []
        for symbol in TRADING_PAIRS:
            for exchange_id in self.exchanges:
                tasks.append(self.fetch_ticker_safe(exchange_id, symbol))
                    
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        current_time = time.time()
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
                    'timestamp': current_time
                }
                
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                self.price_history[symbol].append({
                    'price': (result['bid'] + result['ask']) / 2,
                    'time': current_time
                })
                    
    async def fetch_ticker_safe(self, exchange_id: str, symbol: str):
        """Безопасное получение тикера."""
        try:
            exchange = self.exchanges[exchange_id]
            ticker = await exchange.fetch_ticker(symbol)
            
            if ticker and ticker['bid'] and ticker['ask']:
                return {
                    'exchange': exchange_id,
                    'symbol': symbol,
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'volume': ticker['quoteVolume'] or 0
                }
        except:
            pass
        return None
        
    def analyze_opportunities(self):
        """Анализ арбитража."""
        opportunities = []
        current_time = time.time()
        
        for symbol in self.prices:
            if len(self.prices[symbol]) < 2:
                continue
                
            exchanges = list(self.prices[symbol].keys())
            for i, ex1 in enumerate(exchanges):
                for ex2 in exchanges[i+1:]:
                    price1 = self.prices[symbol][ex1]
                    price2 = self.prices[symbol][ex2]
                    
                    if current_time - price1['timestamp'] > 5 or \
                       current_time - price2['timestamp'] > 5:
                        continue
                        
                    if price1['volume'] < ARBITRAGE_CONFIG['min_volume_24h'] or \
                       price2['volume'] < ARBITRAGE_CONFIG['min_volume_24h']:
                        continue
                        
                    # ex1 → ex2
                    if price2['bid'] > price1['ask']:
                        spread_pct = (price2['bid'] - price1['ask']) / price1['ask'] * 100
                        
                        if ARBITRAGE_CONFIG['use_maker_orders']:
                            buy_fee = EXCHANGE_MODES[ex1]['maker_fee'] * 100
                            sell_fee = EXCHANGE_MODES[ex2]['maker_fee'] * 100
                        else:
                            buy_fee = EXCHANGE_MODES[ex1]['taker_fee'] * 100
                            sell_fee = EXCHANGE_MODES[ex2]['taker_fee'] * 100
                            
                        net_profit = spread_pct - buy_fee - sell_fee
                        
                        if net_profit >= ARBITRAGE_CONFIG['min_profit_threshold']:
                            trade_key = f"{symbol}_{ex1}_{ex2}"
                            last_trade = self.last_trade_time.get(trade_key, 0)
                            
                            if current_time - last_trade > ARBITRAGE_CONFIG['cooldown_seconds']:
                                can_execute = (EXCHANGE_MODES[ex1]['mode'] == 'trading' or
                                             EXCHANGE_MODES[ex2]['mode'] == 'trading')
                                
                                opportunities.append({
                                    'symbol': symbol,
                                    'buy_exchange': ex1,
                                    'sell_exchange': ex2,
                                    'buy_price': price1['ask'],
                                    'sell_price': price2['bid'],
                                    'spread_pct': spread_pct,
                                    'buy_fee': buy_fee,
                                    'sell_fee': sell_fee,
                                    'net_profit': net_profit,
                                    'volume': min(price1['volume'], price2['volume']),
                                    'can_execute': can_execute,
                                    'execution_type': 'real' if can_execute else 'simulation',
                                    'timestamp': current_time
                                })
                    
                    # ex2 → ex1
                    if price1['bid'] > price2['ask']:
                        spread_pct = (price1['bid'] - price2['ask']) / price2['ask'] * 100
                        
                        if ARBITRAGE_CONFIG['use_maker_orders']:
                            buy_fee = EXCHANGE_MODES[ex2]['maker_fee'] * 100
                            sell_fee = EXCHANGE_MODES[ex1]['maker_fee'] * 100
                        else:
                            buy_fee = EXCHANGE_MODES[ex2]['taker_fee'] * 100
                            sell_fee = EXCHANGE_MODES[ex1]['taker_fee'] * 100
                            
                        net_profit = spread_pct - buy_fee - sell_fee
                        
                        if net_profit >= ARBITRAGE_CONFIG['min_profit_threshold']:
                            trade_key = f"{symbol}_{ex2}_{ex1}"
                            last_trade = self.last_trade_time.get(trade_key, 0)
                            
                            if current_time - last_trade > ARBITRAGE_CONFIG['cooldown_seconds']:
                                can_execute = (EXCHANGE_MODES[ex1]['mode'] == 'trading' or
                                             EXCHANGE_MODES[ex2]['mode'] == 'trading')
                                
                                opportunities.append({
                                    'symbol': symbol,
                                    'buy_exchange': ex2,
                                    'sell_exchange': ex1,
                                    'buy_price': price2['ask'],
                                    'sell_price': price1['bid'],
                                    'spread_pct': spread_pct,
                                    'buy_fee': buy_fee,
                                    'sell_fee': sell_fee,
                                    'net_profit': net_profit,
                                    'volume': min(price1['volume'], price2['volume']),
                                    'can_execute': can_execute,
                                    'execution_type': 'real' if can_execute else 'simulation',
                                    'timestamp': current_time
                                })
                    
        opportunities.sort(key=lambda x: x['net_profit'], reverse=True)
        
        if opportunities:
            best = opportunities[0]
            if best['net_profit'] > self.statistics['best_opportunity']['profit']:
                self.statistics['best_opportunity'] = {
                    'profit': best['net_profit'],
                    'route': f"{best['symbol']}: {best['buy_exchange']} → {best['sell_exchange']}"
                }
                
        return opportunities
        
    async def execute_opportunity(self, opportunity):
        """Исполнение арбитража."""
        symbol = opportunity['symbol']
        buy_exchange = opportunity['buy_exchange']
        sell_exchange = opportunity['sell_exchange']
        
        self.statistics['total_opportunities'] += 1
        
        logger.info("=" * 60)
        logger.info(f"🎯 АРБИТРАЖ: {symbol}")
        logger.info(f"   📊 {buy_exchange.upper()} → {sell_exchange.upper()}")
        logger.info(f"   💹 Спред: {opportunity['spread_pct']:.3f}%")
        logger.info(f"   💸 Комиссии: {opportunity['buy_fee']:.3f}% + {opportunity['sell_fee']:.3f}%")
        logger.info(f"   💰 Прибыль: {opportunity['net_profit']:.3f}%")
        logger.info(f"   📈 Объем: ${opportunity['volume']:,.0f}")
        logger.info(f"   🔧 Режим: {opportunity['execution_type'].upper()}")
        
        amount = ARBITRAGE_CONFIG['position_size_usd'] / opportunity['buy_price']
        profit_usd = ARBITRAGE_CONFIG['position_size_usd'] * opportunity['net_profit'] / 100
        
        logger.info(f"   🎮 СИМУЛЯЦИЯ:")
        logger.info(f"      Покупка: {amount:.4f} @ ${opportunity['buy_price']:.2f}")
        logger.info(f"      Продажа: {amount:.4f} @ ${opportunity['sell_price']:.2f}")
        logger.info(f"   ✅ Прибыль: ${profit_usd:.2f}")
        
        self.statistics['simulated_trades'] += 1
        self.statistics['simulated_profit'] += profit_usd
        
        trade_key = f"{symbol}_{buy_exchange}_{sell_exchange}"
        self.last_trade_time[trade_key] = time.time()
        
        self.save_opportunity(opportunity, profit_usd)
        return True
        
    def save_opportunity(self, opportunity, profit_usd):
        """Сохранение информации."""
        filename = 'hybrid_opportunities.json'
        
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as f:
                    data = json.load(f)
            else:
                data = []
                
            data.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': opportunity['symbol'],
                'route': f"{opportunity['buy_exchange']} → {opportunity['sell_exchange']}",
                'spread_pct': opportunity['spread_pct'],
                'net_profit_pct': opportunity['net_profit'],
                'profit_usd': profit_usd,
                'type': opportunity['execution_type'],
                'total_profit': self.statistics['simulated_profit'] + self.statistics['real_profit']
            })
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения: {e}")
            
    def calculate_volatility(self, symbol):
        """Расчет волатильности."""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 10:
            return 0
            
        history = self.price_history[symbol][-50:]
        prices = [h['price'] for h in history]
        
        avg_price = sum(prices) / len(prices)
        variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        volatility = (variance ** 0.5) / avg_price * 100
        
        return volatility
        
    async def print_status(self):
        """Вывод статуса."""
        current_time = time.time()
        
        active_prices = 0
        for symbol_prices in self.prices.values():
            for price in symbol_prices.values():
                if current_time - price['timestamp'] < 10:
                    active_prices += 1
                    
        volatilities = {}
        for symbol in self.price_history:
            vol = self.calculate_volatility(symbol)
            if vol > 0:
                volatilities[symbol] = vol
                
        top_volatile = sorted(volatilities.items(), key=lambda x: x[1], reverse=True)[:3]
        
        logger.info("-" * 60)
        logger.info("📊 СТАТУС:")
        logger.info(f"   🔄 Активных цен: {active_prices}")
        logger.info(f"   🎯 Возможностей: {self.statistics['total_opportunities']}")
        logger.info(f"   🎮 Сделок: {self.statistics['simulated_trades']}")
        logger.info(f"   💰 Прибыль: ${self.statistics['simulated_profit']:.2f}")
        
        if self.statistics['best_opportunity']['route']:
            logger.info(f"   🏆 Лучшая: {self.statistics['best_opportunity']['profit']:.3f}%")
            logger.info(f"      {self.statistics['best_opportunity']['route']}")
            
        if top_volatile:
            logger.info(f"   📈 Волатильность:")
            for symbol, vol in top_volatile[:2]:
                logger.info(f"      {symbol}: {vol:.2f}%")
                
    async def main_loop(self):
        """Основной цикл."""
        scan_interval = 2
        status_interval = 30
        cleanup_interval = 300
        
        last_status_time = 0
        last_cleanup_time = 0
        
        while self.is_running:
            try:
                current_time = time.time()
                
                await self.collect_market_data()
                opportunities = self.analyze_opportunities()
                
                if opportunities:
                    best = opportunities[0]
                    await self.execute_opportunity(best)
                    
                if current_time - last_status_time > status_interval:
                    await self.print_status()
                    last_status_time = current_time
                    
                if current_time - last_cleanup_time > cleanup_interval:
                    for symbol in self.price_history:
                        self.price_history[symbol] = self.price_history[symbol][-100:]
                    last_cleanup_time = current_time
                    
                await asyncio.sleep(scan_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                await asyncio.sleep(5)
                
    async def run(self):
        """Запуск бота."""
        if not await self.initialize():
            return
            
        logger.info("\n" + "=" * 60)
        logger.info("🚀 ЗАПУСК ГИБРИДНОГО РЕЖИМА")
        logger.info("=" * 60)
        
        try:
            await self.main_loop()
        except KeyboardInterrupt:
            logger.info("\n⏹️  Остановка...")
        finally:
            for exchange in self.exchanges.values():
                await exchange.close()
                
            logger.info("\n" + "=" * 60)
            logger.info("📈 ИТОГИ:")
            logger.info(f"   🎯 Возможностей: {self.statistics['total_opportunities']}")
            logger.info(f"   🎮 Сделок: {self.statistics['simulated_trades']}")
            logger.info(f"   💰 Прибыль: ${self.statistics['simulated_profit']:.2f}")
            
            if self.statistics['simulated_trades'] > 0:
                avg = self.statistics['simulated_profit'] / self.statistics['simulated_trades']
                logger.info(f"   📊 Средняя: ${avg:.2f}")
                
            if self.statistics['best_opportunity']['route']:
                logger.info(f"   🏆 Лучшая: {self.statistics['best_opportunity']['profit']:.3f}%")
                
            logger.info("=" * 60)
            
async def main():
    bot = HybridArbitrageBot()
    await bot.run()
    
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("   HYBRID ARBITRAGE BOT")
    print("   Комбинированный режим: Trading + Public")
    print("=" * 60 + "\n")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Завершение...")
