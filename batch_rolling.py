# -*- coding: utf-8 -*-
"""
Пакетный запуск роллинга Strategy A по топ-N параметрам из tune_A_results.csv
с набором фильтров (сессии/ATRmin/edge), с последующим пересчётом stability_score.

Пример:
  .venv/bin/python batch_rolling.py \
    --tune-csv out/tune_A_results.csv --n-top 2 --sort-by oos_pf \
    --data-root data --symbol EURUSD --timeframe M15 \
    --sessions "7-18,8-17" --atrmin "0.0005,0.0007" --edge "0.5,1.0" \
    --include-baseline --max-runs 0 --dry-run
"""
from __future__ import annotations

import os
import sys
import shlex
import subprocess
from typing import List, Tuple

import click
import pandas as pd


def _parse_pairs(s: str) -> List[Tuple[int, int]]:
    if not s:
        return []
    out: List[Tuple[int, int]] = []
    for token in s.split(','):
        token = token.strip()
        if not token:
            continue
        if '-' not in token:
            raise click.BadParameter(f"Ожидается формат пары часов 'start-end', получено: {token}")
        a, b = token.split('-', 1)
        out.append((int(a), int(b)))
    return out


def _parse_floats(s: str) -> List[float]:
    if not s:
        return []
    vals: List[float] = []
    for token in s.split(','):
        token = token.strip()
        if token:
            vals.append(float(token))
    return vals


@click.command()
@click.option('--tune-csv', type=click.Path(exists=True), default='out/tune_A_results.csv', show_default=True,
              help='CSV с результатами подбора параметров Strategy A')
@click.option('--n-top', type=int, default=3, show_default=True, help='Сколько лучших наборов параметров выбрать')
@click.option('--sort-by', type=str, default='oos_pf', show_default=True, help='Столбец для сортировки (по убыванию)')
@click.option('--data-root', type=click.Path(file_okay=False), required=True, help='Корень каталога с данными')
@click.option('--symbol', type=str, required=True, help='Тикер, например EURUSD')
@click.option('--timeframe', type=str, default='M15', show_default=True, help='Таймфрейм данных')
@click.option('--sessions', type=str, default='7-18,8-17', show_default=True,
              help='Список сессионных окон (через запятую), формат каждого: start-end')
@click.option('--atrmin', type=str, default='0.0005,0.0007,0.0010', show_default=True,
              help='Список значений минимального ATR для входа (ценовые единицы)')
@click.option('--edge', type=str, default='0.5,0.75,1.0', show_default=True,
              help='Список значений edge-множителя до полосы Боллинджера')
@click.option('--include-baseline/--no-include-baseline', default=True, show_default=True,
              help='Добавить прогон без фильтров для каждого набора параметров')
@click.option('--pass-through', type=str, default='', show_default=False,
              help='Доп. флаги для backtest.py, передаются как есть (например: "--commission-bps 5")')
@click.option('--max-runs', type=int, default=0, show_default=True,
              help='Ограничение на число запусков (0 = без ограничения)')
@click.option('--dry-run', is_flag=True, default=False, show_default=True, help='Показывать команды, но не выполнять')
@click.option('--recalc-summary/--no-recalc-summary', default=True, show_default=True,
              help='После прогонов пересчитать stability_score')
@click.option('--summary-pattern', type=str, default='rolling_A_24m*.csv', show_default=True,
              help='Шаблон файлов роллинга для stability_score')
@click.option('--summary-out', type=str, default='out/rolling_A_24m_summary.csv', show_default=True,
              help='Файл сводной таблицы stability_score')
@click.option('--python', 'python_exe', type=str, default=sys.executable, show_default=True,
              help='Интерпретатор Python для запуска backtest.py/stability_score.py')
