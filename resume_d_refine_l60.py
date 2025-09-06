# -*- coding: utf-8 -*-
"""
Возобновление уточняющих прогонов Strategy D (L60, trail=3.0, EMA200 trend-only)
с места остановки. Запускает только недостающие комбинации из сетки:
- d_len=60, d_trail_mult=3.0, d_ema_len=200, d_ema_trend_only=True
- sessions: {7–18, 8–17}
- d_buffer_atr: {1.5, 2.0}
- d_adx_min: {22, 30}
Издержки и риск-профиль как в текущей серии.

Пример:
  .venv/bin/python resume_d_refine_l60.py --python .venv/bin/python
"""
from __future__ import annotations

import argparse
import os
import subprocess
from typing import List, Tuple

SESSIONS: List[Tuple[int, int]] = [(7, 18), (8, 17)]
BUFFERS = ["1.5", "2.0"]  # строками для имени
ADXS = [22, 30]
LEN = 60
TRAIL = 3.0
EMA_LEN = 200


def expected_out_path(s: int, e: int, buf: str, adx: int) -> str:
    # Имя файла как его формирует тег D в backtest.py с нашим шаблоном rolling-out: out/rolling_D_24m_portD2_{tag}.csv
    # tag: dc{len}_buf{buffer}_atr1.0_risk0.5_trail{trail}_london{s}-{e}_adx{adx}_ema{EMA}_trend
    return (
        f"out/rolling_D_24m_portD2_dc{LEN}_buf{buf}_atr1.0_risk0.5_trail{int(TRAIL)}_"
        f"london{s}-{e}_adx{adx}_ema{EMA_LEN}_trend.csv"
    )


def run_one(python_exe: str, s: int, e: int, buf: str, adx: int) -> int:
    out_tpl = f"out/rolling_D_24m_portD2_{{tag}}.csv"
    cmd = [
        python_exe, 'backtest.py',
        '--data-root', 'data', '--symbol', 'EURUSD', '--timeframe', 'M15',
        '--strategy', 'D', '--spread-pips', '0.8', '--slippage-pips', '0.2', '--commission-bps', '5', '--risk-pct', '0.005',
        '--d-len', str(LEN), '--d-buffer-atr', buf, '--d-trail-mult', str(TRAIL), '--d-adx-min', str(adx), '--d-adx-len', '14',
        '--d-session-start', str(s), '--d-session-end', str(e), '--d-ema-len', str(EMA_LEN), '--d-ema-trend-only',
        '--rolling-24m', '--rolling-exclude-partial', '--rolling-out', out_tpl,
        '--save-run', f'out/run_D_refine_L{LEN}_B{buf.replace(".","")}_ADX{adx}_S{s}{e}.json'
    ]
    print('[RUN]', ' '.join(cmd))
    return subprocess.call(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--python', default='.venv/bin/python', help='Путь к интерпретатору Python')
    args = ap.parse_args()

    pending = []
    total = 0
    for s, e in SESSIONS:
        for buf in BUFFERS:
            for adx in ADXS:
                total += 1
                path = expected_out_path(s, e, buf, adx)
                if os.path.exists(path):
                    print('[SKIP] exists', path)
                else:
                    pending.append((s, e, buf, adx))

    print(f"[Итог] Всего комбо: {total}; К запуску: {len(pending)}")

    fails = 0
    for s, e, buf, adx in pending:
        rc = run_one(args.python, s, e, buf, adx)
        if rc != 0:
            print('[warn] возвратный код', rc)
            fails += 1
    print(f"[Готово] Успехов: {len(pending) - fails}, Ошибок: {fails}")


if __name__ == '__main__':
    main()
