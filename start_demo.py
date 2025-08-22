#!/usr/bin/env python3
"""
Demo Launcher for Multi-Exchange Arbitrage Bot
Starts the bot in demo mode with paper trading
"""

import asyncio
import logging
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
from colorama import init as colorama_init, Fore, Style
from tabulate import tabulate

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
colorama_init(autoreset=True)

# Import after logging is configured so our demo logging setup is not overridden
from production_multi_exchange_bot import ProductionArbitrageBot
import production_config as config

def _print_demo_banner():
    """Цветной стартовый баннер для DEMO режима."""
    try:
        mode = config.TRADING_CONFIG.get('mode', 'demo').upper()
        ws_source = 'WebSocket' if config.TRADING_CONFIG.get('use_websocket', True) else 'REST only'
        header = f"🚀 DEMO ARBITRAGE BOT | {mode} | Data: {ws_source}"
        print("\n" + Fore.CYAN + "═" * 80)
        print(Fore.CYAN + header)
        print(Fore.CYAN + "═" * 80)

        # Биржи
        ex_rows = []
        for ex_id, ex_cfg in config.EXCHANGES_CONFIG.items():
            if ex_cfg.get('enabled', False):
                ex_rows.append([
                    ex_id,
                    ex_cfg.get('name', ex_id.upper()),
                    'ON' if ex_cfg.get('websocket', False) else 'OFF',
                    'ON' if ex_cfg.get('poll_rest', False) else 'OFF',
                    f"{ex_cfg.get('fee', 0.0) * 100:.2f}%"
                ])
        if ex_rows:
            print(Fore.YELLOW + "Биржи (включены):")
            print(tabulate(ex_rows, headers=['ID', 'Биржа', 'WS', 'REST', 'Комиссия'], tablefmt='github'))

        # Ключевые параметры торговли
        conf_rows = [
            ['Min Profit %', config.TRADING_CONFIG.get('min_profit_threshold')],
            ['Scan Interval (s)', config.TRADING_CONFIG.get('scan_interval')],
            ['Slippage %', config.TRADING_CONFIG.get('slippage_tolerance', 0.0)],
            ['Pair Cooldown (s)', config.TRADING_CONFIG.get('pair_cooldown_seconds')],
            ['Position Size $', config.TRADING_CONFIG.get('position_size_usd')],
            ['Inter-Exchange', config.TRADING_CONFIG.get('enable_inter_exchange', True)],
            ['Triangular', config.TRADING_CONFIG.get('enable_triangular', False)],
            ['Exhaustive Scan', config.TRADING_CONFIG.get('enable_exhaustive_pair_scanning', False)],
            ['Demo Balance $', config.TRADING_CONFIG.get('demo_initial_usdt', 10000)]
        ]
        print(Fore.YELLOW + "Торговые параметры:")
        print(tabulate(conf_rows, headers=['Параметр', 'Значение'], tablefmt='github'))

        # Discovery
        dp = getattr(config, 'DYNAMIC_PAIRS_CONFIG', {})
        if dp:
            disc_rows = [
                ['Enabled', dp.get('enabled', True)],
                ['Min Exchanges', dp.get('min_exchanges')],
                ['Max Pairs', dp.get('max_pairs')],
                ['Per-Exchange Limit', dp.get('per_exchange_discovery_limit')],
                ['Priority Pairs', len(dp.get('priority_pairs', []))]
            ]
            print(Fore.YELLOW + "Discovery пар:")
            print(tabulate(disc_rows, headers=['Параметр', 'Значение'], tablefmt='github'))
        print(Fore.CYAN + "═" * 80 + "\n")
    except Exception as e:
        logger.debug(f"_print_demo_banner error: {e}")

