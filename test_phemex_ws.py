#!/usr/bin/env python3
"""
Phemex WebSocket smoke test with proxy/VPN support (aiohttp)
- Rotates through PROXY_CONFIG endpoints then tries direct connection
- Subscribes to orderbook L20 for BTCUSDT and market24h
- Runs for ~20 seconds and prints message counts and sample best bid/ask
"""
import asyncio
import json
import time
import gzip
import aiohttp
from typing import List, Optional
from urllib.parse import urlsplit

import production_config as config

# Try multiple official endpoints in case of regional blocks or DNS issues
WS_URLS = [
    "wss://ws.phemex.com/ws",
    "wss://phemex.com/ws",
    "wss://vapi.phemex.com/ws",
    "wss://testnet.phemex.com/ws",
]
DURATION_SEC = 20

class PhemexWSSmoke:
    def __init__(self):
        self.message_count = 0
        self.orderbook_updates = 0
        self.market24h_updates = 0
        self.sample_bid = None
        self.sample_ask = None

    def build_attempts(self) -> List[Optional[str]]:
        attempts = []
        use_proxy = config.EXCHANGES_CONFIG.get('phemex', {}).get('use_proxy', False)
        proxy_enabled = config.PROXY_CONFIG.get('enabled', False)
        if proxy_enabled and use_proxy:
            for region, endpoints in config.PROXY_CONFIG.items():
                if region == 'enabled':
                    continue
                if isinstance(endpoints, dict):
                    # Try SOCKS proxies first if present, then HTTP/HTTPS
                    order = ['socks5', 'socks5h', 'socks4', 'socks4a', 'http', 'https']
                    for key in order:
                        val = endpoints.get(key)
                        if val:
                            attempts.append(val)
        else:
            if not use_proxy:
                print("Phemex: use_proxy=False — using direct connection only")
            elif not proxy_enabled:
                print("Phemex: PROXY_CONFIG.enabled=False — using direct connection only")
        attempts.append(None)  # direct
        return attempts

    async def _subscribe(self, ws: aiohttp.ClientWebSocketResponse):
        # orderbook L20
        sub_msg = {
            "id": int(time.time() * 1000),
            "method": "orderbook.subscribe",
            "params": ["BTCUSDT.L20"],
        }
        await ws.send_json(sub_msg)
        await asyncio.sleep(0.05)
        # market24h (global)
        ticker_msg = {
            "id": int(time.time() * 1000) + 1,
            "method": "market24h.subscribe",
            "params": [],
        }
        await ws.send_json(ticker_msg)

    async def _handle_msg(self, msg: aiohttp.WSMessage):
        self.message_count += 1
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            try:
                data = json.loads(gzip.decompress(msg.data).decode("utf-8"))
            except Exception:
                try:
                    data = json.loads(msg.data.decode("utf-8", errors="ignore"))
                except Exception:
                    return
        else:
            return

        if isinstance(data, dict) and 'book' in data:
            book = data.get('book', {})
            bids = book.get('bids', [])
            asks = book.get('asks', [])
            if bids and asks:
                try:
                    self.sample_bid = float(bids[0][0])
                    self.sample_ask = float(asks[0][0])
                except Exception:
                    pass
            self.orderbook_updates += 1
        elif isinstance(data, dict) and 'market24h' in data:
            self.market24h_updates += 1

    async def run_once(self, proxy: Optional[str]) -> bool:
        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=30)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; WSBot/1.0)",
            "Origin": "https://phemex.com",
        }
        # Choose connector strategy based on proxy scheme
        connector = None
        use_ws_proxy_param = True
        scheme = ''
        if proxy:
            try:
                scheme = urlsplit(proxy).scheme.lower()
            except Exception:
                scheme = ''
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
        # Build proxy auth if credentials are embedded in the proxy URL
        proxy_auth = None
        if proxy:
            try:
                parts = urlsplit(proxy)
                if parts.username or parts.password:
                    proxy_auth = aiohttp.BasicAuth(parts.username or '', parts.password or '')
            except Exception:
                proxy_auth = None
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            last_exc: Optional[Exception] = None
            for url in WS_URLS:
                print(f"Connecting to {url} via {'proxy ' + proxy if proxy else 'direct'}...")
                try:
                    if use_ws_proxy_param and proxy:
                        ws = await session.ws_connect(
                            url,
                            proxy=proxy,
                            proxy_auth=proxy_auth,
                            autoping=True,
                            heartbeat=10,
                        )
                    else:
                        ws = await session.ws_connect(
                            url,
                            autoping=True,
                            heartbeat=10,
                        )
                except Exception as e:
                    print(f"  -> failed: {e}")
                    last_exc = e
                    continue
                try:
                    await self._subscribe(ws)
                    start = time.time()
                    while time.time() - start < DURATION_SEC:
                        msg = await ws.receive(timeout=15)
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise ConnectionError(f"ws closed: {msg.type}")
                        await self._handle_msg(msg)
                    return True
                finally:
                    await ws.close()
            # If none of the URLs worked for this proxy
            if last_exc:
                raise last_exc
            return False

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

        print("\n=== Phemex WS Smoke Test Summary ===")
        print(f"Duration: {DURATION_SEC}s")
        print(f"Messages total: {self.message_count}")
        print(f"Orderbook updates: {self.orderbook_updates}")
        print(f"market24h updates: {self.market24h_updates}")
        if self.sample_bid and self.sample_ask:
            print(f"Sample best: bid {self.sample_bid}, ask {self.sample_ask}")


if __name__ == "__main__":
    tester = PhemexWSSmoke()
    asyncio.run(tester.run())
