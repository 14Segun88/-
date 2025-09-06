# -*- coding: utf-8 -*-
"""
Агрегатор Stability Score по файлам роллинга Strategy A.
Собирает все CSV вида rolling_A_24m*.csv, считает:
- months: число месяцев
- share_pf_gt1: доля месяцев с PF > 1
- pf_median: медиана PF
- pf_min: минимум PF
- wr_median: медиана WinRate [%]
- dd_median: медиана Max. Drawdown [%]
И сохраняет сводный рейтинг в out/rolling_A_24m_summary.csv

Пример запуска:
  .venv/bin/python stability_score.py --search-root . --pattern "rolling_A_24m*.csv" \
      --out "out/rolling_A_24m_summary.csv"
"""
from __future__ import annotations

import os
import glob
from typing import List, Dict

import click
import pandas as pd


def _extract_tag_from_filename(path: str) -> str:
    base = os.path.basename(path)
    name, _ = os.path.splitext(base)
    if name.startswith('rolling_A_24m_'):
        return name[len('rolling_A_24m_'):]
    elif name == 'rolling_A_24m':
        return 'current'
    return name


@click.command()
@click.option('--search-root', type=click.Path(file_okay=False), default='.', show_default=True,
              help='Корень поиска файлов роллинга')
@click.option('--pattern', type=str, default='rolling_A_24m*.csv', show_default=True,
              help='Глоб-шаблон для поиска файлов роллинга')
@click.option('--out', 'out_path', type=str, default='out/rolling_A_24m_summary.csv', show_default=True,
              help='Путь для сохранения сводной таблицы')
@click.option('--verbose', is_flag=True, default=False, help='Подробный лог в консоль')
def main(search_root: str, pattern: str, out_path: str, verbose: bool):
    files = sorted(glob.glob(os.path.join(search_root, '**', pattern), recursive=True))
    # Исключим сам summary, если паттерн захватил
    files = [f for f in files if 'rolling_A_24m_summary' not in os.path.basename(f)]
    if verbose:
        click.echo(f"[Инфо] Найдено файлов роллинга: {len(files)}")
        for f in files:
            click.echo(f"  - {f}")
    rows: List[Dict] = []
    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception as e:
            if verbose:
                click.echo(f"[warn] Не удалось прочитать {f}: {e}")
            continue
        # Фильтруем пусые
        if df is None or df.empty:
            continue
        # Ожидаемые колонки: month,trades,pf,winrate,dd
        if 'pf' not in df.columns:
            if verbose:
                click.echo(f"[warn] В {f} нет колонки 'pf', пропускаю")
            continue
        # Вычисления
        n = len(df)
        share_pf_gt1 = float((df['pf'] > 1.0).sum()) / float(n) if n > 0 else 0.0
        pf_median = float(df['pf'].median()) if n > 0 else float('nan')
        pf_min = float(df['pf'].min()) if n > 0 else float('nan')
        wr_median = float(df['winrate'].median()) if 'winrate' in df.columns and n > 0 else float('nan')
        dd_median = float(df['dd'].median()) if 'dd' in df.columns and n > 0 else float('nan')
        tag = _extract_tag_from_filename(f)
        rows.append(dict(
            file=f,
            tag=tag,
            months=int(n),
            share_pf_gt1=share_pf_gt1,
            pf_median=pf_median,
            pf_min=pf_min,
            wr_median=wr_median,
            dd_median=dd_median,
        ))
    if not rows:
        click.echo("[warn] Не найдено валидных файлов роллинга по заданному шаблону.")
        raise SystemExit(1)
    res = pd.DataFrame(rows)
    res = res.sort_values(by=['share_pf_gt1', 'pf_median', 'pf_min'], ascending=[False, False, False]).reset_index(drop=True)
    res.insert(0, 'rank', res.index + 1)
    # Сохранить
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    res.to_csv(out_path, index=False)
    click.echo(f"[Инфо] Сводная таблица сохранена: {out_path}")
    # Вывести топ-10
    head = res.head(10)
    click.echo("Top-10 Stability:")
    with pd.option_context('display.max_columns', None):
        click.echo(head.to_string(index=False))


if __name__ == '__main__':
    main()
