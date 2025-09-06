# -*- coding: utf-8 -*-
"""
Заготовка коннектора к живой торговле.

Назначение:
- Прочитать экспортированные сигналы (CSV/JSON) из backtest.py (--export-signals)
- Нормализовать поля и сформировать заявки в единый формат
- В "сухом" режиме (dry-run) просто вывести заявки в консоль и/или сохранить в JSONL
- В перспективе: заменить sink на реальный брокер/шину (HTTP, FIX, ws и т.п.)

Схема ожидаемых входных сигналов (из backtest.py):
- symbol: str (например, "EURUSD")
- strategy: str (например, "A")
- timestamp: ISO-8601 UTC "YYYY-MM-DDTHH:MM:SSZ"
- side: "buy" | "sell"
- price: float
- sl: float
- tp: float
- size: int
- tag: str (произвольная метка стратегии)

Пример запуска:
  .venv/bin/python live_connector.py consume signals_A.csv --out orders.jsonl --dry-run
  .venv/bin/python live_connector.py consume signals_A.json --out orders.jsonl --dry-run

Примечание:
- Реальная отправка в брокера не реализована и помечена TODO (безопасность по умолчанию)
- Для HTTP-интеграции можно добавить зависимость requests и реализовать send_http()
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import click
import pandas as pd


# --------------------------- Модель выходного ордера ---------------------------

@dataclass
class Order:
    symbol: str
    side: str  # "buy" | "sell"
    quantity: int
    order_type: str  # "market" (по умолчанию)
    timestamp: str  # ISO-8601 UTC
    price_hint: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    strategy: Optional[str] = None
    client_tag: Optional[str] = None


def _to_iso_utc(ts: object) -> str:
    try:
        dt = pd.to_datetime(ts, utc=True, errors="coerce")
        if pd.isna(dt):
            raise ValueError("invalid timestamp")
        # Приводим к точности секунд и Z-суффиксу
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        # fallback на текущее время UTC
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_side(side: str) -> str:
    s = str(side).strip().lower()
    if s in {"buy", "long", "b"}:
        return "buy"
    if s in {"sell", "short", "s"}:
        return "sell"
    return s or "buy"


def _load_signals(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext == ".json":
        # Ожидаем список объектов [{...}, ...]
        data = json.loads(path.read_text(encoding="utf-8"))
        df = pd.DataFrame(data)
    else:
        df = pd.read_csv(path)
    return df


def _signals_to_orders(df: pd.DataFrame) -> List[Order]:
    required = [
        "symbol",
        "strategy",
        "timestamp",
        "side",
        "price",
        "sl",
        "tp",
        "size",
    ]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Отсутствует необходимый столбец: {col}")

    orders: List[Order] = []
    for _, r in df.iterrows():
        orders.append(
            Order(
                symbol=str(r["symbol"]),
                side=_normalize_side(r["side"]),
                quantity=int(r["size"]),
                order_type="market",
                timestamp=_to_iso_utc(r["timestamp"]),
                price_hint=float(r["price"]) if pd.notna(r["price"]) else None,
                sl=float(r["sl"]) if pd.notna(r["sl"]) else None,
                tp=float(r["tp"]) if pd.notna(r["tp"]) else None,
                strategy=str(r["strategy"]) if pd.notna(r["strategy"]) else None,
                client_tag=str(r.get("tag")) if "tag" in r and pd.notna(r["tag"]) else None,
            )
        )
    return orders


# -------------------------------- CLI команды --------------------------------

@click.group()
def cli():
    """Коннектор к живой торговле (шаблон).
    
    Подкоманды:
      - consume: прочитать файл сигналов и вывести/сохранить ордера.
    """
    pass


@cli.command("consume")
@click.argument("signals", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Если указан, сохранить ордера в JSONL (по одной записи в строке)")
@click.option("--dry-run/--live", default=True, show_default=True,
              help="В live-режиме заменить sink на реальную интеграцию (TODO)")
def consume_cmd(signals: Path, out: Optional[Path], dry_run: bool):
    """Прочитать экспортированные сигналы (CSV/JSON) и сформировать заявки.

    Пример:
      .venv/bin/python live_connector.py consume signals_A.csv --out orders.jsonl --dry-run
    """
    # Читаем сигналы
    df = _load_signals(signals)
    if df.empty:
        click.echo("[Инфо] Файл сигналов пуст.")
        return

    # Нормализуем и маппим в ордера
    try:
        orders = _signals_to_orders(df)
    except Exception as e:
        raise click.ClickException(f"Ошибка нормализации сигналов: {e}")

    # Вывод в консоль
    click.echo(f"[Инфо] Получено сигналов: {len(orders)}")
    for i, o in enumerate(orders, 1):
        click.echo(f"{i:04d} | {o.timestamp} | {o.symbol} | {o.side} x{o.quantity} | SL={o.sl} TP={o.tp} | tag={o.client_tag}")

    # Сохранение в JSONL (универсальный машинно-читаемый формат для шины)
    if out is not None:
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as f:
                for o in orders:
                    f.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")
            click.echo(f"[Инфо] Ордера сохранены в: {out}")
        except Exception as e:
            raise click.ClickException(f"Не удалось сохранить JSONL: {e}")

    # Заглушка live-режима (для безопасности по умолчанию ничего не делает)
    if not dry_run:
        # TODO: заменить на реальную интеграцию (HTTP/FIX/ws/брокерский SDK)
        # Например, добавить send_http(endpoint) с батчем orders,
        # либо положить JSONL в каталог-"аутбокс", откуда подберёт другая служба.
        click.echo("[Внимание] LIVE-режим пока не реализован. Добавьте реализацию sink по требованиям вашего брокера.")


if __name__ == "__main__":
    cli()
