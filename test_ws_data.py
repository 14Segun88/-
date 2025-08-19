#!/usr/bin/env python3
"""
Тестирование WebSocket данных и стаканов
"""

import asyncio
import json
import websockets
import time
from datetime import datetime

class TestWebSocketData:
    def __init__(self):
        self.data_received = {
            'mexc': {'tickers': 0, 'orderbooks': 0, 'last_price': 0},
            'bybit': {'tickers': 0, 'orderbooks': 0, 'last_price': 0},
            'huobi': {'tickers': 0, 'orderbooks': 0, 'last_price': 0},
        }
    
    async def test_mexc(self):
        """Тест MEXC WebSocket"""
        try:
            url = 'wss://wbs.mexc.com/ws'
            async with websockets.connect(url) as ws:
                print("✅ MEXC подключен")
                
                # Подписка на ticker BTC/USDT
                sub = {
                    "method": "SUBSCRIPTION",
                    "params": ["spot@public.miniTickers.v3.api@BTCUSDT"]
                }
                await ws.send(json.dumps(sub))
                
                # Читаем сообщения 10 секунд
                start = time.time()
                while time.time() - start < 10:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)
                        
                        if 'd' in data:
                            self.data_received['mexc']['tickers'] += 1
                            if 'p' in data['d']:
                                self.data_received['mexc']['last_price'] = float(data['d']['p'])
                                
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"MEXC ошибка: {e}")
                        
        except Exception as e:
            print(f"❌ MEXC не подключился: {e}")
    
    async def test_bybit(self):
        """Тест Bybit WebSocket"""
        try:
            url = 'wss://stream.bybit.com/v5/public/spot'
            async with websockets.connect(url) as ws:
                print("✅ Bybit подключен")
                
                # Подписка на ticker
                sub = {
                    "op": "subscribe",
                    "args": ["tickers.BTCUSDT"]
                }
                await ws.send(json.dumps(sub))
                
                # Читаем сообщения 10 секунд
                start = time.time()
                while time.time() - start < 10:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        data = json.loads(msg)
                        
                        if 'data' in data:
                            self.data_received['bybit']['tickers'] += 1
                            if 'lastPrice' in data['data']:
                                self.data_received['bybit']['last_price'] = float(data['data']['lastPrice'])
                                
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"Bybit ошибка: {e}")
                        
        except Exception as e:
            print(f"❌ Bybit не подключился: {e}")
    
    async def test_huobi(self):
        """Тест Huobi WebSocket"""
        try:
            url = 'wss://api.huobi.pro/ws'
            async with websockets.connect(url) as ws:
                print("✅ Huobi подключен")
                
                # Подписка на ticker
                sub = {
                    "sub": "market.btcusdt.ticker",
                    "id": "id1"
                }
                await ws.send(json.dumps(sub))
                
                # Читаем сообщения 10 секунд
                start = time.time()
                while time.time() - start < 10:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1)
                        # Huobi использует gzip
                        import gzip
                        data = json.loads(gzip.decompress(msg))
                        
                        if 'tick' in data:
                            self.data_received['huobi']['tickers'] += 1
                            if 'close' in data['tick']:
                                self.data_received['huobi']['last_price'] = float(data['tick']['close'])
                        
                        # Отвечаем на ping
                        if 'ping' in data:
                            await ws.send(json.dumps({'pong': data['ping']}))
                            
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        print(f"Huobi ошибка обработки: {e}")
                        
        except Exception as e:
            print(f"❌ Huobi не подключился: {e}")
    
    async def run_tests(self):
        """Запуск всех тестов"""
        print("\n" + "="*60)
        print("🔍 ТЕСТИРОВАНИЕ WEBSOCKET ДАННЫХ")
        print("="*60)
        print(f"Время: {datetime.now().strftime('%H:%M:%S')}")
        print("-"*60)
        
        # Запускаем тесты параллельно
        tasks = [
            self.test_mexc(),
            self.test_bybit(),
            self.test_huobi()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Выводим результаты
        print("\n" + "="*60)
        print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("="*60)
        
        for exchange, data in self.data_received.items():
            status = "✅" if data['tickers'] > 0 else "❌"
            print(f"\n{exchange.upper()}:")
            print(f"  {status} Ticker сообщений: {data['tickers']}")
            print(f"  💰 Последняя цена BTC: ${data['last_price']:.2f}")
            
            if data['tickers'] == 0:
                print(f"  ⚠️  WebSocket НЕ ПОЛУЧАЕТ данные!")
        
        # Проверка арбитража
        prices = [d['last_price'] for d in self.data_received.values() if d['last_price'] > 0]
        if len(prices) >= 2:
            spread = (max(prices) - min(prices)) / min(prices) * 100
            print(f"\n📈 МЕЖБИРЖЕВОЙ СПРЕД:")
            print(f"  Минимальная цена: ${min(prices):.2f}")
            print(f"  Максимальная цена: ${max(prices):.2f}")
            print(f"  Спред: {spread:.3f}%")
            
            if spread > 0.2:
                print(f"  💎 ПОТЕНЦИАЛЬНАЯ АРБИТРАЖНАЯ ВОЗМОЖНОСТЬ!")
            else:
                print(f"  ⚠️  Спред слишком мал для прибыльного арбитража")

if __name__ == "__main__":
    tester = TestWebSocketData()
    asyncio.run(tester.run_tests())
