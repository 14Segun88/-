# -*- coding: utf-8 -*-
"""
Портфельный агрегатор A + D по роллинговым CSV:
- Ожидает два файла CSV: rolling_A_24m_*.csv и rolling_D_24m_*.csv
- В обоих должны быть столбцы: month, gp, gl (а также pf, trades, winrate, dd — опционально)
- Склеивает по month, суммирует gp, gl, считает PF_port = gp_sum / |gl_sum| по каждому месяцу
- Отчёт: share_pf_gt1, pf_median, pf_min; дополнительно: wr_median, dd_median (если доступны у обеих, не суммируются)

Пример:
  .venv/bin/python portfolio_score.py \
    --a out/rolling_A_24m_rsi18_bb2.0_atr1.2_risk0.5_london7-18_atrmin0.0005_edge0.5.csv \
    --d out/rolling_D_24m_dc60_buf1_atr1.0_risk0.5_trail2_london7-18_adx18_ema200_trend.csv \
    --save out/rolling_AD_24m_summary.csv
"""
from __future__ import annotations

import argparse
import os
import sys
import pandas as pd
import numpy as np


def read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Нормализуем имена
    cols = {c.lower(): c for c in df.columns}
    # Переименуем известные столбцы к стандарту
    rename = {}
    for key in ['month', 'pf', 'trades', 'winrate', 'dd', 'gp', 'gl']:
        for c in df.columns:
            if c.lower() == key:
                rename[c] = key
    if rename:
        df = df.rename(columns=rename)
    # month -> период YYYY-MM
    if 'month' in df.columns:
        df['month'] = df['month'].astype(str)
    # gp/gl по умолчанию 0.0
    if 'gp' not in df.columns:
        df['gp'] = 0.0
    if 'gl' not in df.columns:
        df['gl'] = 0.0
    return df


def portfolio_metrics(df: pd.DataFrame) -> dict:
    """df: содержит pf_A, pf_D (опционально), gp_A, gl_A, gp_D, gl_D, month и pf_port (по gp/gl)."""
    res = {}
    # Портфельный PF по месяцам
    pf_port = df['pf_port'].to_numpy(dtype=float)
    pf_port = pf_port[np.isfinite(pf_port)]
    if pf_port.size > 0:
        res['share_pf_gt1'] = float(np.mean(pf_port > 1.0)) if pf_port.size > 0 else np.nan
        res['pf_median'] = float(np.median(pf_port)) if pf_port.size > 0 else np.nan
        res['pf_min'] = float(np.min(pf_port)) if pf_port.size > 0 else np.nan
    else:
        res['share_pf_gt1'] = np.nan
        res['pf_median'] = np.nan
        res['pf_min'] = np.nan
    # wr_median и dd_median — если есть в обоих, возьмём медиану среднего (как индикативно)
    for col, out in [('winrate', 'wr_median'), ('dd', 'dd_median')]:
        if col in df.columns:
            vals = df[col].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            res[out] = float(np.median(vals)) if vals.size > 0 else np.nan
        else:
            res[out] = np.nan
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True, help='CSV роллинга Strategy A (24м)')
    ap.add_argument('--d', required=True, help='CSV роллинга Strategy D (24м)')
    ap.add_argument('--save', default='out/rolling_AD_24m_summary.csv', help='Куда сохранить сводный CSV (одна строка)')
    args = ap.parse_args()

    df_a = read_csv(args.a)
    df_d = read_csv(args.d)

    # Мерж по месяцам
    merged = pd.merge(df_a, df_d, on='month', how='inner', suffixes=('_A', '_D'))
    if merged.empty:
        print('[Ошибка] Нет пересекающихся месяцев между A и D.')
        sys.exit(2)

    # Портфельные gp/gl по месяцам
    merged['gp_port'] = merged['gp_A'].astype(float) + merged['gp_D'].astype(float)
    merged['gl_port'] = merged['gl_A'].astype(float) + merged['gl_D'].astype(float)
    # PF портфеля по месяцам: gp / |gl| (если gl==0 и gp>0 -> inf; если gp<=0 и gl==0 -> 0)
    def pf_from_gpgln(gp, gl):
        if gl < 0:
            return gp / abs(gl) if abs(gl) > 0 else np.inf
        return np.inf if gp > 0 else 0.0
    merged['pf_port'] = [pf_from_gpgln(gp, gl) for gp, gl in zip(merged['gp_port'], merged['gl_port'])]

    # Индикативные wr/dd портфеля: среднее A/D, если доступны
    if 'winrate_A' in merged.columns and 'winrate_D' in merged.columns:
        merged['winrate'] = (merged['winrate_A'].astype(float) + merged['winrate_D'].astype(float)) / 2.0
    if 'dd_A' in merged.columns and 'dd_D' in merged.columns:
        merged['dd'] = (merged['dd_A'].astype(float) + merged['dd_D'].astype(float)) / 2.0

    met = portfolio_metrics(merged)
    out_row = {
        'a_csv': os.path.basename(args.a),
        'd_csv': os.path.basename(args.d),
        **met
    }
    out_df = pd.DataFrame([out_row])
    os.makedirs(os.path.dirname(args.save), exist_ok=True) if os.path.dirname(args.save) else None
    out_df.to_csv(args.save, index=False)

    print('\n=== Портфель A + D (на основе gp/gl по месяцам) ===')
    print(out_df.to_string(index=False))


if __name__ == '__main__':
    main()
