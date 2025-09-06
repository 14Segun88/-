# -*- coding: utf-8 -*-
"""
Загрузчик минутных данных (M1) Dukascopy c кэшем в Parquet.

Пример:
  /mnt/c/Users/123/Desktop/fx_lab/.venv/bin/python data_fetch.py \
    --symbol EURUSD --start 2020-09-01 --end 2025-09-01 \
    --out data --offer-side bid
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from dateutil import parser as dtparser
from typing import Optional

import click
import pandas as pd

import dukascopy_python
from dukascopy_python import OFFER_SIDE_BID, OFFER_SIDE_ASK
# Импортируем константу инструмента для EURUSD (основная пара для старта)
try:
    from dukascopy_python.instruments import (
        INSTRUMENT_FX_MAJORS_EUR_USD,
        INSTRUMENT_FX_MAJORS_GBP_USD,
        INSTRUMENT_FX_MAJORS_USD_JPY,
        INSTRUMENT_FX_MAJORS_USD_CHF,
    )
except Exception as e:
    print("[Ошибка] Не удалось импортировать список инструментов из dukascopy_python.instruments:\n", e)
    sys.exit(1)

SYMBOL_TO_INSTR = {
    "EURUSD": INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": INSTRUMENT_FX_MAJORS_USD_JPY,
    "USDCHF": INSTRUMENT_FX_MAJORS_USD_CHF,
}

def month_range(start: datetime, end: datetime):
    """Итератор по месяцам [start, end)."""
    cur = datetime(start.year, start.month, 1)
    stop = datetime(end.year, end.month, 1)
    # захватить последний месяц, содержащий end
    if stop < end:
        stop = datetime(end.year, end.month, 1)
    while cur <= end:
        # старт месяца
        m_start = cur
        # следующий месяц
        if cur.month == 12:
            m_next = datetime(cur.year + 1, 1, 1)
        else:
            m_next = datetime(cur.year, cur.month + 1, 1)
        # ограничим концом диапазона
        m_end = min(m_next, end)
        yield m_start, m_end
        cur = m_next

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def save_parquet_partition(df: pd.DataFrame, out_root: str, symbol: str, tf: str, start: datetime):
    year = start.year
    month = start.month
    out_dir = os.path.join(out_root, symbol, tf, f"year={year}", f"month={month:02d}")
    ensure_dir(out_dir)
    out_path = os.path.join(out_dir, f"{symbol}_{tf}_{year}_{month:02d}.parquet")
    # Гарантируем сортировку по времени
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    df.to_parquet(out_path, index=False)
    print(f"[OK] Сохранено: {out_path} (строк: {len(df)})")

@click.command()
@click.option("--symbol", type=str, default="EURUSD", show_default=True, help="Символ Forex, напр. EURUSD")
@click.option("--start", type=str, default=None, help="Дата начала YYYY-MM-DD (по умолчанию: 5 лет назад от сегодня)")
@click.option("--end", type=str, default=None, help="Дата конца YYYY-MM-DD (по умолчанию: сегодня)")
@click.option("--out", "out_root", type=click.Path(file_okay=False), default="data", show_default=True, help="Корень для кэша Parquet")
@click.option("--offer-side", type=click.Choice(["bid", "ask"], case_sensitive=False), default="bid", show_default=True, help="Сторона котировки")
def main(symbol: str, start: Optional[str], end: Optional[str], out_root: str, offer_side: str):
    """Скачать минутные свечи (M1) с Dukascopy за интервал и сохранить в Parquet по месяцам."""
    symbol = symbol.upper().replace("/", "")
    if symbol not in SYMBOL_TO_INSTR:
        print(f"[Ошибка] Пока поддержаны только: {list(SYMBOL_TO_INSTR.keys())}. Запрошено: {symbol}")
        sys.exit(2)

    instr = SYMBOL_TO_INSTR[symbol]
    side = OFFER_SIDE_BID if offer_side.lower() == "bid" else OFFER_SIDE_ASK

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if end:
        end_dt = dtparser.parse(end)
    else:
        end_dt = today
    if start:
        start_dt = dtparser.parse(start)
    else:
        start_dt = end_dt - timedelta(days=365 * 5)

    # Нормализуем границы на начало/конец дня
    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)

    print(f"[Инфо] Загрузка {symbol} M1 c {start_dt.date()} по {end_dt.date()} сторона={offer_side}")

    # Пройдём по месяцам, чтобы не утыкаться в большие запросы
    for m_start, m_end in month_range(start_dt, end_dt):
        # dukascopy-python 4.0.1: M1 — это INTERVAL_MIN_1
        interval = getattr(dukascopy_python, "INTERVAL_MIN_1", None)
        if interval is None:
            print("[Ошибка] В dukascopy_python отсутствует INTERVAL_MIN_1. Обновите пакет или используйте другой интервал.")
            sys.exit(3)
        try:
            df = dukascopy_python.fetch(
                instr,
                interval,
                side,
                m_start,
                m_end,
            )
        except Exception as e:
            print(f"[Предупреждение] Не удалось получить {symbol} за {m_start.date()}–{m_end.date()}: {e}")
            continue

        if df is None or len(df) == 0:
            print(f"[Пусто] {symbol} {m_start.date()}–{m_end.date()} — данных нет")
            continue

        # Убедимся, что есть колонка timestamp
        if "timestamp" not in df.columns:
            # иногда индекс может быть временем — сбросим индекс
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index().rename(columns={"index": "timestamp"})
            else:
                # попытаемся найти time-like колонку
                for c in df.columns:
                    if "time" in c:
                        df = df.rename(columns={c: "timestamp"})
                        break
        # Приведём тип времени
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        # Фильтр нулевых/битых
        df = df.dropna(subset=["timestamp"])  # убрать NaT

        save_parquet_partition(df, out_root, symbol, "M1", m_start)

    print("[Готово] Загрузка завершена.")

if __name__ == "__main__":
    main()
