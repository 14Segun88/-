#!/usr/bin/env python3
"""
Bitget WebSocket smoke test (safe, no trading)
- Connects to Bitget spot WS (public endpoint by default)
- Optionally sends login (HMAC-SHA256) using API keys from production_config.py
- Subscribes to public ticker channel for a few USDT pairs
- Runs for N seconds and prints summary

Notes:
- This is a read-only test. It does NOT place orders or touch private channels beyond optional login.
- Uses the same auth scheme as websocket_manager.py
"""

import asyncio
import json
import time
import sys
import os
import hmac
import hashlib
import base64
import argparse
from typing import Dict

# Ensure local imports work when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import production_config as config
import websockets


class BitgetWSTester:
    def __init__(self, duration_sec: int = 20, no_login: bool = False):
        self.duration_sec = duration_sec
        self.url = config.EXCHANGES_CONFIG['bitget']['ws_url']
        self.api_key = config.API_KEYS.get('bitget', {}).get('apiKey') or config.API_KEYS.get('bitget', {}).get('api_key')
        self.secret = config.API_KEYS.get('bitget', {}).get('secret')
        self.passphrase = config.API_KEYS.get('bitget', {}).get('passphrase', '')
        self.use_paptrading = (
            str(config.API_KEYS.get('bitget', {}).get('env', '')).lower() == 'demo'
        ) or (config.TRADING_CONFIG.get('mode') in ('demo', 'paper'))
        self.no_login = no_login
        self.msg_total = 0
        self.ticker_msgs = 0
        self.login_ack = False
        self.last_prices: Dict[str, Dict[str, float]] = {}
        self._printed_first_msgs = 0

    def _build_login(self) -> dict:
        ts = str(int(time.time()))
        message = ts + 'GET' + '/user/verify'
        sign = base64.b64encode(hmac.new(self.secret.encode(), message.encode(), hashlib.sha256).digest()).decode()
        return {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": ts,
                "sign": sign
            }]
        }

    def _build_subscribe(self, inst_id: str) -> dict:
        # Public ticker channel for spot (Bitget: instType 'SP', instId '<SYMBOL>')
        inst_id_norm = inst_id.replace('/', '').upper()
        return {
            "op": "subscribe",
            "args": [{
                "instType": "SPOT",
                "channel": "ticker",
                "instId": inst_id_norm
            }]
        }

    def _update_from_snapshot(self, data: dict):
        # Matches websocket_manager.py logic for Bitget ticker snapshot
        for item in data.get('data', []):
            inst = item.get('instId', '')
            if not inst:
                continue
            sym = inst  # e.g. BTCUSDT
            if len(sym) > 4:
                base, quote = sym[:-4], sym[-4:]
            else:
                base, quote = sym, ''
            symbol_std = f"{base}/{quote}" if quote else sym
            # Support both field variants seen in docs: bidPr/askPr and bestBid/bestAsk
            bid_raw = item.get('bidPr') if item.get('bidPr') is not None else item.get('bestBid')
            ask_raw = item.get('askPr') if item.get('askPr') is not None else item.get('bestAsk')
            bid = float(bid_raw or 0)
            ask = float(ask_raw or 0)
            if bid > 0 and ask > 0:
                self.last_prices[symbol_std] = {"bid": bid, "ask": ask}
                self.ticker_msgs += 1

    async def run(self):
        # Basic validation of keys
        if not self.api_key or not self.secret:
            print("❌ Bitget API keys missing in production_config.py (apiKey/secret)")
            if not self.no_login:
                # If no keys and we planned to login, we must stop.
                return
            else:
                print("ℹ️ Proceeding without login as --no-login is set")

        symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
        print("\n" + "="*60)
        print("🔌 Bitget WS Auth Test")
        print("="*60)
        print(f"Endpoint: {self.url}")
        print(f"Duration: {self.duration_sec}s")
        print(f"Symbols: {', '.join(symbols)}")
        if self.use_paptrading:
            print("Bitget: using PAPTRADING=1 header (demo)")

        # If per-exchange proxy flag is False, clear HTTP(S)_PROXY env vars to force direct connection
        prev_env = {}
        cleared_proxies = False
        use_proxy = config.EXCHANGES_CONFIG.get('bitget', {}).get('use_proxy', False)
        if not use_proxy:
            cleared_proxies = True
            print("Bitget: use_proxy=False — clearing HTTP(S)_PROXY env vars for direct connection during this test")
            for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                if k in os.environ:
                    prev_env[k] = os.environ.pop(k)

        try:
            headers = {'PAPTRADING': '1'} if self.use_paptrading else None
            async with websockets.connect(
                    self.url,
                    extra_headers=headers,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10,
            ) as ws:
                # Optional login (skip for public-only test)
                if not self.no_login:
                    login_msg = self._build_login()
                    await ws.send(json.dumps(login_msg))
                    print("→ Login sent")
                else:
                    print("→ Skipping login (public WS test)")

                # Subscribe to tickers
                for inst in symbols:
                    await ws.send(json.dumps(self._build_subscribe(inst)))
                print(f"→ Subscribed to {len(symbols)} tickers")

                start = time.time()
                while time.time() - start < self.duration_sec:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=2)
                        self.msg_total += 1
                        data = None
                        try:
                            data = json.loads(raw)
                        except Exception:
                            # Not JSON? ignore
                            continue

                        # Heuristic: print first few messages for visibility
                        if self._printed_first_msgs < 3:
                            print(f"⇢ {data}")
                            self._printed_first_msgs += 1

                        # Try to detect login ack heuristically
                        if not self.login_ack and isinstance(data, dict):
                            if ('login' in str(data.get('event', '')).lower()) or \
                               ('login' in str(data.get('action', '')).lower()) or \
                               ('op' in data and str(data.get('op')).lower() == 'login'):
                                self.login_ack = True

                        # Ticker handling (snapshot or update)
                        if isinstance(data, dict) and data.get('action') in ('snapshot', 'update'):
                            self._update_from_snapshot(data)

                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"⚠️ recv error: {e}")
                        await asyncio.sleep(0.5)
                        continue

        except Exception as e:
            print(f"❌ Connection error: {e}")
            return
        finally:
            if cleared_proxies:
                # Restore any env vars we cleared
                for k, v in prev_env.items():
                    os.environ[k] = v

        # Summary
        print("\n" + "="*60)
        print("📊 Bitget WS Test Summary")
        print("="*60)
        print(f"Messages total: {self.msg_total}")
        print(f"Ticker snapshots parsed: {self.ticker_msgs}")
        print(f"Login ack heuristic: {'✅' if self.login_ack else '❓ not detected'}")
        if self.last_prices:
            # Print a few symbols
            for i, (sym, pa) in enumerate(self.last_prices.items()):
                print(f"  {sym}: bid {pa['bid']}, ask {pa['ask']}")
                if i >= 2:
                    break
        else:
            print("  No ticker prices parsed from snapshots")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bitget WS smoke test (public, optional login)")
    parser.add_argument("--duration", type=int, default=20, help="Duration to run the test in seconds")
    parser.add_argument("--no-login", action="store_true", help="Do not send login (for public endpoint test)")
    args = parser.parse_args()

    tester = BitgetWSTester(duration_sec=args.duration, no_login=args.no_login)
    asyncio.run(tester.run())
