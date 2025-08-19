#!/usr/bin/env python3
"""
Hybrid Arbitrage Bot - Combines MEXC API trading with OKX/KuCoin public data
Uses MEXC for actual trading (0% maker fees) and other exchanges for price discovery
"""

import asyncio
import ccxt.async_support as ccxt
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class ArbitrageOpportunity:
    """Represents an arbitrage opportunity"""
    pair: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float
    net_profit_pct: float
    timestamp: datetime
    volume_available: float

class HybridArbitrageBot:
    """
    Hybrid bot that uses MEXC for trading and other exchanges for price discovery
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.exchanges = {}
        self.orderbooks = {}
        self.balances = {}
        self.opportunities = []
        self.executed_trades = []
        self.last_trade_time = {}
        
        # Trading parameters
        self.min_profit_threshold = config.get('MIN_PROFIT_THRESHOLD', 0.05)
        self.position_size = config.get('POSITION_SIZE_USD', 100)
        self.trade_cooldown = config.get('TRADE_COOLDOWN_SECONDS', 30)
        self.max_open_positions = config.get('MAX_OPEN_POSITIONS', 5)
        
    async def initialize(self):
        """Initialize exchange connections"""
        logger.info("Initializing Hybrid Arbitrage Bot...")
        
        # MEXC with API keys for trading
        if self.config.get('MEXC_API_KEY'):
            self.exchanges['mexc'] = ccxt.mexc({
                'apiKey': self.config['MEXC_API_KEY'],
                'secret': self.config['MEXC_SECRET_KEY'],
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',
                    'adjustForTimeDifference': True
                }
            })
            logger.info("✅ MEXC initialized with API keys (trading mode)")
        else:
            logger.warning("⚠️ MEXC API keys not found, using public data only")
            self.exchanges['mexc'] = ccxt.mexc({'enableRateLimit': True})
        
        # OKX - public data only
        self.exchanges['okx'] = ccxt.okx({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info("✅ OKX initialized (public data mode)")
        
        # KuCoin - public data only  
        self.exchanges['kucoin'] = ccxt.kucoin({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info("✅ KuCoin initialized (public data mode)")
        
        # Load markets
        for name, exchange in self.exchanges.items():
            try:
                await exchange.load_markets()
                logger.info(f"Loaded {len(exchange.symbols)} markets from {name}")
            except Exception as e:
                logger.error(f"Failed to load markets from {name}: {e}")
        
        # Get common trading pairs
        await self.find_common_pairs()
        
        # Load initial balances if MEXC has API keys
        if self.config.get('MEXC_API_KEY'):
            await self.update_balances()
    
    async def find_common_pairs(self):
        """Find trading pairs available on all exchanges"""
        all_symbols = []
        for name, exchange in self.exchanges.items():
            symbols = set(s for s in exchange.symbols if '/USDT' in s and exchange.markets[s]['active'])
            all_symbols.append(symbols)
        
        # Get intersection of all symbols
        self.common_pairs = list(set.intersection(*all_symbols))
        
        # Filter to top volume pairs
        self.trading_pairs = self.common_pairs[:20]  # Top 20 pairs
        logger.info(f"Found {len(self.common_pairs)} common pairs, monitoring top {len(self.trading_pairs)}")
        logger.info(f"Monitoring pairs: {', '.join(self.trading_pairs[:10])}...")
    
    async def update_balances(self):
        """Update MEXC account balances"""
        if 'mexc' in self.exchanges and self.config.get('MEXC_API_KEY'):
            try:
                balance = await self.exchanges['mexc'].fetch_balance()
                self.balances = {
                    'USDT': balance['USDT']['free'],
                    'total': balance['USDT']['total']
                }
                logger.info(f"MEXC Balance: {self.balances['USDT']:.2f} USDT available")
            except Exception as e:
                logger.error(f"Failed to fetch MEXC balance: {e}")
                self.balances = {'USDT': self.position_size * 10, 'total': self.position_size * 10}
    
    async def fetch_orderbook(self, exchange: str, symbol: str) -> Optional[dict]:
        """Fetch orderbook for a symbol from an exchange"""
        try:
            orderbook = await self.exchanges[exchange].fetch_order_book(symbol, limit=10)
            return {
                'bids': orderbook['bids'],
                'asks': orderbook['asks'],
                'timestamp': orderbook['timestamp'],
                'exchange': exchange,
                'symbol': symbol
            }
        except Exception as e:
            logger.debug(f"Failed to fetch {symbol} from {exchange}: {e}")
            return None
    
    async def scan_arbitrage_opportunities(self):
        """Scan for arbitrage opportunities across exchanges"""
        opportunities = []
        
        for symbol in self.trading_pairs:
            # Fetch orderbooks from all exchanges
            orderbooks = {}
            for exchange in self.exchanges.keys():
                ob = await self.fetch_orderbook(exchange, symbol)
                if ob and len(ob['bids']) > 0 and len(ob['asks']) > 0:
                    orderbooks[exchange] = ob
            
            if len(orderbooks) < 2:
                continue
            
            # Find best bid and ask across exchanges
            best_bid = {'price': 0, 'exchange': '', 'volume': 0}
            best_ask = {'price': float('inf'), 'exchange': '', 'volume': 0}
            
            for exchange, ob in orderbooks.items():
                if ob['bids'][0][0] > best_bid['price']:
                    best_bid = {
                        'price': ob['bids'][0][0],
                        'exchange': exchange,
                        'volume': ob['bids'][0][1]
                    }
                if ob['asks'][0][0] < best_ask['price']:
                    best_ask = {
                        'price': ob['asks'][0][0],
                        'exchange': exchange,
                        'volume': ob['asks'][0][1]
                    }
            
            # Calculate spread
            if best_bid['price'] > 0 and best_ask['price'] < float('inf'):
                spread_pct = ((best_bid['price'] - best_ask['price']) / best_ask['price']) * 100
                
                # Calculate fees
                buy_fee = 0.001 if best_ask['exchange'] == 'mexc' else 0.001  # 0.1%
                sell_fee = 0.001 if best_bid['exchange'] == 'mexc' else 0.001
                total_fees = buy_fee + sell_fee
                
                net_profit_pct = spread_pct - (total_fees * 100)
                
                if net_profit_pct > self.min_profit_threshold:
                    opportunity = ArbitrageOpportunity(
                        pair=symbol,
                        buy_exchange=best_ask['exchange'],
                        sell_exchange=best_bid['exchange'],
                        buy_price=best_ask['price'],
                        sell_price=best_bid['price'],
                        spread_pct=spread_pct,
                        net_profit_pct=net_profit_pct,
                        timestamp=datetime.now(),
                        volume_available=min(best_bid['volume'], best_ask['volume'])
                    )
                    opportunities.append(opportunity)
                    logger.info(f"🎯 Opportunity: {symbol} {best_ask['exchange']}→{best_bid['exchange']} "
                              f"spread: {spread_pct:.3f}% net: {net_profit_pct:.3f}%")
        
        self.opportunities = sorted(opportunities, key=lambda x: x.net_profit_pct, reverse=True)
        return opportunities
    
    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute arbitrage trade if MEXC is involved"""
        symbol = opportunity.pair
        
        # Check if MEXC is involved (we can only trade on MEXC)
        if 'mexc' not in [opportunity.buy_exchange, opportunity.sell_exchange]:
            logger.info(f"Skipping {symbol}: MEXC not involved in opportunity")
            return False
        
        # Check cooldown
        if symbol in self.last_trade_time:
            time_since_last = (datetime.now() - self.last_trade_time[symbol]).seconds
            if time_since_last < self.trade_cooldown:
                logger.debug(f"Cooldown active for {symbol}: {self.trade_cooldown - time_since_last}s remaining")
                return False
        
        # Check balance
        if self.balances.get('USDT', 0) < self.position_size:
            logger.warning(f"Insufficient balance: {self.balances.get('USDT', 0):.2f} < {self.position_size}")
            return False
        
        # Calculate trade amount
        amount = self.position_size / opportunity.buy_price
        amount = min(amount, opportunity.volume_available * 0.5)  # Use max 50% of available volume
        
        try:
            if self.config.get('MEXC_API_KEY'):
                # Real trading mode
                if opportunity.buy_exchange == 'mexc':
                    # Buy on MEXC
                    order = await self.exchanges['mexc'].create_limit_buy_order(
                        symbol, amount, opportunity.buy_price
                    )
                    logger.info(f"✅ Executed BUY on MEXC: {amount:.4f} {symbol} @ {opportunity.buy_price:.4f}")
                else:
                    # Sell on MEXC
                    order = await self.exchanges['mexc'].create_limit_sell_order(
                        symbol, amount, opportunity.sell_price
                    )
                    logger.info(f"✅ Executed SELL on MEXC: {amount:.4f} {symbol} @ {opportunity.sell_price:.4f}")
                
                self.executed_trades.append({
                    'timestamp': datetime.now(),
                    'opportunity': opportunity,
                    'amount': amount,
                    'status': 'executed'
                })
            else:
                # Demo mode
                logger.info(f"📝 DEMO: Would execute {opportunity.pair} arbitrage")
                logger.info(f"   Buy {amount:.4f} on {opportunity.buy_exchange} @ {opportunity.buy_price:.4f}")
                logger.info(f"   Sell on {opportunity.sell_exchange} @ {opportunity.sell_price:.4f}")
                logger.info(f"   Expected profit: {opportunity.net_profit_pct:.3f}%")
                
                self.executed_trades.append({
                    'timestamp': datetime.now(),
                    'opportunity': opportunity,
                    'amount': amount,
                    'status': 'demo'
                })
            
            self.last_trade_time[symbol] = datetime.now()
            await self.update_balances()
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute trade: {e}")
            return False
    
    async def run(self):
        """Main bot loop"""
        logger.info("Starting Hybrid Arbitrage Bot...")
        scan_count = 0
        
        while True:
            try:
                scan_count += 1
                logger.info(f"\n=== Scan #{scan_count} ===")
                
                # Scan for opportunities
                opportunities = await self.scan_arbitrage_opportunities()
                
                if opportunities:
                    logger.info(f"Found {len(opportunities)} opportunities")
                    
                    # Try to execute best opportunity
                    for opp in opportunities[:3]:  # Try top 3
                        success = await self.execute_arbitrage(opp)
                        if success:
                            break
                else:
                    logger.info("No profitable opportunities found")
                
                # Print statistics every 10 scans
                if scan_count % 10 == 0:
                    await self.print_statistics()
                
                # Wait before next scan
                await asyncio.sleep(5)
                
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(10)
        
        # Cleanup
        await self.cleanup()
    
    async def print_statistics(self):
        """Print trading statistics"""
        logger.info("\n📊 Trading Statistics:")
        logger.info(f"Total scans: {len(self.opportunities)}")
        logger.info(f"Trades executed: {len(self.executed_trades)}")
        
        if self.executed_trades:
            df = pd.DataFrame([
                {
                    'pair': t['opportunity'].pair,
                    'profit': t['opportunity'].net_profit_pct,
                    'status': t['status']
                } for t in self.executed_trades
            ])
            logger.info(f"Average profit: {df['profit'].mean():.3f}%")
            logger.info(f"Best trade: {df['profit'].max():.3f}%")
        
        if self.balances:
            logger.info(f"Current balance: {self.balances.get('USDT', 0):.2f} USDT")
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up...")
        for exchange in self.exchanges.values():
            await exchange.close()

async def main():
    """Main entry point"""
    import os
    from dotenv import load_dotenv
    load_dotenv('config.env')
    
    config = {
        'MEXC_API_KEY': os.getenv('MEXC_API_KEY'),
        'MEXC_SECRET_KEY': os.getenv('MEXC_SECRET_KEY'),
        'MIN_PROFIT_THRESHOLD': 0.05,  # 0.05% minimum profit
        'POSITION_SIZE_USD': 100,
        'TRADE_COOLDOWN_SECONDS': 30,
        'MAX_OPEN_POSITIONS': 5
    }
    
    bot = HybridArbitrageBot(config)
    await bot.initialize()
    await bot.run()

if __name__ == '__main__':
    asyncio.run(main())
