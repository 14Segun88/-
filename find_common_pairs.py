#!/usr/bin/env python3
"""
Поиск общих торговых пар между OKX и Bitget
"""

import asyncio
import aiohttp
import json
from typing import Set, List

async def get_okx_pairs() -> Set[str]:
    """Получить список пар OKX"""
    try:
        url = "https://www.okx.com/api/v5/market/tickers?instType=SPOT"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = set()
                    for ticker in data.get('data', []):
                        inst_id = ticker.get('instId', '')  # e.g., BTC-USDT
                        if 'USDT' in inst_id:
                            symbol = inst_id.replace('-', '/')
                            pairs.add(symbol)
                    return pairs
    except Exception as e:
        print(f"Ошибка получения пар OKX: {e}")
    return set()

async def get_bitget_pairs() -> Set[str]:
    """Получить список пар Bitget"""
    try:
        url = "https://api.bitget.com/api/spot/v1/market/tickers"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = set()
                    for ticker in data.get('data', []):
                        symbol = ticker.get('symbol', '')  # e.g., BTCUSDT
                        if symbol.endswith('USDT') and len(symbol) > 4:
                            base = symbol[:-4]
                            formatted = f"{base}/USDT"
                            pairs.add(formatted)
                    return pairs
    except Exception as e:
        print(f"Ошибка получения пар Bitget: {e}")
    return set()

async def main():
    print("🔍 Поиск общих торговых пар между OKX и Bitget...")
    
    # Получаем пары с обеих бирж
    okx_pairs, bitget_pairs = await asyncio.gather(
        get_okx_pairs(),
        get_bitget_pairs()
    )
    
    print(f"📊 OKX: найдено {len(okx_pairs)} USDT пар")
    print(f"📊 Bitget: найдено {len(bitget_pairs)} USDT пар")
    
    # Находим общие пары
    common_pairs = okx_pairs & bitget_pairs
    print(f"🎯 Общих пар: {len(common_pairs)}")
    
    # Сортируем и выводим
    sorted_pairs = sorted(list(common_pairs))
    
    print("\n📋 Список общих пар:")
    for i, pair in enumerate(sorted_pairs, 1):
        print(f"{i:3d}. {pair}")
    
    # Сохраняем в файл
    with open('common_pairs_okx_bitget.json', 'w') as f:
        json.dump({
            'okx_pairs_count': len(okx_pairs),
            'bitget_pairs_count': len(bitget_pairs),
            'common_pairs_count': len(common_pairs),
            'common_pairs': sorted_pairs,
            'okx_only': sorted(list(okx_pairs - bitget_pairs)),
            'bitget_only': sorted(list(bitget_pairs - okx_pairs))
        }, f, indent=2)
    
    print(f"\n💾 Результаты сохранены в common_pairs_okx_bitget.json")
    
    # Показываем топ-20 общих пар
    print("\n🏆 Топ-20 общих пар:")
    for pair in sorted_pairs[:20]:
        print(f"  • {pair}")

if __name__ == "__main__":
    asyncio.run(main())
