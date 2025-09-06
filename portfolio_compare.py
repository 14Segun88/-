# -*- coding: utf-8 -*-
"""
Сравнение портфеля A + D по всем комбинациям заданных файлов A и шаблона D.

Примеры:
  # Базовый режим (как раньше)
  .venv/bin/python portfolio_compare.py \
    --a out/rolling_A_24m_G3_KILL_rsi18_bb2.0_atr1.2_risk0.5_london7-18_atrmin0.0005_edge0.5.csv \
    --a out/rolling_A_24m_G3_KILL_rsi18_bb2.0_atr1.2_risk0.5_london8-17_atrmin0.0005_edge0.5.csv \
    --d-glob "out/rolling_D_24m_portD_*.csv" \
    --out out/rolling_AD_24m_compare.csv

  # Режим с весами и гейтингом D (фильтруем D по порогам качества)
  .venv/bin/python portfolio_compare.py \
    --a out/rolling_A_24m_portA_micro10_s8-17_rr2.0_...csv \
    --d-glob "out/rolling_D_24m_portD_*.csv" \
    --a-weight 1.0 --d-weight 0.2 \
    --d-min-pf 0.12 --d-min-share 0.2 --d-min-months 18 \
    --out out/rolling_AD_24m_compare_weighted.csv
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import List

import numpy as np
import pandas as pd


def read_roll_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Привести имена столбцов к стандарту
    rename = {}
    for c in list(df.columns):
        lc = c.lower()
        if lc in {"month", "pf", "trades", "winrate", "dd", "gp", "gl"}:
            rename[c] = lc
    if rename:
        df = df.rename(columns=rename)
    if "month" in df.columns:
        df["month"] = df["month"].astype(str)
    for k in ("gp", "gl"):
        if k not in df.columns:
            df[k] = 0.0
    return df


def pf_series_from_df(df: pd.DataFrame) -> pd.Series:
    """Получить ряд PF по месяцам из роллингового CSV.
    Если столбца pf нет, вычислить на основе gp/gl.
    """
    if "pf" in df.columns:
        s = pd.to_numeric(df["pf"], errors="coerce")
        return s
    # Восстановим PF из gp/gl
    gp = pd.to_numeric(df.get("gp", pd.Series(index=df.index, dtype=float)), errors="coerce")
    gl = pd.to_numeric(df.get("gl", pd.Series(index=df.index, dtype=float)), errors="coerce")

    def pf_from(gp_val, gl_val):
        if pd.isna(gp_val) or pd.isna(gl_val):
            return np.nan
        if gl_val < 0:
            return gp_val / abs(gl_val) if abs(gl_val) > 0 else np.inf
        return np.inf if gp_val > 0 else 0.0

    return pd.Series([pf_from(g, l) for g, l in zip(gp, gl)], index=df.index, dtype=float)


def roll_metrics_for_file(path: str) -> dict:
    """Подсчёт ключевых метрик (months, pf_min, pf_median, share_pf_gt1) для файла роллинга."""
    df = read_roll_csv(path)
    pf = pf_series_from_df(df)
    pf = pf.to_numpy(dtype=float)
    pf = pf[np.isfinite(pf)]
    if pf.size == 0:
        return {"months": 0, "pf_min": np.nan, "pf_median": np.nan, "share_pf_gt1": np.nan}
    return {
        "months": int(pf.size),
        "pf_min": float(np.min(pf)),
        "pf_median": float(np.median(pf)),
        "share_pf_gt1": float(np.mean(pf > 1.0)),
    }


def pf_metrics_from_gpgl(df_port: pd.DataFrame) -> dict:
    pf_port = df_port["pf_port"].to_numpy(dtype=float)
    pf_port = pf_port[np.isfinite(pf_port)]
    if pf_port.size == 0:
        return {"share_pf_gt1": np.nan, "pf_median": np.nan, "pf_min": np.nan}
    return {
        "share_pf_gt1": float(np.mean(pf_port > 1.0)),
        "pf_median": float(np.median(pf_port)),
        "pf_min": float(np.min(pf_port)),
    }


def combine_portfolio(a_path: str, d_path: str, w_a: float = 1.0, w_d: float = 1.0) -> dict:
    a = read_roll_csv(a_path)
    d = read_roll_csv(d_path)
    m = pd.merge(a, d, on="month", how="inner", suffixes=("_A", "_D"))
    if m.empty:
        return {
            "a_csv": os.path.basename(a_path),
            "d_csv": os.path.basename(d_path),
            "share_pf_gt1": np.nan,
            "pf_median": np.nan,
            "pf_min": np.nan,
            "wr_median": np.nan,
            "dd_median": np.nan,
            "a_weight": w_a,
            "d_weight": w_d,
        }
    # Весим GP/GL по заданным весам
    m["gp_port"] = w_a * m["gp_A"].astype(float) + w_d * m["gp_D"].astype(float)
    m["gl_port"] = w_a * m["gl_A"].astype(float) + w_d * m["gl_D"].astype(float)

    def pf_from(gp, gl):
        if gl < 0:
            return gp / abs(gl) if abs(gl) > 0 else np.inf
        return np.inf if gp > 0 else 0.0

    m["pf_port"] = [pf_from(gp, gl) for gp, gl in zip(m["gp_port"], m["gl_port"])]

    # Весим вспомогательные метрики (если есть)
    denom = (w_a + w_d) if (w_a + w_d) != 0 else 1.0
    if "winrate_A" in m.columns and "winrate_D" in m.columns:
        m["winrate"] = (w_a * m["winrate_A"].astype(float) + w_d * m["winrate_D"].astype(float)) / denom
    if "dd_A" in m.columns and "dd_D" in m.columns:
        m["dd"] = (w_a * m["dd_A"].astype(float) + w_d * m["dd_D"].astype(float)) / denom

    met = pf_metrics_from_gpgl(m)
    wr_median = float(np.median(m["winrate"])) if "winrate" in m.columns else np.nan
    dd_median = float(np.median(m["dd"])) if "dd" in m.columns else np.nan
    return {
        "a_csv": os.path.basename(a_path),
        "d_csv": os.path.basename(d_path),
        **met,
        "wr_median": wr_median,
        "dd_median": dd_median,
        "a_weight": w_a,
        "d_weight": w_d,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", dest="a_files", action="append", required=True, help="Файлы роллинга A (можно несколько флагов --a)")
    ap.add_argument("--d-glob", required=True, help="Глоб-шаблон файлов роллинга D")
    ap.add_argument("--a-weight", type=float, default=1.0, help="Вес стратегии A в портфеле (по умолчанию 1.0)")
    ap.add_argument("--d-weight", type=float, default=1.0, help="Вес стратегии D в портфеле (по умолчанию 1.0)")
    # Гейтинг D: допускаем в портфель только D, прошедшие пороги качества
    ap.add_argument("--d-min-pf", type=float, default=None, help="Минимальный pf_min для допуска D (опционально)")
    ap.add_argument("--d-min-share", type=float, default=None, help="Минимальная доля месяцев с PF>1 для допуска D (опционально)")
    ap.add_argument("--d-min-months", type=int, default=None, help="Минимум валидных месяцев для допуска D (опционально)")
    ap.add_argument("--out", default="out/rolling_AD_24m_compare.csv")
    args = ap.parse_args()

    d_files: List[str] = sorted(glob.glob(args.d_glob))
    if not d_files:
        print(f"[Ошибка] Не найдено файлов по шаблону: {args.d_glob}")
        sys.exit(2)

    # Применим гейтинг к D, если заданы пороги
    use_gate = any(v is not None for v in (args.d_min_pf, args.d_min_share, args.d_min_months))
    if use_gate:
        kept = []
        dropped = []
        for d_path in d_files:
            met = roll_metrics_for_file(d_path)
            ok = True
            if args.d_min_months is not None and (met["months"] < int(args.d_min_months)):
                ok = False
            if args.d_min_pf is not None and (not np.isfinite(met["pf_min"]) or met["pf_min"] < float(args.d_min_pf)):
                ok = False
            if args.d_min_share is not None and (not np.isfinite(met["share_pf_gt1"]) or met["share_pf_gt1"] < float(args.d_min_share)):
                ok = False
            (kept if ok else dropped).append((d_path, met))
        d_files = [p for p, _ in kept]
        print(f"[Гейтинг D] прошло: {len(kept)}; отклонено: {len(dropped)} из {len(kept)+len(dropped)}")
        if not d_files:
            print("[Ошибка] Все кандидаты D отклонены гейтингом — ослабьте пороги")
            sys.exit(2)

    rows = []
    for a_path in args.a_files:
        if not os.path.exists(a_path):
            print(f"[warn] Пропуск: нет файла {a_path}")
            continue
        for d_path in d_files:
            rows.append(combine_portfolio(a_path, d_path, w_a=args.a_weight, w_d=args.d_weight))

    if not rows:
        print("[Ошибка] Нет комбинаций для сравнения")
        sys.exit(2)

    out_df = pd.DataFrame(rows)
    out_path = args.out
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_df.to_csv(out_path, index=False)

    # Печать топов
    try:
        top = out_df.sort_values(["pf_median", "pf_min"], ascending=[False, False]).head(10)
        print("\nTOP-10 A+D по pf_median и pf_min:")
        print(top.to_string(index=False))
    except Exception:
        pass


if __name__ == "__main__":
    main()