def main(
    tune_csv: str,
    n_top: int,
    sort_by: str,
    data_root: str,
    symbol: str,
    timeframe: str,
    sessions: str,
    atrmin: str,
    edge: str,
    include_baseline: bool,
    pass_through: str,
    max_runs: int,
    dry_run: bool,
    recalc_summary: bool,
    summary_pattern: str,
    summary_out: str,
    python_exe: str,
):
    # Загрузка топ-N
    df = pd.read_csv(tune_csv)
    if sort_by not in df.columns:
        raise click.UsageError(f"В файле {tune_csv} нет столбца '{sort_by}'. Доступные: {list(df.columns)}")
    df = df.sort_values(by=sort_by, ascending=False).head(n_top).reset_index(drop=True)

    sess_pairs = _parse_pairs(sessions)
    atr_vals = _parse_floats(atrmin)
    edge_vals = _parse_floats(edge)

    extra_args = shlex.split(pass_through) if pass_through else []
    # Доп. колонки, которые могут появиться в расширенном гриде подбора
    cols = set(df.columns)

    # Построение списка запусков
    runs: List[List[str]] = []
    for i, row in df.iterrows():
        rsi_len = int(row['rsi_len'])
        bb_std = float(row['bb_std'])
        atr_mult_sl = float(row['atr_mult_sl'])
        risk_pct = float(row['risk_pct'])

        # Необязательные параметры из результата подбора (если присутствуют)
        rr_tp_val = float(row['rr_tp']) if ('rr_tp' in cols and pd.notnull(row['rr_tp'])) else None
        rsi_os_val = float(row['rsi_os']) if ('rsi_os' in cols and pd.notnull(row['rsi_os'])) else None
        rsi_ob_val = float(row['rsi_ob']) if ('rsi_ob' in cols and pd.notnull(row['rsi_ob'])) else None
        bb_len_val = int(row['bb_len']) if ('bb_len' in cols and pd.notnull(row['bb_len'])) else None

        base = [
            python_exe, 'backtest.py',
            '--data-root', data_root,
            '--symbol', symbol,
            '--timeframe', timeframe,
            '--strategy', 'A',
            '--rsi-len', str(rsi_len),
            '--bb-std', str(bb_std),
            '--atr-mult-sl', str(atr_mult_sl),
            '--risk-pct', str(risk_pct),
            '--rolling-24m',
            # rolling_out по умолчанию: out/rolling_A_24m_{tag}.csv
        ] + extra_args

        # Прокидываем необязательные параметры, если доступны
        if rr_tp_val is not None:
            base += ['--rr-tp', str(rr_tp_val)]
        if rsi_os_val is not None:
            base += ['--rsi-os', str(rsi_os_val)]
        if rsi_ob_val is not None:
            base += ['--rsi-ob', str(rsi_ob_val)]
        if bb_len_val is not None:
            base += ['--bb-len', str(bb_len_val)]

        if include_baseline:
            runs.append(base[:])

        # Комбинации фильтров
        if not sess_pairs:
            sess_pairs_iter = [None]
        else:
            sess_pairs_iter = sess_pairs

        atr_iter = atr_vals or [None]
        edge_iter = edge_vals or [None]

        for sess in sess_pairs_iter:
            for atr_min in atr_iter:
                for edge_mult in edge_iter:
                    args = base[:]
                    if sess is not None:
                        s, e = sess
                        args += ['--a-session-start', str(s), '--a-session-end', str(e)]
                    if atr_min is not None:
                        args += ['--a-atr-min', str(atr_min)]
                    if edge_mult is not None:
                        args += ['--a-edge-mult', str(edge_mult)]
                    # Не используем --rolling-save-current в пакетном режиме, чтобы избежать перезаписи
                    runs.append(args)

    # Ограничение по числу запусков
    total = len(runs)
    if max_runs and total > max_runs:
        click.echo(f"[Инфо] План запусков {total} сокращён до {max_runs}")
        runs = runs[:max_runs]

    click.echo(f"[Инфо] Запусков запланировано: {len(runs)}")
    for cmd in runs:
        click.echo('  ' + ' '.join(shlex.quote(x) for x in cmd))

    if dry_run:
        click.echo('[Инфо] dry-run: выполнение пропущено')
        return

    # Выполнение
    failures = 0
    for idx, cmd in enumerate(runs, 1):
        click.echo(f"[Инфо] [{idx}/{len(runs)}] Запуск...")
        try:
            res = subprocess.run(cmd, check=False)
            if res.returncode != 0:
                failures += 1
                click.echo(f"[warn] Команда завершилась с кодом {res.returncode}")
        except Exception as e:
            failures += 1
            click.echo(f"[warn] Ошибка запуска: {e}")

    click.echo(f"[Итог] Успешно: {len(runs) - failures}, Ошибок: {failures}")

    if recalc_summary:
        click.echo('[Инфо] Пересчитываю stability_score...')
        cmd = [python_exe, 'stability_score.py', '--search-root', '.', '--pattern', summary_pattern, '--out', summary_out]
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            click.echo(f"[warn] stability_score завершился с кодом {res.returncode}")
        else:
            click.echo('[Инфо] Сводка обновлена')


if __name__ == '__main__':
    main()
