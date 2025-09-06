# -*- coding: utf-8 -*-
"""
Возобновление микробатча A #7 с места остановки.
Проходит по сетке параметров и запускает только те комбинации, для которых нет целевого CSV.

Сетка соответствует micro7:
- sessions: {7–18, 8–17}
- rr_tp: {1.5, 1.8}
- a_atr_min: {0.0008, 0.0011}
- a_edge_mult: {0.5, 0.6}
- a_adx_min: {16, 18, 20}
- a_mid_slope_min: 0.00001
- a_kill_month_pf: 0.8, a_kill_month_min_trades: 6

Пример запуска:
  .venv/bin/python resume_microbatch_a7.py --python .venv/bin/python
"""
from __future__ import annotations

import argparse
import os
import subprocess
from typing import List, Tuple

SESSIONS: List[Tuple[int, int]] = [(7, 18), (8, 17)]
RR_LIST = [1.5, 1.8]
ATRMIN_LIST = ["0.0008", "0.0011"]  # как строки для имени файла
EDGE_LIST = ["0.5", "0.6"]
ADX_LIST = [16, 18, 20]
MS = "0.00001"
KP = 0.8
KT = 6


def expected_out_path(s: int, e: int, rr: float, atrmin: str, edge: str, adx: int) -> str:
    # Имя файла точно в формате, который создаёт micro7
    # Префикс + tag A (который добавляется backtest.py) в конце
    return (
        f"out/rolling_A_24m_portA_micro7_s{s}-{e}_rr{rr}_atrmin{atrmin}_edge{edge}_adx{adx}_ms{MS}_kp{KP}_kt{KT}_"
        f"rsi18_bb2.0_atr1.2_risk0.5_rr{rr}_london{s}-{e}_atrmin{atrmin}_edge{edge}.csv"
    )


def run_one(python_exe: str, s: int, e: int, rr: float, atrmin: str, edge: str, adx: int) -> int:
    out_tpl = (
        f"out/rolling_A_24m_portA_micro7_s{s}-{e}_rr{rr}_atrmin{atrmin}_edge{edge}_adx{adx}_ms{MS}_kp{KP}_kt{KT}_{{tag}}.csv"
    )
    cmd = [
        python_exe, 'backtest.py',
        '--data-root', 'data', '--symbol', 'EURUSD', '--timeframe', 'M15',
        '--strategy', 'A',
        '--rsi-len', '18', '--bb-std', '2.0', '--atr-mult-sl', '1.2', '--risk-pct', '0.005',
        '--rr-tp', str(rr),
        '--a-session-start', str(s), '--a-session-end', str(e),
        '--a-atr-min', atrmin, '--a-edge-mult', edge,
        '--a-adx-min', str(adx), '--a-mid-slope-min', MS,
        '--a-kill-month-pf', str(KP), '--a-kill-month-min-trades', str(KT),
        '--commission-bps', '5', '--spread-pips', '0.8', '--slippage-pips', '0.2',
        '--cache-resampled', '--rolling-24m', '--rolling-exclude-partial',
        '--rolling-out', out_tpl,
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
        for rr in RR_LIST:
            for atrmin in ATRMIN_LIST:
                for edge in EDGE_LIST:
                    for adx in ADX_LIST:
                        total += 1
                        path = expected_out_path(s, e, rr, atrmin, edge, adx)
                        if os.path.exists(path):
                            print('[SKIP] exists', path)
                        else:
                            pending.append((s, e, rr, atrmin, edge, adx))

    print(f"[Итог] Всего комбо: {total}; К запуску: {len(pending)}")

    fails = 0
    for s, e, rr, atrmin, edge, adx in pending:
        rc = run_one(args.python, s, e, rr, atrmin, edge, adx)
        if rc != 0:
            print('[warn] возвратный код', rc)
            fails += 1
    print(f"[Готово] Успехов: {len(pending) - fails}, Ошибок: {fails}")


if __name__ == '__main__':
    main()
