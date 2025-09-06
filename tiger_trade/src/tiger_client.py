"""
Tiger Trade data client utilities.
- Загрузка дневного OI по 6E (CME Euro FX) через Nasdaq Data Link (Quandl)
- В дальнейшем: загрузка минуток EURUSD/6E и ордер-флоу из CSV/API Tiger.Trade

Запуск из CLI (пример):
    python -m tiger_trade.src.tiger_client oi-download --start 2021-01-01 --end 2025-09-01

Требования:
- .env с NDAQ_API_KEY=... (или QUANDL_API_KEY)
- См. tiger_trade/src/config.py для путей и загрузки .env
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import requests
import nasdaqdatalink as ndl

from .config import Config, ensure_dirs


def _resolve_oi_column(df: pd.DataFrame) -> str:
    """Ищем колонку с OI в разных вариантах имен.
    Возвращаем точное имя колонки. Бросаем ошибку, если не нашли.
    """
    candidates = [
        "Open Interest",
        "OpenInterest",
        "Open_Interest",
        "Open Interest (Contracts)",
        "OpenInterest (Contracts)",
    ]
    lower = {c.lower(): c for c in df.columns}
    for name in candidates:
        if name in df.columns:
            return name
        if name.lower() in lower:
            return lower[name.lower()]
    # иногда встречаются столбцы без пробела/с подчёркиванием
    for col in df.columns:
        if col.replace(" ", "").replace("_", "").lower() in {"openinterest", "openinterestcontracts"}:
            return col
    raise KeyError(f"Не удалось найти столбец с OI в набранных колонках: {list(df.columns)[:10]}...")


def download_6e_daily_oi(start_date: str, end_date: Optional[str] = None, dataset: str = "CHRIS/CME_EC1") -> pd.DataFrame:
    """Скачать дневной OI 6E через Nasdaq Data Link (Quandl) как DataFrame.

    Параметры:
        start_date: YYYY-MM-DD
        end_date: YYYY-MM-DD или None (по сегодня)
        dataset: по умолчанию CHRIS/CME_EC1 (front-month continuous)

    Возвращает:
        DataFrame с колонками [date, oi]
    """
    cfg = Config.from_env()
    ensure_dirs(cfg)
    if not cfg.ndq_api_key:
        raise RuntimeError("Отсутствует NDAQ_API_KEY/QUANDL_API_KEY в .env — укажите API-ключ Nasdaq Data Link.")

    # 1) Основной путь: официальный клиент nasdaqdatalink (часто устойчив к Incapsula)
    print(f"[OI] Загружаю {dataset} за период {start_date}..{end_date or 'today'} через nasdaqdatalink")
    try:
        ndl.ApiConfig.api_key = cfg.ndq_api_key
        df = ndl.get(dataset, start_date=start_date, end_date=end_date)
        # nasdaqdatalink возвращает индекс Date, приведём к колонке
        df = df.reset_index().rename(columns={df.index.name or "index": "Date"}) if df.index.name else df
    except Exception as e:
        print(f"[OI] nasdaqdatalink не сработал: {e}. Пытаюсь через requests CSV…")
        # 2) Fallback: прямой CSV запрос
        params = {"start_date": start_date}
        if end_date:
            params["end_date"] = end_date
        params["api_key"] = cfg.ndq_api_key
        url = f"https://data.nasdaq.com/api/v3/datasets/{dataset}.csv"
        # Не печатаем ключ. Только датасет и даты.
        print(f"[OI] Fallback CSV: {dataset} {start_date}..{end_date or 'today'}")
        r = requests.get(url, params=params, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"Ошибка загрузки OI: HTTP {r.status_code} — {r.text[:300]}")
        df = pd.read_csv(io.StringIO(r.text))
    # Ожидаемые колонки: Date, Open, High, Low, Last, Change, Settle, Volume, Open Interest, ...
    if "Date" not in df.columns:
        # Бывают варианты с маленькими буквами
        date_col = next((c for c in df.columns if c.lower() == "date"), None)
        if not date_col:
            raise KeyError(f"Не найдена колонка даты в ответе: {df.columns.tolist()}")
        df.rename(columns={date_col: "Date"}, inplace=True)

    oi_col = _resolve_oi_column(df)
    out = (
        df[["Date", oi_col]]
        .rename(columns={"Date": "date", oi_col: "oi"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    # Приведём типы
    out["date"] = pd.to_datetime(out["date"], utc=True).dt.date
    out["oi"] = pd.to_numeric(out["oi"], errors="coerce")
    out = out.dropna(subset=["oi"])  # NaN OI исключаем
    print(f"[OI] Загружено строк: {len(out)}; диапазон: {out['date'].min()}..{out['date'].max()}")
    return out


def save_6e_daily_oi_csv(df: pd.DataFrame, cfg: Optional[Config] = None, filename: Optional[str] = None) -> Path:
    """Сохранить OI 6E дневной в CSV под tiger_trade/data/.../6E_daily/.
    Возвращает путь к файлу.
    """
    cfg = cfg or Config.from_env()
    ensure_dirs(cfg)
    target_dir = cfg.data_root / "6E_daily"
    target_dir.mkdir(parents=True, exist_ok=True)
    if filename is None:
        d1, d2 = df["date"].min(), df["date"].max()
        filename = f"6E_oi_{d1}_{d2}.csv"
    path = target_dir / filename
    df.to_csv(path, index=False)
    print(f"[OI] Сохранено: {path}")
    return path


def cli() -> None:
    p = argparse.ArgumentParser(description="Tiger Trade data helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_oi = sub.add_parser("oi-download", help="Скачать дневной OI 6E через Nasdaq Data Link")
    p_oi.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_oi.add_argument("--end", default=None, help="YYYY-MM-DD (опционально)")
    p_oi.add_argument("--dataset", default="CHRIS/CME_EC1", help="Datasets (по умолчанию CHRIS/CME_EC1)")

    args = p.parse_args()

    if args.cmd == "oi-download":
        df = download_6e_daily_oi(args.start, args.end, dataset=args.dataset)
        save_6e_daily_oi_csv(df)
    else:
        p.error("Неизвестная команда")


if __name__ == "__main__":
    cli()
