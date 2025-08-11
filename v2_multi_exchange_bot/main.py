import asyncio
import logging
import os
import subprocess
from datetime import datetime
from itertools import permutations

import pandas as pd

import config
from exchanges import import_exchange_class

# -------- Config fallbacks --------
INTER_EXCHANGE_ARBITRAGE_ENABLED = getattr(config, 'INTER_EXCHANGE_ARBITRAGE_ENABLED', True)
TRIANGULAR_ARBITRAGE_ENABLED = getattr(config, 'TRIANGULAR_ARBITRAGE_ENABLED', True)
MIN_PROFIT_THRESHOLD = float(getattr(config, 'MIN_PROFIT_THRESHOLD', 0.0))  # percent
POLLING_INTERVAL = float(getattr(config, 'POLLING_INTERVAL', 1.0))
DEFAULT_SYMBOLS = getattr(config, 'INTER_EXCHANGE_SYMBOLS', ['BTC/USDT', 'ETH/USDT', 'ETH/BTC'])
FEES = getattr(config, 'FEES', {'binance': 0.00075, 'kraken': 0.0016})  # decimal per trade (cheapest realistic: BNB discount + Kraken maker)

RESULTS_DIR = 'results'
LOGS_DIR = 'logs'
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, f'arbitrage_bot.log')),
        logging.StreamHandler()
    ]
)

# -------- Helpers --------

def get_symbols_for_triangular_chain(chain):
    # chain like ['USDT','BTC','ETH'] -> symbols: ['BTC/USDT', 'ETH/BTC', 'ETH/USDT']
    base, mid, quote = chain  # base=USDT, mid=BTC, quote=ETH
    # Use common listed pairs: mid/base, quote/mid, quote/base
    return [f"{mid}/{base}", f"{quote}/{mid}", f"{quote}/{base}"]


def best_pairwise_opportunities(exchanges, symbols):
    now = datetime.utcnow().isoformat()
    rows = []
    names = list(exchanges.keys())
    for symbol in symbols:
        for buy, sell in permutations(names, 2):
            buy_ex = exchanges[buy]
            sell_ex = exchanges[sell]
            bt = getattr(buy_ex, 'tickers', {}).get(symbol)
            st = getattr(sell_ex, 'tickers', {}).get(symbol)
            if not bt or not st:
                continue
            try:
                buy_ask = float(bt['ask'])
                sell_bid = float(st['bid'])
            except Exception:
                continue
            if buy_ask <= 0:
                continue
            gross = (sell_bid - buy_ask) / buy_ask * 100.0
            net = gross - (FEES.get(buy, 0) + FEES.get(sell, 0)) * 100.0
            if net >= MIN_PROFIT_THRESHOLD:
                logging.info(f"OPPORTUNITY | {symbol} | Buy: {buy}, Sell: {sell} | Gross: {gross:.3f}%, Net: {net:.3f}%")
            rows.append({
                'timestamp': now,
                'symbol': symbol,
                'buy_exchange': buy,
                'sell_exchange': sell,
                'profit_gross_percent': round(gross, 6),
                'profit_net_percent': round(net, 6),
            })
    return rows


def triangular_opportunities_for_exchange(name, ex, chains):
    now = datetime.utcnow().isoformat()
    rows = []
    for chain in chains:
        try:
            symbols = get_symbols_for_triangular_chain(chain)
            t1 = getattr(ex, 'tickers', {}).get(symbols[0])  # mid/quote, e.g., BTC/USDT (bid/ask in quote)
            t2 = getattr(ex, 'tickers', {}).get(symbols[1])  # base/mid, e.g., USDT/BTC (but we use ETH/BTC)
            t3 = getattr(ex, 'tickers', {}).get(symbols[2])  # base/quote, e.g., ETH/USDT
            if not (t1 and t2 and t3):
                continue
            # USDT -> BTC -> ETH -> USDT example mapping for ['USDT','BTC','ETH'] with symbols [BTC/USDT, ETH/BTC, ETH/USDT]
            # Buy BTC with USDT at ask of BTC/USDT
            price_usdt_btc = float(t1['ask'])
            # Buy ETH with BTC at ask of ETH/BTC (price in BTC)
            price_btc_eth = float(t2['ask'])
            # Sell ETH for USDT at bid of ETH/USDT
            price_eth_usdt = float(t3['bid'])
            if price_usdt_btc <= 0 or price_btc_eth <= 0:
                continue
            init = 100.0
            btc = init / price_usdt_btc
            eth = btc / price_btc_eth
            final = eth * price_eth_usdt
            gross = (final - init) / init * 100.0
            # three trades on same exchange
            net = gross - (3 * FEES.get(name, 0)) * 100.0
            chain_str = f"{chain[2]}->{chain[1]}->{chain[0]} (reverse)" if final < init else f"{chain[0]}->{chain[1]}->{chain[2]}"
            rows.append({
                'timestamp': now,
                'exchange': name,
                'chain': chain_str,
                'profit_net_percent': round(net, 6),
            })
        except Exception:
            continue
    return rows


