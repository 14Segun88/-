#!/usr/bin/env python3
"""
🔍 ПРОВЕРКА РЕАЛЬНОСТИ АРБИТРАЖА
Проверяем реальные цены и объемы для APT/USDT
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime

async def check_real_prices():
    """Проверяем реальные цены и объемы"""
    print("🔍 ПРОВЕРКА РЕАЛЬНОСТИ АРБИТРАЖА APT/USDT")
    print("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        # Получаем данные с KuCoin
        print("📊 KuCoin данные:")
        try:
            kucoin_url = "https://api.kucoin.com/api/v1/market/orderbook/level2_20?symbol=APT-USDT"
            async with session.get(kucoin_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == '200000':
                        orderbook = data['data']
                        best_bid = float(orderbook['bids'][0][0])
                        best_ask = float(orderbook['asks'][0][0])
                        bid_volume = float(orderbook['bids'][0][1])
                        ask_volume = float(orderbook['asks'][0][1])
                        
                        print(f"  Лучший бид: ${best_bid:.4f} (объем: {bid_volume:.2f} APT)")
                        print(f"  Лучший аск: ${best_ask:.4f} (объем: {ask_volume:.2f} APT)")
                        print(f"  Спред: {(best_ask - best_bid) / best_bid * 100:.3f}%")
                        
                        kucoin_data = {
                            'bid': best_bid,
                            'ask': best_ask,
                            'bid_volume': bid_volume,
                            'ask_volume': ask_volume
                        }
                else:
                    print(f"  ❌ Ошибка: {resp.status}")
                    return
        except Exception as e:
            print(f"  ❌ Ошибка KuCoin: {e}")
            return
        
        print()
        
        # Получаем данные с Huobi
        print("📊 Huobi данные:")
        try:
            huobi_url = "https://api.huobi.pro/market/depth?symbol=aptusdt&type=step0"
            async with session.get(huobi_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('status') == 'ok':
                        tick = data['tick']
                        best_bid = float(tick['bids'][0][0])
                        best_ask = float(tick['asks'][0][0])
                        bid_volume = float(tick['bids'][0][1])
                        ask_volume = float(tick['asks'][0][1])
                        
                        print(f"  Лучший бид: ${best_bid:.4f} (объем: {bid_volume:.2f} APT)")
                        print(f"  Лучший аск: ${best_ask:.4f} (объем: {ask_volume:.2f} APT)")
                        print(f"  Спред: {(best_ask - best_bid) / best_bid * 100:.3f}%")
                        
                        huobi_data = {
                            'bid': best_bid,
                            'ask': best_ask,
                            'bid_volume': bid_volume,
                            'ask_volume': ask_volume
                        }
                else:
                    print(f"  ❌ Ошибка: {resp.status}")
                    return
        except Exception as e:
            print(f"  ❌ Ошибка Huobi: {e}")
            return
        
        print()
        print("🔍 АНАЛИЗ АРБИТРАЖА:")
        print("=" * 50)
        
        # Проверяем возможность KuCoin -> Huobi
        if kucoin_data['ask'] < huobi_data['bid']:
            spread = (huobi_data['bid'] - kucoin_data['ask']) / kucoin_data['ask'] * 100
            fees = 0.08 + 0.20  # KuCoin + Huobi
            net_profit = spread - fees - 0.03  # минус слиппедж
            
            print(f"✅ Возможность: KuCoin → Huobi")
            print(f"  Купить на KuCoin: ${kucoin_data['ask']:.4f}")
            print(f"  Продать на Huobi: ${huobi_data['bid']:.4f}")
            print(f"  Спред: {spread:.3f}%")
            print(f"  Комиссии: {fees:.2f}%")
            print(f"  Чистая прибыль: {net_profit:.3f}%")
            
            # Проверяем объемы
            min_volume = min(kucoin_data['ask_volume'], huobi_data['bid_volume'])
            max_trade_usd = min_volume * kucoin_data['ask']
            
            print(f"  Доступный объем: {min_volume:.2f} APT (${max_trade_usd:.2f})")
            
            if max_trade_usd < 100:
                print("  ⚠️ Недостаточная ликвидность для $100 сделки")
            else:
                print("  ✅ Достаточная ликвидность")
                
        # Проверяем возможность Huobi -> KuCoin  
        elif huobi_data['ask'] < kucoin_data['bid']:
            spread = (kucoin_data['bid'] - huobi_data['ask']) / huobi_data['ask'] * 100
            fees = 0.20 + 0.08  # Huobi + KuCoin
            net_profit = spread - fees - 0.03  # минус слиппедж
            
            print(f"✅ Возможность: Huobi → KuCoin")
            print(f"  Купить на Huobi: ${huobi_data['ask']:.4f}")
            print(f"  Продать на KuCoin: ${kucoin_data['bid']:.4f}")
            print(f"  Спред: {spread:.3f}%")
            print(f"  Комиссии: {fees:.2f}%")
            print(f"  Чистая прибыль: {net_profit:.3f}%")
            
            # Проверяем объемы
            min_volume = min(huobi_data['ask_volume'], kucoin_data['bid_volume'])
            max_trade_usd = min_volume * huobi_data['ask']
            
            print(f"  Доступный объем: {min_volume:.2f} APT (${max_trade_usd:.2f})")
            
            if max_trade_usd < 100:
                print("  ⚠️ Недостаточная ликвидность для $100 сделки")
            else:
                print("  ✅ Достаточная ликвидность")
        else:
            print("❌ Арбитражной возможности не найдено")
            print(f"  KuCoin аск: ${kucoin_data['ask']:.4f}")
            print(f"  Huobi бид: ${huobi_data['bid']:.4f}")
            print(f"  Huobi аск: ${huobi_data['ask']:.4f}")
            print(f"  KuCoin бид: ${kucoin_data['bid']:.4f}")

if __name__ == "__main__":
    asyncio.run(check_real_prices())
