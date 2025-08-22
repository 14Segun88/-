# -*- coding: utf-8 -*-
"""
Binance WebSocket Smoke Test

Цель:
- Подключиться к Binance WebSocket с запасными хостами (обход геоблокировки)
- Подписаться на тикеры (и опционально на стаканы) для небольшого набора символов
- Считать количество сообщений и ошибок
- Вывести итоговую статистику за заданный интервал

Запуск:
python3 test_binance_ws.py --symbols "BTC/USDT,ETH/USDT,SOL/USDT" --duration 30
python3 test_binance_ws.py --duration 30 --depth  # авто-символы из production_config
"""

import asyncio
import json
import logging
import time
import argparse
from typing import List, Optional

import websockets

try:
    # Используем ту же websocket-конфигурацию, что и в проде
    from production_config import WEBSOCKET_CONFIG, DYNAMIC_PAIRS_CONFIG
except Exception:
    # Резервные значения на случай отсутствия импорта
    WEBSOCKET_CONFIG = {
        'ping_interval': 20,
        'ping_timeout': 10,
        'close_timeout': 10,
        'reconnect_delay': 1,
        'max_reconnect_delay': 60,
        'message_queue_size': 10000,
        'compression': 'deflate',
    }
    DYNAMIC_PAIRS_CONFIG = {
        'priority_pairs': ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT']
    }

logger = logging.getLogger("binance_smoke")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%H:%M:%S',
)

# Те же альтернативные URL, что и в websocket_manager._connect_binance()
ALTERNATIVE_URLS = [
    'wss://stream.binance.com:9443/ws',
    'wss://stream.binance.com:443/ws',
    'wss://stream.binancezh.com:9443/ws',  # Китайский сервер
]


def resolve_symbols(user_symbols: Optional[str], limit: int) -> List[str]:
    """Возвращает список символов в формате 'BTC/USDT'."""
    if user_symbols:
        syms = [s.strip().upper() for s in user_symbols.split(',') if s.strip()]
    else:
        syms = [s for s in DYNAMIC_PAIRS_CONFIG.get('priority_pairs', [])]
        if not syms:
            syms = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'ADA/USDT']
    # Ограничим количество для легкого смок-теста
    return syms[:max(1, limit)]


def build_streams(symbols: List[str], include_depth: bool) -> List[str]:
    """Строит список потоков Binance: <symbol>@ticker (+ опционально depth5)."""
    streams: List[str] = []
    for s in symbols:
        b = s.replace('/', '').lower()
        streams.append(f"{b}@ticker")
        if include_depth:
            streams.append(f"{b}@depth5@100ms")
    return streams


