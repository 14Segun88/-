#!/usr/bin/env python3
"""
Простой тест production бота с минимальным выводом
"""

import asyncio
import aiohttp
import json
from datetime import datetime
from collections import defaultdict
import sys

# Отключаем логи от библиотек
import logging
logging.getLogger('websockets').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)

# Цветной вывод
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def log(msg, color=None):
    """Красивый вывод с временем"""
    time_str = datetime.now().strftime("%H:%M:%S")
    if color:
        print(f"[{time_str}] {color}{msg}{Colors.ENDC}")
    else:
        print(f"[{time_str}] {msg}")

async def test_api_connections():
    """Тест REST API подключений к биржам"""
    log("=" * 60, Colors.HEADER)
    log("🚀 ТЕСТ ПОДКЛЮЧЕНИЙ К БИРЖАМ", Colors.HEADER)
    log("=" * 60, Colors.HEADER)
    
    results = {}
    
    async with aiohttp.ClientSession() as session:
        # MEXC
        try:
            url = "https://api.mexc.com/api/v3/ticker/24hr"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    usdt_pairs = [t['symbol'] for t in data if t['symbol'].endswith('USDT')]
                    results['mexc'] = {'status': 'OK', 'pairs': len(usdt_pairs)}
                    log(f"✅ MEXC: {len(usdt_pairs)} USDT пар", Colors.GREEN)
                else:
                    results['mexc'] = {'status': 'ERROR', 'code': resp.status}
                    log(f"❌ MEXC: HTTP {resp.status}", Colors.RED)
        except Exception as e:
            results['mexc'] = {'status': 'ERROR', 'error': str(e)}
            log(f"❌ MEXC: {e}", Colors.RED)
        
        # Bybit
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            params = {'category': 'spot'}
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tickers = data.get('result', {}).get('list', [])
                    usdt_pairs = [t['symbol'] for t in tickers if t['symbol'].endswith('USDT')]
                    results['bybit'] = {'status': 'OK', 'pairs': len(usdt_pairs)}
                    log(f"✅ Bybit: {len(usdt_pairs)} USDT пар", Colors.GREEN)
                else:
                    results['bybit'] = {'status': 'ERROR', 'code': resp.status}
                    log(f"❌ Bybit: HTTP {resp.status}", Colors.RED)
        except Exception as e:
            results['bybit'] = {'status': 'ERROR', 'error': str(e)}
            log(f"❌ Bybit: {e}", Colors.RED)
        
        # Huobi
        try:
            url = "https://api.huobi.pro/market/tickers"
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tickers = data.get('data', [])
                    usdt_pairs = [t['symbol'] for t in tickers if t['symbol'].endswith('usdt')]
                    results['huobi'] = {'status': 'OK', 'pairs': len(usdt_pairs)}
                    log(f"✅ Huobi: {len(usdt_pairs)} USDT пар", Colors.GREEN)
                else:
                    results['huobi'] = {'status': 'ERROR', 'code': resp.status}
                    log(f"❌ Huobi: HTTP {resp.status}", Colors.RED)
        except Exception as e:
            results['huobi'] = {'status': 'ERROR', 'error': str(e)}
            log(f"❌ Huobi: {e}", Colors.RED)
    
    return results