async def main():
    logging.info("Initializing bot...")

    enabled = {n: c for n, c in getattr(config, 'EXCHANGES', {}).items() if c.get('enabled', True)}
    if not enabled:
        logging.error('No enabled exchanges in config.EXCHANGES')
        return

    # Instantiate exchanges
    exchanges = {}
    for name, conf in enabled.items():
        cls = import_exchange_class(conf['class'])
        api = conf.get('api_config', {})
        exchanges[name] = cls(
            apiKey=api.get('apiKey'),
            secret=api.get('secret'),
        )

    # Determine symbols to track
    symbols = set(DEFAULT_SYMBOLS)
    # Optionally expand from triangular chains if present
    chains = getattr(config, 'TRIANGULAR_CHAINS', [['USDT', 'BTC', 'ETH']])
    for ch in chains:
        symbols.update(get_symbols_for_triangular_chain(ch))
    symbols = sorted(symbols)
    logging.info(f"Combined list of symbols to watch: {symbols}")

    # Connect exchanges
    await asyncio.gather(*[ex.connect(symbols) for ex in exchanges.values()])
    logging.info("Successfully connected to all exchanges.")

    collected_cross = []
    collected_tri = []

    try:
        logging.info("Starting data collection for arbitrage analysis...")
        while True:
            if INTER_EXCHANGE_ARBITRAGE_ENABLED:
                collected_cross.extend(best_pairwise_opportunities(exchanges, symbols))
            if TRIANGULAR_ARBITRAGE_ENABLED:
                for name, ex in exchanges.items():
                    collected_tri.extend(triangular_opportunities_for_exchange(name, ex, chains))
            await asyncio.sleep(POLLING_INTERVAL)
    except asyncio.CancelledError:
        logging.info("Data collection loop cancelled.")
    except KeyboardInterrupt:
        logging.info("Shutdown requested by user.")
    finally:
        # One last snapshot evaluation to ensure we have at least one batch of data
        try:
            if INTER_EXCHANGE_ARBITRAGE_ENABLED:
                collected_cross.extend(best_pairwise_opportunities(exchanges, symbols))
            if TRIANGULAR_ARBITRAGE_ENABLED:
                for name, ex in exchanges.items():
                    collected_tri.extend(triangular_opportunities_for_exchange(name, ex, chains))
        except Exception as e:
            logging.warning(f"Final snapshot evaluation failed: {e}")

        # Disconnect (после снимка)
        await asyncio.gather(*[ex.disconnect() for ex in exchanges.values()])
        logging.info("All exchanges disconnected.")

        ts = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save cross-exchange CSV
        if collected_cross:
            cross_file = os.path.join(RESULTS_DIR, f'cross_arbitrage_data_{ts}.csv')
            pd.DataFrame(collected_cross).to_csv(cross_file, index=False)
            logging.info(f"Cross-exchange data saved to {cross_file}.")
            try:
                subprocess.run(['python3', 'generate_report.py', cross_file], check=True)
                logging.info("Cross-exchange PNG report generated.")
            except Exception as e:
                logging.error(f"Failed to generate cross-exchange report: {e}")

        # Save triangular CSV
        if collected_tri:
            tri_file = os.path.join(RESULTS_DIR, f'triangular_arbitrage_data_{ts}.csv')
            pd.DataFrame(collected_tri).to_csv(tri_file, index=False)
            logging.info(f"Triangular data saved to {tri_file}.")
            try:
                subprocess.run(['python3', 'generate_triangular_report.py', tri_file], check=True)
                logging.info("Triangular PNG report generated.")
            except Exception as e:
                logging.error(f"Failed to generate triangular report: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # suppress final traceback if user hits Ctrl+C during shutdown
        pass