def setup_demo_config(args=None):
    """Setup demo configuration by modifying the production config (with optional CLI overrides)."""
    # Defaults for demo
    use_ws_default = True
    min_profit_default = -0.5
    scan_interval_default = 0.25
    position_size_default = 10
    min_liquidity_default = 10
    pair_cooldown_default = 1
    max_age_default = 2.0
    demo_balance_default = 10000.0

    # Resolve CLI overrides
    use_ws = use_ws_default if (args is None or (getattr(args, 'use_ws', None) is None and not getattr(args, 'no_ws', False))) else (False if getattr(args, 'no_ws', False) else True)
    min_profit = getattr(args, 'min_profit', None)
    position_size = getattr(args, 'position_size', None)
    scan_interval = getattr(args, 'scan_interval', None)
    min_liquidity = getattr(args, 'min_liquidity', None)
    pair_cooldown = getattr(args, 'cooldown', None)
    max_age = getattr(args, 'max_age', None)
    demo_balance = getattr(args, 'demo_balance', None)
    enable_exhaustive = getattr(args, 'enable_exhaustive', False) if args else False
    enable_triangular_arg = getattr(args, 'enable_triangular', None) if args else None
    discovery_limit = getattr(args, 'discovery_limit', None) if args else None
    ioc_arg = getattr(args, 'use_ioc', None) if args else None

    # Override production settings for demo
    config.TRADING_CONFIG['mode'] = 'demo'
    config.TRADING_CONFIG['use_websocket'] = use_ws
    config.TRADING_CONFIG['min_profit_threshold'] = min_profit if (min_profit is not None) else min_profit_default
    config.TRADING_CONFIG['scan_interval'] = scan_interval if (scan_interval is not None and scan_interval > 0) else scan_interval_default
    config.TRADING_CONFIG['position_size_usd'] = position_size if (position_size is not None and position_size > 0) else position_size_default
    config.TRADING_CONFIG['min_liquidity_usd'] = min_liquidity if (min_liquidity is not None and min_liquidity > 0) else min_liquidity_default
    config.TRADING_CONFIG['pair_cooldown_seconds'] = pair_cooldown if (pair_cooldown is not None and pair_cooldown >= 0) else pair_cooldown_default
    config.TRADING_CONFIG['max_opportunity_age'] = max_age if (max_age is not None and max_age > 0) else max_age_default

    # Set demo balance
    config.TRADING_CONFIG['demo_initial_usdt'] = demo_balance if (demo_balance is not None and demo_balance > 0) else demo_balance_default

    # Scanning modes
    if enable_exhaustive:
        config.TRADING_CONFIG['enable_exhaustive_pair_scanning'] = True
    if enable_triangular_arg is not None:
        config.TRADING_CONFIG['enable_triangular'] = bool(enable_triangular_arg)

    # Discovery limits
    if discovery_limit is not None and discovery_limit > 0 and hasattr(config, 'DYNAMIC_PAIRS_CONFIG'):
        config.DYNAMIC_PAIRS_CONFIG['per_exchange_discovery_limit'] = int(discovery_limit)

    # IOC flag override
    if ioc_arg is not None:
        config.TRADING_CONFIG['use_ioc'] = bool(ioc_arg)

    # Exchanges override (e.g., --exchanges okx,bitget)
    if args and getattr(args, 'exchanges', None):
        desired = {e.strip().lower() for e in args.exchanges.split(',') if e.strip()}
        enabled_count = 0
        for ex_id in list(config.EXCHANGES_CONFIG.keys()):
            is_enabled = ex_id in desired
            if is_enabled:
                enabled_count += 1
            config.EXCHANGES_CONFIG[ex_id]['enabled'] = is_enabled
        if enabled_count < 2:
            logger.warning("⚠️ Less than 2 exchanges enabled via CLI. Arbitrage opportunities may not be found.")

    # Pairs override (e.g., --pairs BTC/USDT,ETH/USDT)
    if args and getattr(args, 'pairs', None):
        pairs = [p.strip().upper() for p in args.pairs.split(',') if p.strip()]
        if hasattr(config, 'DYNAMIC_PAIRS_CONFIG'):
            config.DYNAMIC_PAIRS_CONFIG['priority_pairs'] = pairs
            # Ensure we at least consider these pairs
            config.DYNAMIC_PAIRS_CONFIG['max_pairs'] = max(len(pairs), config.DYNAMIC_PAIRS_CONFIG.get('max_pairs', 50))

    # Strictly limit to only provided pairs if requested
    only_pairs_flag = bool(getattr(args, 'only_pairs', False)) if args else False
    config.TRADING_CONFIG['only_pairs'] = only_pairs_flag
    if only_pairs_flag and not (args and getattr(args, 'pairs', None)):
        logger.warning("⚠️ --only-pairs set but no --pairs provided; active pairs will be empty")

    logger.info("🎮 Demo Configuration Setup")
    logger.info(f"  Mode: {config.TRADING_CONFIG['mode']}")
    logger.info(f"  Demo Balance: ${config.TRADING_CONFIG.get('demo_initial_usdt', 10000)}")
    logger.info(f"  Min Profit: {config.TRADING_CONFIG['min_profit_threshold']}%")
    logger.info(f"  WebSocket: {config.TRADING_CONFIG.get('use_websocket', False)}")
    logger.info(f"  Triangular: {config.TRADING_CONFIG.get('enable_triangular', False)}")
    logger.info(f"  Exhaustive Scan: {config.TRADING_CONFIG.get('enable_exhaustive_pair_scanning', False)}")
    logger.info(f"  IOC: {config.TRADING_CONFIG.get('use_ioc', False)}")
    if hasattr(config, 'DYNAMIC_PAIRS_CONFIG'):
        logger.info(f"  Discovery Limit per exchange: {config.DYNAMIC_PAIRS_CONFIG.get('per_exchange_discovery_limit')}")