async def test_arbitrage_scan():
    """Тест поиска арбитражных возможностей"""
    log("\n" + "=" * 60, Colors.HEADER)
    log("🔍 ПОИСК АРБИТРАЖНЫХ ВОЗМОЖНОСТЕЙ", Colors.HEADER)
    log("=" * 60, Colors.HEADER)
    
    async with aiohttp.ClientSession() as session:
        # Получаем цены BTC/USDT с разных бирж
        prices = {}
        
        # MEXC
        try:
            url = "https://api.mexc.com/api/v3/ticker/price"
            params = {'symbol': 'BTCUSDT'}
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    prices['mexc'] = float(data['price'])
        except:
            pass
        
        # Bybit
        try:
            url = "https://api.bybit.com/v5/market/tickers"
            params = {'category': 'spot', 'symbol': 'BTCUSDT'}
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('result') and data['result'].get('list'):
                        prices['bybit'] = float(data['result']['list'][0]['lastPrice'])
        except:
            pass
        
        # Huobi
        try:
            url = "https://api.huobi.pro/market/detail/merged"
            params = {'symbol': 'btcusdt'}
            async with session.get(url, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('tick'):
                        prices['huobi'] = float(data['tick']['close'])
        except:
            pass
        
        # Анализ цен
        if len(prices) >= 2:
            log("\n📊 Цены BTC/USDT:", Colors.BLUE)
            for exchange, price in prices.items():
                log(f"  {exchange.upper()}: ${price:,.2f}")
            
            # Находим арбитраж
            min_exchange = min(prices.items(), key=lambda x: x[1])
            max_exchange = max(prices.items(), key=lambda x: x[1])
            
            spread = (max_exchange[1] - min_exchange[1]) / min_exchange[1] * 100
            
            log(f"\n💰 Арбитражная возможность:", Colors.YELLOW)
            log(f"  Купить на {min_exchange[0].upper()}: ${min_exchange[1]:,.2f}")
            log(f"  Продать на {max_exchange[0].upper()}: ${max_exchange[1]:,.2f}")
            log(f"  Спред: {spread:.3f}%", Colors.GREEN if spread > 0.1 else Colors.YELLOW)
            
            # Расчет прибыли
            fees = 0.2  # 0.1% на покупку + 0.1% на продажу
            net_profit = spread - fees
            
            if net_profit > 0:
                log(f"  Чистая прибыль: {net_profit:.3f}% ✅", Colors.GREEN)
            else:
                log(f"  Чистая прибыль: {net_profit:.3f}% (убыток)", Colors.RED)
        else:
            log("⚠️ Недостаточно данных для анализа", Colors.YELLOW)

async def test_websocket_simple():
    """Простой тест WebSocket подключения"""
    log("\n" + "=" * 60, Colors.HEADER)
    log("🌐 ТЕСТ WEBSOCKET (упрощенный)", Colors.HEADER)
    log("=" * 60, Colors.HEADER)
    
    try:
        import websockets
        import json
        
        # Подключаемся к MEXC WebSocket
        log("Подключение к MEXC WebSocket...", Colors.BLUE)
        
        uri = "wss://wbs.mexc.com/ws"
        received_messages = 0
        
        async with websockets.connect(uri) as ws:
            log("✅ Подключено к MEXC", Colors.GREEN)
            
            # Подписываемся на BTC/USDT тикер
            subscribe_msg = {
                "method": "SUBSCRIPTION", 
                "params": ["spot@public.deals.v3.api@BTCUSDT"]
            }
            await ws.send(json.dumps(subscribe_msg))
            log("📝 Подписка на BTC/USDT отправлена", Colors.BLUE)
            
            # Получаем 5 сообщений
            start_time = datetime.now()
            while received_messages < 5:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    
                    if 'd' in data:  # Данные о цене
                        received_messages += 1
                        bid = data['d'].get('b', 'N/A')
                        ask = data['d'].get('a', 'N/A')
                        log(f"  📈 BTC/USDT - Bid: ${bid}, Ask: ${ask}")
                    
                except asyncio.TimeoutError:
                    log("⏱️ Таймаут ожидания данных", Colors.YELLOW)
                    break
            
            elapsed = (datetime.now() - start_time).total_seconds()
            log(f"\n✅ Получено {received_messages} сообщений за {elapsed:.1f} сек", Colors.GREEN)
            
    except Exception as e:
        log(f"❌ Ошибка WebSocket: {e}", Colors.RED)

async def main():
    """Главная функция тестирования"""
    try:
        # Тест API подключений
        await test_api_connections()
        
        # Тест поиска арбитража
        await test_arbitrage_scan()
        
        # Тест WebSocket
        await test_websocket_simple()
        
        log("\n" + "=" * 60, Colors.HEADER)
        log("✅ ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ", Colors.HEADER)
        log("=" * 60, Colors.HEADER)
        
    except KeyboardInterrupt:
        log("\n⚠️ Остановлено пользователем", Colors.YELLOW)
    except Exception as e:
        log(f"\n❌ Критическая ошибка: {e}", Colors.RED)

if __name__ == "__main__":
    asyncio.run(main())
