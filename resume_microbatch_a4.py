# -*- coding: utf-8 -*-
"""
Возобновление микробатча A #4 с места остановки.
Пробегает по сетке параметров и запускает только те комбинации, для которых нет файла роллинга.

Сетка соответствует ранее запущенной серии:
- sessions: {7–18, 8–17, 7–19, 9–18}
- rr_tp: {1.5, 1.8}
- a_adx_min: {12, 15}
- a_bb_width_min: {0.0004, 0.0006}
- a_mid_slope_min: {0.00001, 0.00002}
- a_kill_month_pf: {0.6, 0.8}, a_kill_month_min_trades=6
- Прочие константы: rsi_len=18, bb_std=2.0, atr_mult_sl=1.2, risk_pct=0.005, комиссии/спред/слиппедж как прежде.

Пример:
  .venv/bin/python resume_microbatch_a4.py --python .venv/bin/python
"""
from __future__ import annotations

import argparse
import os
import subprocess
from typing import List, Tuple


SESSIONS: List[Tuple[int, int]] = [(7, 18), (8, 17), (7, 19), (9, 18)]
RR_LIST = [1.5, 1.8]
ADX_LIST = [12, 15]
BBW_LIST = ["0.0004", "0.0006"]  # строки, чтобы имя файла совпало
MS_LIST = ["0.00001", "0.00002"]
KP_LIST = [0.6, 0.8]
KT = 6


def expected_out_path(s: int, e: int, rr: float, adx: int, bbw: str, ms: str, kp: float) -> str:
    # Имя файла строго как в запуске микробатча #4
    # В конце используем ожидаемый tag A: _rsi18_bb2.0_atr1.2_risk0.5_rr{rr}_london{s}-{e}.csv
    return (
        f"out/rolling_A_24m_portA_micro4_s{s}-{e}_rr{rr}_adx{adx}_bbw{bbw}_ms{ms}_kp{kp}_kt{KT}_"
        f"rsi18_bb2.0_atr1.2_risk0.5_rr{rr}_london{s}-{e}.csv"
    )


def run_one(python_exe: str, s: int, e: int, rr: float, adx: int, bbw: str, ms: str, kp: float) -> int:
    out_tpl = f"out/rolling_A_24m_portA_micro4_s{s}-{e}_rr{rr}_adx{adx}_bbw{bbw}_ms{ms}_kp{kp}_kt{KT}_{{tag}}.csv"
    cmd = [
        python_exe, 'backtest.py',
        '--data-root', 'data', '--symbol', 'EURUSD', '--timeframe', 'M15',
        '--strategy', 'A',
        '--rsi-len', '18', '--bb-std', '2.0', '--atr-mult-sl', '1.2', '--risk-pct', '0.005',
        '--rr-tp', str(rr),
        '--a-session-start', str(s), '--a-session-end', str(e),
        '--a-adx-min', str(adx), '--a-bb-width-min', bbw, '--a-mid-slope-min', ms,
        '--a-kill-month-pf', str(kp), '--a-kill-month-min-trades', str(KT),
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
            for adx in ADX_LIST:
                for bbw in BBW_LIST:
                    for ms in MS_LIST:
                        for kp in KP_LIST:
                            total += 1
                            path = expected_out_path(s, e, rr, adx, bbw, ms, kp)
                            if os.path.exists(path):
                                print('[SKIP] exists', path)
                            else:
                                pending.append((s, e, rr, adx, bbw, ms, kp))

    print(f"[Итог] Всего комбо: {total}; К запуску: {len(pending)}")

    fails = 0
    for s, e, rr, adx, bbw, ms, kp in pending:
        rc = run_one(args.python, s, e, rr, adx, bbw, ms, kp)
        if rc != 0:
            print('[warn] возвратный код', rc)
            fails += 1
    print(f"[Готово] Успехов: {len(pending) - fails}, Ошибок: {fails}")


if __name__ == '__main__':
    main()