async def run_demo(args=None):
    """Run the bot in demo mode"""
    logger.info("=" * 50)
    logger.info("🚀 Starting Multi-Exchange Arbitrage Bot (DEMO MODE)")
    logger.info("=" * 50)
    
    # Setup demo configuration
    setup_demo_config(args)
    
    # Validate configuration
    errors, warnings = config.validate_config()
    if errors:
        logger.error("Configuration errors found:")
        for error in errors:
            logger.error(f"  ❌ {error}")
        return
    if warnings:
        logger.warning("Configuration warnings:")
        for w in warnings:
            logger.warning(f"  ⚠️ {w}")
    
    # Pretty start banner
    try:
        _print_demo_banner()
    except Exception:
        pass

    # Create and initialize bot
    bot = ProductionArbitrageBot()
    
    try:
        # Start monitoring
        logger.info("\n🔍 Starting arbitrage scanning...")
        logger.info("Press Ctrl+C to stop\n")
        
        # Run the bot
        run_seconds = getattr(args, 'run_seconds', 0) if args else 0
        if run_seconds and run_seconds > 0:
            logger.info(f"⏱️ Timed run: stopping after {run_seconds} seconds")
            task = asyncio.create_task(bot.start())
            try:
                await asyncio.sleep(run_seconds)
            finally:
                await bot.stop()
                # Give tasks chance to finish
                try:
                    await asyncio.wait_for(task, timeout=5)
                except Exception:
                    pass
        else:
            await bot.start()
        
    except KeyboardInterrupt:
        logger.info("\n⚠️ Received shutdown signal...")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
    finally:
        # Stop the bot
        logger.info("🧹 Stopping bot...")
        try:
            await bot.stop()
        except Exception:
            pass
        
        # Show final statistics
        logger.info("\n📈 Final Statistics:")
        logger.info(f"  Total Scans: {bot.statistics['scans']}")
        logger.info(f"  Opportunities Found: {bot.statistics['opportunities_found']}")
        logger.info(f"  Trades Executed: {bot.statistics['trades_executed']}")
        
        if bot.statistics['trades_executed'] > 0:
            logger.info(f"  Total Profit: ${bot.statistics.get('total_profit_usd', 0):.2f}")
        
        logger.info("\n✅ Demo session completed")
        logger.info(f"📁 Logs saved to: logs/")

