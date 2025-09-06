# -*- coding: utf-8 -*-
"""
Утилиты для загрузки кэша Parquet и подготовки OHLC для бэктеста.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pandas as pd

# ------------------ FX вспомогательные функции ------------------

def pip_size(symbol: str) -> float:
    s = symbol.upper()
    if s.endswith("JPY"):
        return 0.01
    # для большинства пар
    return 0.0001

def pips_to_price(symbol: str, pips: float) -> float:
    return pip_size(symbol) * float(pips)

# ------------------ Чтение и ресемплинг ------------------

@dataclass
class OHLC:
    df: pd.DataFrame  # колонки: Open, High, Low, Close, Volume (индекс DateTime)
    symbol: str
    timeframe: str

def read_m1_parquet(root: str, symbol: str) -> pd.DataFrame:
    pattern = os.path.join(root, symbol, "M1", "year=*", "month=*", "*.parquet")
    paths = sorted(glob.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"Не найден кэш M1 по шаблону: {pattern}")

    parts = []
    for p in paths:
        try:
            df = pd.read_parquet(p)
            parts.append(df)
        except Exception as e:
            print(f"[warn] пропустил {p}: {e}")
    if not parts:
        raise RuntimeError("Не удалось прочитать ни один из parquet-файлов")

    df = pd.concat(parts, ignore_index=True)

    # стандартизация колонок
    cols_map = {
        'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume',
        'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume',
    }
    df = df.rename(columns=cols_map)
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True, errors='coerce')
        df = df.dropna(subset=['timestamp']).set_index('timestamp')
    elif isinstance(df.index, pd.DatetimeIndex):
        pass
    else:
        raise ValueError("Нет колонки 'timestamp' или DatetimeIndex в данных M1")

    # сортировка
    df = df.sort_index()
    # удалим дубликаты по времени (оставим последнюю запись месяца)
    before_len = len(df)
    if isinstance(df.index, pd.DatetimeIndex):
        df = df[~df.index.duplicated(keep='last')]
    dup_removed = before_len - len(df)

    # Убедимся, что колонок хватает
    need = {'Open', 'High', 'Low', 'Close'}
    if len(df.columns.intersection(need)) < 4:
        raise ValueError("Данные не содержат OHLC колонок после нормализации")

    if 'Volume' not in df.columns:
        df['Volume'] = np.nan

    # соблюдение инвариантов OHLC: Low ≤ Open/Close ≤ High
    try:
        high_new = df[['High', 'Open', 'Close']].max(axis=1)
        low_new = df[['Low', 'Open', 'Close']].min(axis=1)
        fixed_high = int((high_new != df['High']).sum())
        fixed_low = int((low_new != df['Low']).sum())
        if fixed_high or fixed_low:
            df['High'] = high_new
            df['Low'] = low_new
    except Exception as e:
        print(f"[warn] Не удалось применить проверку инвариантов OHLC: {e}")
        fixed_high = fixed_low = 0

    # отчёт о разрывах во времени (больше 1 минуты)
    gaps_count = 0
    largest_gap = pd.Timedelta(0)
    try:
        diffs = df.index.to_series().diff().dropna()
        gaps = diffs[diffs > pd.Timedelta(minutes=1)]
        gaps_count = int(len(gaps))
        if gaps_count:
            largest_gap = gaps.max()
    except Exception as e:
        print(f"[warn] Не удалось вычислить разрывы по времени: {e}")

    # краткий отчёт качества данных
    try:
        dup_info = f"дубликатов удалено: {dup_removed}" if 'dup_removed' in locals() else "дубликаты: н/д"
        fix_info = f"исправлено High: {fixed_high}, Low: {fixed_low}"
        gap_info = f"разрывов: {gaps_count}, макс: {largest_gap}"
        print(f"[Качество] M1 {symbol}: {dup_info}; {fix_info}; {gap_info}")
    except Exception:
        pass

    return df[['Open', 'High', 'Low', 'Close', 'Volume']]

def resample_ohlc(df_m1: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    tf = timeframe.upper()
    if tf == 'M1':
        return df_m1
    if tf == 'M5':
        rule = '5min'
    elif tf == 'M15':
        rule = '15min'
    elif tf == 'M30':
        rule = '30min'
    elif tf == 'H1':
        rule = '1h'
    else:
        raise ValueError(f"Неподдерживаемый таймфрейм: {timeframe}")

    o = df_m1['Open'].resample(rule).first()
    h = df_m1['High'].resample(rule).max()
    l = df_m1['Low'].resample(rule).min()
    c = df_m1['Close'].resample(rule).last()
    v = df_m1['Volume'].resample(rule).sum(min_count=1)
    out = pd.concat({'Open': o, 'High': h, 'Low': l, 'Close': c, 'Volume': v}, axis=1).dropna()
    return out

def _resampled_cache_path(root: str, symbol: str, timeframe: str) -> str:
    """Путь к файлу полного ресемплинга (все доступные M1 -> TF)."""
    tf = timeframe.upper()
    # хранить в data/<SYMBOL>/<TF>/resampled_full.parquet
    dir_path = os.path.join(root, symbol, tf)
    os.makedirs(dir_path, exist_ok=True)
    return os.path.join(dir_path, 'resampled_full.parquet')

def load_ohlc(root: str, symbol: str, timeframe: str = 'M15',
              start: Optional[pd.Timestamp] = None,
              end: Optional[pd.Timestamp] = None,
              use_cache_resampled: bool = False) -> OHLC:
    tf = timeframe.upper()
    # Если просили кеш и таймфрейм не M1 — пробуем читать готовый паракет
    if use_cache_resampled and tf != 'M1':
        cache_path = _resampled_cache_path(root, symbol, tf)
        # Определим, актуален ли кеш относительно M1 файлов
        m1_pattern = os.path.join(root, symbol, 'M1', 'year=*', 'month=*', '*.parquet')
        m1_files = sorted(glob.glob(m1_pattern))
        latest_src_mtime = max([os.path.getmtime(p) for p in m1_files], default=0.0)
        cache_mtime = os.path.getmtime(cache_path) if os.path.exists(cache_path) else 0.0
        if os.path.exists(cache_path) and cache_mtime >= latest_src_mtime:
            try:
                df_cached = pd.read_parquet(cache_path)
                # Убедимся, что индекс типа DatetimeIndex и отсортирован
                if 'timestamp' in df_cached.columns:
                    df_cached['timestamp'] = pd.to_datetime(df_cached['timestamp'], utc=True, errors='coerce')
                    df_cached = df_cached.dropna(subset=['timestamp']).set_index('timestamp')
                if not isinstance(df_cached.index, pd.DatetimeIndex):
                    raise ValueError('Кеш ресемплинга не содержит DatetimeIndex')
                df_cached = df_cached.sort_index()
                ohlc = df_cached[['Open', 'High', 'Low', 'Close', 'Volume']]
                if start is not None:
                    start_ts = pd.to_datetime(start, utc=True)
                    ohlc = ohlc[ohlc.index >= start_ts]
                if end is not None:
                    end_ts = pd.to_datetime(end, utc=True)
                    ohlc = ohlc[ohlc.index <= end_ts]
                return OHLC(df=ohlc, symbol=symbol, timeframe=timeframe)
            except Exception as e:
                print(f"[warn] Не удалось прочитать кеш ресемплинга {cache_path}: {e}. Перестроим…")

    # Построим из M1 и при необходимости сохраним кеш
    m1 = read_m1_parquet(root, symbol)
    ohlc_full = resample_ohlc(m1, tf)
    if use_cache_resampled and tf != 'M1':
        cache_path = _resampled_cache_path(root, symbol, tf)
        try:
            # Сохраним с индексом как timestamp
            to_save = ohlc_full.copy()
            to_save = to_save.reset_index().rename(columns={'index': 'timestamp'})
            to_save.to_parquet(cache_path, index=False)
            # print/лог на русском
            print(f"[Инфо] Кеш ресемплинга обновлён: {cache_path}")
        except Exception as e:
            print(f"[warn] Не удалось сохранить кеш ресемплинга {cache_path}: {e}")

    # Фильтрация по датам
    ohlc = ohlc_full
    if start is not None:
        start_ts = pd.to_datetime(start, utc=True)
        ohlc = ohlc[ohlc.index >= start_ts]
    if end is not None:
        end_ts = pd.to_datetime(end, utc=True)
        ohlc = ohlc[ohlc.index <= end_ts]
    return OHLC(df=ohlc, symbol=symbol, timeframe=timeframe)

def percent_from_pips(symbol: str, pips: float, ref_price: float) -> float:
    """Перевод пипсов в долю цены (процент в валюте backtesting.py).
    Возвращает долю (0.0001 = 0.01%).
    """
    abs_price = pips_to_price(symbol, pips)
    return float(abs_price) / float(ref_price)
