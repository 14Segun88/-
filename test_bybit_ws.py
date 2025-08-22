#!/usr/bin/env python3
"""
Bybit WebSocket smoke test with proxy/VPN support (aiohttp)
- Rotates through PROXY_CONFIG endpoints then tries direct connection
- Subscribes to spot v5: orderbook.1 and tickers for BTCUSDT
- Runs for ~20 seconds and prints message counts and sample best bid/ask
"""
import asyncio
import json
import time
import gzip
import aiohttp
from typing import List, Optional
from urllib.parse import urlsplit

from production_config import PROXY_CONFIG, EXCHANGES_CONFIG

WS_URL = EXCHANGES_CONFIG['bybit']['ws_url']  # e.g. wss://stream.bybit.com/v5/public/spot
DURATION_SEC = 20

class BybitWSSmoke:
    def __init__(self):
        self.message_count = 0
        self.orderbook_updates = 0
        self.ticker_updates = 0
        self.sample_bid = None
        self.sample_ask = None

    def build_attempts(self) -> List[Optional[str]]:
        attempts = []
        if PROXY_CONFIG.get('enabled', False):
            for region, endpoints in PROXY_CONFIG.items():
                if region == 'enabled':
                    continue
                if isinstance(endpoints, dict):
                    # Prefer SOCKS, then HTTP/HTTPS
                    order = ['socks5', 'http', 'https']
                    for key in order:
                        val = endpoints.get(key)
                        if val:
                            attempts.append(val)
        attempts.append(None)  # direct
        return attempts

    async def _subscribe(self, ws: aiohttp.ClientWebSocketResponse):
        sub_msg = {
            "op": "subscribe",
            "args": [
                "orderbook.1.BTCUSDT",
                "tickers.BTCUSDT",
            ]
        }
        await ws.send_json(sub_msg)

    async def _handle_msg(self, msg: aiohttp.WSMessage):
        self.message_count += 1
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            try:
                text = gzip.decompress(msg.data).decode("utf-8")
            except Exception:
                text = msg.data.decode("utf-8", errors="ignore")
            try:
                data = json.loads(text)
            except Exception:
                return
        else:
            return

        if isinstance(data, dict) and data.get('op') == 'ping':
            # Respond to ping
            return {'op': 'pong'}

        if isinstance(data, dict) and 'topic' in data:
            topic = data['topic']
            if topic.startswith('orderbook'):
                payload = data.get('data', {})
                bids = payload.get('b', [])
                asks = payload.get('a', [])
                if bids and asks:
                    try:
                        self.sample_bid = float(bids[0][0])
                        self.sample_ask = float(asks[0][0])
                    except Exception:
                        pass
                self.orderbook_updates += 1
            elif topic.startswith('tickers'):
                self.ticker_updates += 1

        return None

    async def run_once(self, proxy: Optional[str]) -> bool:
        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=30)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; WSBot/1.0)",
            "Origin": "https://bybit.com",
        }
        # Choose connector strategy based on proxy scheme
        connector = None
        use_ws_proxy_param = True
        scheme = ''
        proxy_auth = None
        if proxy:
            try:
                parts = urlsplit(proxy)
                scheme = parts.scheme.lower()
                if parts.username or parts.password:
                    proxy_auth = aiohttp.BasicAuth(parts.username or '', parts.password or '')
            except Exception:
                scheme = ''
                proxy_auth = None
            if scheme.startswith('socks'):
                # Try to use aiohttp_socks if available
                try:
                    from aiohttp_socks import ProxyConnector  # type: ignore
                    connector = ProxyConnector.from_url(proxy)
                    use_ws_proxy_param = False  # connector handles proxying
                except Exception as e:
                    print(f"aiohttp_socks not available for SOCKS proxy: {e}")
            elif scheme == 'https':
                # Disable SSL verification to proxy host to avoid cert errors
                connector = aiohttp.TCPConnector(ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            print(f"Connecting to {WS_URL} via {'proxy ' + proxy if proxy else 'direct'}...")
            try:
                if use_ws_proxy_param and proxy:
                    ws = await session.ws_connect(
                        WS_URL,
                        proxy=proxy,
                        proxy_auth=proxy_auth,
                        autoping=True,
                        heartbeat=10,
                    )
                else:
                    ws = await session.ws_connect(
                        WS_URL,
                        autoping=True,
                        heartbeat=10,
                    )
            except Exception as e:
                print(f"  -> failed: {e}")
                raise

            try:
                await self._subscribe(ws)
                start = time.time()
                while time.time() - start < DURATION_SEC:
                    msg = await ws.receive(timeout=15)
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise ConnectionError(f"ws closed: {msg.type}")
                    resp = await self._handle_msg(msg)
                    if resp is not None:
                        await ws.send_json(resp)
                return True
            finally:
                await ws.close()

    async def run(self):
        attempts = self.build_attempts()
        # Debug: print attempts list
        print("Proxy attempts order:")
        for i, a in enumerate(attempts):
            print(f"  {i+1}. {'direct' if a is None else a}")
        last_err = None
        for proxy in attempts:
            try:
                ok = await self.run_once(proxy)
                if ok:
                    break
            except aiohttp.WSServerHandshakeError as e:
                print(f"Handshake failed (status={getattr(e, 'status', '?')}): {e}")
                last_err = e
                continue
            except Exception as e:
                print(f"Connect failed: {e}")
                last_err = e
                continue
        else:
            raise last_err or ConnectionError("All attempts failed")

        print("\n=== Bybit WS Smoke Test Summary ===")
        print(f"Duration: {DURATION_SEC}s")
        print(f"Messages total: {self.message_count}")
        print(f"Orderbook updates: {self.orderbook_updates}")
        print(f"Ticker updates: {self.ticker_updates}")
        if self.sample_bid and self.sample_ask:
            print(f"Sample best: bid {self.sample_bid}, ask {self.sample_ask}")


if __name__ == "__main__":
    tester = BybitWSSmoke()
    asyncio.run(tester.run())