def parse_args():
    parser = argparse.ArgumentParser(description="Demo launcher for Multi-Exchange Arbitrage Bot")
    parser.add_argument('--run-seconds', type=float, default=0, help='Run duration in seconds (0 = until Ctrl+C)')
    parser.add_argument('--min-profit', type=float, help='Min profit threshold in % (e.g., 0.1)')
    parser.add_argument('--position-size', type=float, help='Position size in USD (default demo 10)')
    parser.add_argument('--scan-interval', type=float, help='Scan interval in seconds (default demo 0.25)')
    parser.add_argument('--min-liquidity', type=float, help='Min liquidity in USD (default demo 10)')
    parser.add_argument('--cooldown', type=float, help='Pair cooldown seconds (default demo 1)')
    parser.add_argument('--max-age', type=float, help='Max opportunity age seconds (default demo 2.0)')
    parser.add_argument('--demo-balance', type=float, help='Initial demo USDT balance (default 10000)')
    parser.add_argument('--use-ws', dest='use_ws', action='store_true', help='Force use WebSocket data source')
    parser.add_argument('--no-ws', dest='no_ws', action='store_true', help='Disable WebSocket (REST polling only)')
    parser.add_argument('--exchanges', type=str, help='Comma-separated exchange ids to enable (e.g., okx,bitget)')
    parser.add_argument('--pairs', type=str, help='Comma-separated pairs to prioritize (e.g., BTC/USDT,ETH/USDT)')
    parser.add_argument('--only-pairs', action='store_true', help='Strictly limit active pairs to the provided --pairs list')
    parser.add_argument('--log-level', type=str, choices=['DEBUG','INFO','WARNING','ERROR','CRITICAL'], help='Root log level')
    # New scanning/discovery controls
    parser.add_argument('--enable-exhaustive', action='store_true', help='Enable exhaustive pair scanning for inter-exchange mode')
    tri_group = parser.add_mutually_exclusive_group()
    tri_group.add_argument('--enable-triangular', dest='enable_triangular', action='store_true', help='Enable triangular arbitrage scanning')
    tri_group.add_argument('--no-triangular', dest='enable_triangular', action='store_false', help='Disable triangular arbitrage scanning')
    parser.add_argument('--discovery-limit', type=int, help='Limit number of pairs per exchange during dynamic discovery')
    # IOC controls
    ioc_group = parser.add_mutually_exclusive_group()
    ioc_group.add_argument('--ioc', dest='use_ioc', action='store_true', help='Enable IOC (Immediate-Or-Cancel) on supported exchanges')
    ioc_group.add_argument('--no-ioc', dest='use_ioc', action='store_false', help='Disable IOC')
    parser.set_defaults(use_ioc=None)
    return parser.parse_args()

def main():
    """Main entry point"""
    print("""
    ╔════════════════════════════════════════════╗
    ║   Multi-Exchange Arbitrage Bot - DEMO     ║
    ║         Safe Paper Trading Mode            ║
    ╚════════════════════════════════════════════╝
    """)
    
    args = parse_args()
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ required")
        sys.exit(1)
    
    # Check dependencies
    try:
        import ccxt  # noqa: F401
        import aiohttp  # noqa: F401
        import pandas  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        sys.exit(1)

    # Apply log level override if provided
    if args.log_level:
        level = getattr(logging, args.log_level.upper(), logging.INFO)
        logging.getLogger().setLevel(level)
        logger.setLevel(level)

    # Optionally enable uvloop if configured and available
    try:
        if getattr(config, 'PERFORMANCE_CONFIG', {}).get('use_uvloop', False):
            import uvloop  # type: ignore
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("uvloop enabled")
    except Exception:
        # uvloop is optional; ignore if unavailable
        pass
    
    # Run async main
    try:
        asyncio.run(run_demo(args))
    except KeyboardInterrupt:
        print("\n👋 Demo stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