async def run_smoke(symbols: List[str], duration: int, include_depth: bool) -> int:
    """Запускает смок-тест с подключением к первому доступному альтернативному URL."""
    streams = build_streams(symbols, include_depth)

    for attempt_url in ALTERNATIVE_URLS:
        logger.info(f"Попытка подключения к {attempt_url}")
        try:
            async with websockets.connect(
                attempt_url,
                ping_interval=WEBSOCKET_CONFIG.get('ping_interval', 20),
                ping_timeout=WEBSOCKET_CONFIG.get('ping_timeout', 10),
                close_timeout=WEBSOCKET_CONFIG.get('close_timeout', 10),
            ) as ws:
                logger.info("✅ Подключение установлено")

                sub_msg = {"method": "SUBSCRIBE", "params": streams, "id": 1}
                await ws.send(json.dumps(sub_msg))
                logger.info(
                    f"📡 Отправлена подписка: {len(streams)} потоков (символов: {len(symbols)}, depth={'on' if include_depth else 'off'})"
                )

                start = time.time()
                deadline = start + duration

                total_msgs = 0
                ticker_msgs = 0
                depth_msgs = 0
                confirm_msgs = 0
                parse_errors = 0
                other_msgs = 0
                samples: List[str] = []

                while time.time() < deadline:
                    timeout_left = max(0.1, deadline - time.time())
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(2.0, timeout_left))
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"Ошибка получения сообщения: {e}")
                        break

                    try:
                        data = json.loads(raw)
                        total_msgs += 1

                        # Подтверждение подписки
                        if isinstance(data, dict) and data.get('id') == 1 and 'result' in data:
                            confirm_msgs += 1
                            if confirm_msgs <= 1:
                                logger.info("Binance подписка подтверждена")
                            continue

                        # Формат комбинированного потока: {'stream': 'btcusdt@ticker', 'data': {...}}
                        if isinstance(data, dict) and 'stream' in data:
                            stream = data.get('stream', '')
                            if '@ticker' in stream:
                                ticker_msgs += 1
                            elif '@depth' in stream:
                                depth_msgs += 1
                            else:
                                other_msgs += 1
                            if len(samples) < 3:
                                samples.append(raw[:200])
                            continue

                        # Формат одиночного потока/ивента: {'e': '24hrTicker', ...}
                        if isinstance(data, dict) and 'e' in data:
                            ev = str(data.get('e', '')).lower()
                            if 'ticker' in ev:
                                ticker_msgs += 1
                            else:
                                other_msgs += 1
                            if len(samples) < 3:
                                samples.append(raw[:200])
                            continue

                        # Частичный стакан (partial depth), приходит без 'stream' и без 'e'
                        if isinstance(data, dict) and 'bids' in data and 'asks' in data:
                            depth_msgs += 1
                            if len(samples) < 3:
                                samples.append(raw[:200])
                            continue

                        other_msgs += 1
                        if len(samples) < 3:
                            samples.append(raw[:200])

                    except json.JSONDecodeError as e:
                        parse_errors += 1
                        logger.error(f"Ошибка парсинга JSON: {e}")
                    except Exception as e:
                        other_msgs += 1
                        logger.error(f"Ошибка обработки сообщения: {e}")

                elapsed = max(0.001, time.time() - start)
                logger.info("\n===== Итоговая статистика Binance WebSocket =====")
                logger.info(f"URL подключения: {attempt_url}")
                logger.info(f"Длительность: {elapsed:.1f} сек")
                logger.info(f"Всего сообщений: {total_msgs} (~{total_msgs/elapsed:.1f} msg/s)")
                logger.info(f"Тикеры: {ticker_msgs}")
                logger.info(f"Стаканы: {depth_msgs}")
                logger.info(f"Подтверждения подписки: {confirm_msgs}")
                logger.info(f"Ошибки парсинга: {parse_errors}")
                logger.info(f"Прочие сообщения: {other_msgs}")
                if samples:
                    logger.info("Примеры сообщений (первые 3):")
                    for i, s in enumerate(samples, 1):
                        logger.info(f"[{i}] {s}")

                return 0
        except Exception as e:
            logger.warning(f"Не удалось подключиться к {attempt_url}: {e}")
            continue

    logger.error("❌ Все попытки подключения к Binance WebSocket неудачны")
    return 1


async def amain(args: argparse.Namespace) -> int:
    symbols = resolve_symbols(args.symbols, args.limit)
    logger.info(f"Символы для смок-теста ({len(symbols)}): {', '.join(symbols)}")
    return await run_smoke(symbols, args.duration, args.depth)


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance WebSocket Smoke Test")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Список символов через запятую (например: BTC/USDT,ETH/USDT). По умолчанию берутся из production_config.DYNAMIC_PAIRS_CONFIG",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Длительность теста в секундах (по умолчанию 30)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Ограничение количества символов для теста (по умолчанию 10)",
    )
    parser.add_argument(
        "--depth",
        action="store_true",
        help="Подписаться дополнительно на стаканы (depth5@100ms)",
    )
    args = parser.parse_args()

    rc = asyncio.run(amain(args))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
