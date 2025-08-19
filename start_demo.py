#!/usr/bin/env python3
"""
Demo Launcher for Multi-Exchange Arbitrage Bot
Starts the bot in demo mode with paper trading
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production_multi_exchange_bot import ProductionArbitrageBot
import production_config as config

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/demo_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_demo_config():
    """Setup demo configuration by modifying the production config"""
    # Override production settings for demo
    config.TRADING_CONFIG['mode'] = 'demo'
    config.TRADING_CONFIG['use_websocket'] = False  # Use REST API only for demo
    config.TRADING_CONFIG['min_profit_threshold'] = 0.10  # Lower threshold for more demos
    config.TRADING_CONFIG['scan_interval'] = 5  # Faster scanning
    
    # Set demo balance
    config.TRADING_CONFIG['demo_balance_usd'] = 10000.0
    
    logger.info("🎮 Demo Configuration Setup")
    logger.info(f"  Mode: {config.TRADING_CONFIG['mode']}")
    logger.info(f"  Demo Balance: ${config.TRADING_CONFIG.get('demo_balance_usd', 10000)}")
    logger.info(f"  Min Profit: {config.TRADING_CONFIG['min_profit_threshold']}%")
    logger.info(f"  WebSocket: {config.TRADING_CONFIG.get('use_websocket', False)}")

async def run_demo():
    """Run the bot in demo mode"""
    logger.info("=" * 50)
    logger.info("🚀 Starting Multi-Exchange Arbitrage Bot (DEMO MODE)")
    logger.info("=" * 50)
    
    # Setup demo configuration
    setup_demo_config()
    
    # Validate configuration
    errors, warnings = config.validate_config()
    if errors:
        logger.error("Configuration errors found:")
        for error in errors:
            logger.error(f"  ❌ {error}")
        return
    
    # Create and initialize bot
    bot = ProductionArbitrageBot()
    
    try:
        # Show initial status
        logger.info("\n📊 Initial Configuration:")
        logger.info(f"  Demo Balance: ${config.TRADING_CONFIG.get('demo_balance_usd', 10000)}")
        logger.info(f"  Min Profit Threshold: {config.TRADING_CONFIG['min_profit_threshold']}%")
        logger.info(f"  Position Size: ${config.TRADING_CONFIG['position_size_usd']}")
        
        # Start monitoring
        logger.info("\n🔍 Starting arbitrage scanning...")
        logger.info("Press Ctrl+C to stop\n")
        
        # Run the bot
        await bot.start()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Received shutdown signal...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        # Stop the bot
        logger.info("🧹 Stopping bot...")
        await bot.stop()
        
        # Show final statistics
        logger.info("\n📈 Final Statistics:")
        logger.info(f"  Total Scans: {bot.statistics['scans']}")
        logger.info(f"  Opportunities Found: {bot.statistics['opportunities_found']}")
        logger.info(f"  Trades Executed: {bot.statistics['trades_executed']}")
        
        if bot.statistics['trades_executed'] > 0:
            logger.info(f"  Total Profit: ${bot.statistics.get('total_profit_usd', 0):.2f}")
        
        logger.info("\n✅ Demo session completed")
        logger.info(f"📁 Logs saved to: logs/")

def main():
    """Main entry point"""
    print("""
    ╔════════════════════════════════════════════╗
    ║   Multi-Exchange Arbitrage Bot - DEMO     ║
    ║         Safe Paper Trading Mode            ║
    ╚════════════════════════════════════════════╝
    """)
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Check dependencies
    try:
        import ccxt
        import aiohttp
        import pandas
        import numpy
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)
    
    # Run async main
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\n👋 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
