# -*- coding: utf-8 -*-
"""
Простой каркас бэктеста EURUSD M15 c RR 1:3 для стратегий A и C.
- Стратегия A: Bollinger + RSI (mean-reversion с жёстким RR 1:3)
- Стратегия C: EMA pullback (тренд с отката, RR 1:3)

Учёт издержек:
- spread (в процентах от цены) — в backtesting.py применяется однократно через _adjusted_price.
- проскальзывание — грубо включаем в spread через конвертацию пипсов в долю цены.

Примеры запуска:

  .venv/bin/python backtest.py --data-root data --symbol EURUSD --timeframe M15 \
      --strategy ALL --spread-pips 0.8 --slippage-pips 0.2 --cash 10000
"""
from __future__ import annotations

import sys
import os
import json
import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict

import click
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy
import backtesting as btlib

from data_utils import load_ohlc, pip_size

# ------------------------ Вспомогательные индикаторы ------------------------

def _ema(close: np.ndarray, length: int = 20):
    s = pd.Series(np.asarray(close))
    e = s.ewm(span=length, adjust=False, min_periods=length).mean()
    return e.to_numpy()

def _rsi(close: np.ndarray, length: int = 14):
    s = pd.Series(np.asarray(close))
    delta = s.diff()
    up = pd.Series(np.where(delta > 0, delta, 0.0))
    down = pd.Series(np.where(delta < 0, -delta, 0.0))
    roll_up = up.ewm(span=length, adjust=False, min_periods=length).mean()
    roll_down = down.ewm(span=length, adjust=False, min_periods=length).mean()
    rs = roll_up / roll_down
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.to_numpy()

def _bbands(close: np.ndarray, length: int = 20, std: float = 2.0):
    s = pd.Series(np.asarray(close))
    ma = s.rolling(length, min_periods=length).mean()
    sd = s.rolling(length, min_periods=length).std(ddof=0)
    bbl = (ma - std * sd).to_numpy()
    bbm = ma.to_numpy()
    bbu = (ma + std * sd).to_numpy()
    return np.vstack([bbl, bbm, bbu])  # (3, N)

def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14):
    h = pd.Series(np.asarray(high))
    l = pd.Series(np.asarray(low))
    c = pd.Series(np.asarray(close))
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=length, adjust=False, min_periods=length).mean()
    return atr.to_numpy()

def _adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int = 14):
    """Простой расчёт ADX (Вайлдер) для фильтра направленности.
    Возвращает массив ADX той же длины, первые значения NaN до накопления окна."""
    h = pd.Series(np.asarray(high))
    l = pd.Series(np.asarray(low))
    c = pd.Series(np.asarray(close))
    up = h.diff()
    down = -l.diff()
    plus_dm = ((up > down) & (up > 0)).astype(float) * up
    minus_dm = ((down > up) & (down > 0)).astype(float) * down
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/length, adjust=False, min_periods=length).mean() / atr)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    adx = dx.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    return adx.to_numpy()

def _donchian(high: np.ndarray, low: np.ndarray, length: int = 20):
    """Каналы Дончиана: верхний = max(High, L), нижний = min(Low, L)."""
    h = pd.Series(np.asarray(high))
    l = pd.Series(np.asarray(low))
    upper = h.rolling(length, min_periods=length).max().to_numpy()
    lower = l.rolling(length, min_periods=length).min().to_numpy()
    return np.vstack([upper, lower])

def _asia_range(high: np.ndarray, low: np.ndarray, index, asia_start_h: int = 0, asia_end_h: int = 6):
    # Вернём массивы длины N: high/low азиатской сессии (по дням)
    idx = pd.DatetimeIndex(index)
    h = pd.Series(np.asarray(high), index=idx)
    l = pd.Series(np.asarray(low), index=idx)
    asia_hi = pd.Series(np.nan, index=idx)
    asia_lo = pd.Series(np.nan, index=idx)
    # Пройдём по дням
    for day, grp in h.groupby(h.index.date):
        day_idx = pd.DatetimeIndex(grp.index)
        mask_asia = (day_idx.hour >= asia_start_h) & (day_idx.hour < asia_end_h)
        if mask_asia.any():
            hi = float(h.loc[grp.index[mask_asia]].max())
            lo = float(l.loc[grp.index[mask_asia]].min())
            # Заполним значением на весь день (упростим использование)
            day_mask = idx.date == day
            asia_hi.loc[day_mask] = hi
            asia_lo.loc[day_mask] = lo
    return np.vstack([asia_hi.to_numpy(), asia_lo.to_numpy()])

def _session_window(index, start_h: int, end_h: int):
    idx = pd.DatetimeIndex(index)
    arr = ((idx.hour >= start_h) & (idx.hour < end_h)).astype(float)
    return np.asarray(arr)

# ----------------------- Сессионные множители спреда ------------------------

def _parse_session_spread(s: Optional[str]):
    """Парсинг строки вида "asia=1.2,london=1.0,ny=1.1" -> dict.
    Отсутствующие ключи получают множитель 1.0. Поддерживаются ключи: asia, london, ny, other.
    """
    mults = {"asia": 1.0, "london": 1.0, "ny": 1.0, "other": 1.0}
    if not s:
        return mults
    try:
        parts = [p.strip() for p in str(s).split(',') if p.strip()]
        for p in parts:
            if '=' in p:
                k, v = p.split('=', 1)
                k = k.strip().lower()
                v = float(v.strip())
                if k in mults:
                    mults[k] = max(0.0, float(v))
    except Exception:
        # Если парсинг не удался, вернём единичные множители
        mults = {"asia": 1.0, "london": 1.0, "ny": 1.0, "other": 1.0}
    return mults

def _weighted_session_multiplier(index, mults: Dict[str, float]) -> float:
    """Рассчитать средневзвешенный множитель спреда по сессиям.
    Сессии: Asia [0,6), London [7,12), NY [13,17), Other — остальное. Вес — доля баров в интервале.
    """
    idx = pd.DatetimeIndex(index)
    hours = idx.hour
    mask_asia = (hours >= 0) & (hours < 6)
    mask_london = (hours >= 7) & (hours < 12)
    mask_ny = (hours >= 13) & (hours < 17)
    n = len(idx)
    if n == 0:
        return 1.0
    w_asia = mask_asia.sum() / n
    w_london = mask_london.sum() / n
    w_ny = mask_ny.sum() / n
    w_other = 1.0 - (w_asia + w_london + w_ny)
    return (
        w_asia * mults.get('asia', 1.0) +
        w_london * mults.get('london', 1.0) +
        w_ny * mults.get('ny', 1.0) +
        w_other * mults.get('other', 1.0)
    )

# ------------------------------- Стратегии ----------------------------------

# --------------------- Риск-менеджмент: расчёт размера ----------------------

def _position_size_by_risk(*, equity: float, entry: float, sl: float,
                           risk_pct: Optional[float] = 0.01,
                           fixed_size: Optional[float] = None) -> int:
    """Расчёт размера позиции по риску.
    - Если задан `fixed_size>0`, вернуть его (int).
    - Иначе размер = floor((risk_pct * equity) / abs(entry - SL)),
      ограниченный максимумом по доступным средствам: floor(0.99 * equity / entry).
    Возвращает 0, если расчёт некорректен.
    """
    # Фиксированное количество юнитов
    if fixed_size is not None and float(fixed_size) > 0:
        return int(float(fixed_size))

    if entry is None or sl is None or entry <= 0 or not np.isfinite(entry) or not np.isfinite(sl):
        return 0

    rpct = 0.0 if risk_pct is None else float(risk_pct)
    rpct = max(0.0, rpct)
    if rpct == 0.0:
        return 0

    risk_per_unit = abs(entry - sl)
    if risk_per_unit <= 0 or not np.isfinite(risk_per_unit):
        return 0

    risk_amount = equity * rpct
    size_by_risk = int(risk_amount / risk_per_unit)

    # Ограничение сверху по кэшу (без плеча; здесь margin=1.0 в Backtest)
    max_units_by_cash = int((equity * 0.99) / entry)
    size = min(size_by_risk, max_units_by_cash)
    return int(size) if size >= 1 else 0

@dataclass
class CommonParams:
    symbol: str
    rr_tp: float = 3.0
    atr_mult_sl: float = 1.0

class StrategyA_BBRSI_RR3(Strategy):
    # Параметры стратегии задаются как атрибуты класса (API backtesting.py v0.6.5)
    rr_tp = 3.0
    atr_mult_sl = 1.0
    rsi_len = 14
    rsi_os = 30.0
    rsi_ob = 70.0
    bb_len = 20
    bb_std = 2.0
    risk_pct = 0.01
    fixed_size = None
    # Антишумовые фильтры (опционально)
    a_atr_min = 0.0           # минимальный ATR в абсолютных ценовых единицах
    a_edge_mult = 0.0         # требуемое расстояние от полосы Боллинджера в мультипликаторах ATR
    a_session_start = None    # если заданы оба часа, ограничить входы этой сессией
    a_session_end = None
    # Новые «ограждения» (опционально)
    a_bb_width_min = 0.0      # мин. относительная ширина полос Боллинджера: (bbu-bbl)/Close
    a_adx_min = 0.0           # мин. ADX
    a_adx_len = 14            # окно ADX
    a_mid_slope_min = 0.0     # мин. относительный наклон средней полосы |bbm - bbm[-L]|/(Close*L)
    a_mid_slope_len = 10      # окно для оценки наклона средней полосы
    a_dow_include = None      # допустимые дни недели, например "Tue,Wed,Thu"
    a_kill_month_pf = 0.0     # kill-switch: если после N сделок PF<порога — блок до конца месяца
    a_kill_month_min_trades = 0
    a_max_consec_losses = 0   # пауза после серии убыточных
    a_cooldown_bars = 0       # длительность паузы (в барах)
    a_be_trail_r = 0.0        # BE-трейл: перевести в безубыток при движении >= R (R в SL-единицах)
    # Маршрутизатор месяцев (router): блокировать следующий месяц по результатам последних N месяцев
    a_router_prev_m = 0       # длина окна (месяцев) для оценки, 0 = выкл
    a_router_prev_pf_thr = 0.0  # порог PF агрегата за N пред. месяцев
    a_router_min_trades = 0   # минимум сделок за N пред. месяцев для активации

    def init(self):
        self.atr = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 14)
        self.rsi = self.I(_rsi, self.data.Close, self.rsi_len)
        self.bbl, self.bbm, self.bbu = self.I(_bbands, self.data.Close, self.bb_len, self.bb_std)
        # ADX по требованию
        try:
            if float(self.a_adx_min) > 0:
                self.adx = self.I(_adx, self.data.High, self.data.Low, self.data.Close, int(self.a_adx_len))
            else:
                self.adx = None
        except Exception:
            self.adx = None
        # Сессионное окно при необходимости
        try:
            if self.a_session_start is not None and self.a_session_end is not None:
                self.session = self.I(_session_window, self.data.index,
                                      int(self.a_session_start), int(self.a_session_end))
            else:
                self.session = None
        except Exception:
            self.session = None
        # Разбор дней недели
        self._dow_set = None
        try:
            if self.a_dow_include:
                names = [s.strip().lower() for s in str(self.a_dow_include).split(',') if s.strip()]
                map_idx = {'mon':0,'monday':0,'tue':1,'tuesday':1,'wed':2,'wednesday':2,
                           'thu':3,'thursday':3,'fri':4,'friday':4,'sat':5,'saturday':5,'sun':6,'sunday':6}
                self._dow_set = {map_idx[n[:3]] if n[:3] in map_idx else map_idx.get(n, None) for n in names}
                self._dow_set = {d for d in self._dow_set if d is not None}
        except Exception:
            self._dow_set = None
        # Служебные счётчики/состояния
        self._consec_losses = 0
        self._cooldown_left = 0
        self._be_armed = False
        self._open_entry = None
        self._open_risk = None
        self._month_stats = {}   # key -> dict(trades, gp, gl)
        self._month_blocked = set()
        # Router: контроль перехода месяца
        self._router_last_month = None
        # Буфер сигналов для экспорта (мост к реальной торговле)
        self._signals = []
        # Класс-уровень: общий накопитель для извлечения после bt.run()
        try:
            type(self).emitted_signals  # проверка наличия
        except AttributeError:
            type(self).emitted_signals = []

    def next(self):
        i = -1
        close = float(self.data.Close[i])
        atr = float(self.atr[i]) if not np.isnan(self.atr[i]) else None
        rsi = float(self.rsi[i]) if not np.isnan(self.rsi[i]) else None
        bbl = float(self.bbl[i]) if not np.isnan(self.bbl[i]) else None
        bbu = float(self.bbu[i]) if not np.isnan(self.bbu[i]) else None
        # Router: на первом баре каждого месяца решаем, блокировать ли месяц
        try:
            if int(self.a_router_prev_m) > 0 and float(self.a_router_prev_pf_thr) > 0:
                ts_now = pd.Timestamp(self.data.index[i])
                mk_now = ts_now.strftime('%Y-%m')
                if getattr(self, '_router_last_month', None) != mk_now:
                    self._router_last_month = mk_now
                    prev_n = int(self.a_router_prev_m)
                    cur_per = ts_now.to_period('M')
                    prev_stats = []
                    for k in range(1, prev_n + 1):
                        pmk = str(cur_per - k)
                        st = self._month_stats.get(pmk)
                        if st:
                            prev_stats.append(st)
                    if len(prev_stats) == prev_n:
                        total_trades = sum(int(st.get('trades', 0)) for st in prev_stats)
                        if int(self.a_router_min_trades) == 0 or total_trades >= int(self.a_router_min_trades):
                            gp_tot = sum(float(st.get('gp', 0.0)) for st in prev_stats)
                            gl_tot = sum(float(st.get('gl', 0.0)) for st in prev_stats)
                            pf_prev = (gp_tot / abs(gl_tot)) if gl_tot < 0 else float('inf')
                            if pf_prev < float(self.a_router_prev_pf_thr):
                                self._month_blocked.add(mk_now)
        except Exception:
            pass

        if atr is None or rsi is None or bbl is None or bbu is None:
            return

        # Управление позицией (BE-трейл)
        if self.position:
            try:
                if float(self.a_be_trail_r) > 0 and self._open_entry is not None and self._open_risk is not None:
                    entry = float(self._open_entry)
                    risk = float(self._open_risk)
                    if self.position.is_long:
                        # Во столько же пунктов в прибыль от входа
                        if not self._be_armed and (close - entry) >= float(self.a_be_trail_r) * risk:
                            self._be_armed = True
                        if self._be_armed and close <= entry:
                            self.position.close()
                            # сбросим флаги; trade() обновит счётчики
                            self._be_armed = False
                            self._open_entry = None
                            self._open_risk = None
                            return
                    else:
                        if not self._be_armed and (entry - close) >= float(self.a_be_trail_r) * risk:
                            self._be_armed = True
                        if self._be_armed and close >= entry:
                            self.position.close()
                            self._be_armed = False
                            self._open_entry = None
                            self._open_risk = None
                            return
            except Exception:
                pass
            # Больше ничего не делаем, пока позиция открыта
            return

        # Сессионный фильтр
        if getattr(self, 'session', None) is not None:
            try:
                if not bool(self.session[i]):
                    return
            except Exception:
                pass
        # Фильтр по дням недели
        try:
            if self._dow_set is not None:
                ts = pd.Timestamp(self.data.index[i])
                if ts.weekday() not in self._dow_set:
                    return
        except Exception:
            pass
        # Пауза после серии убыточных
        try:
            if int(self.a_max_consec_losses) > 0 and int(self.a_cooldown_bars) > 0 and self._cooldown_left > 0:
                self._cooldown_left -= 1
                return
        except Exception:
            pass
        # Блокировка месяца по kill-switch
        try:
            if float(self.a_kill_month_pf) > 0 and int(self.a_kill_month_min_trades) > 0:
                ts = pd.Timestamp(self.data.index[i])
                mk = ts.strftime('%Y-%m')
                if mk in self._month_blocked:
                    return
        except Exception:
            pass

        # Минимальная волатильность по ATR
        try:
            if float(self.a_atr_min) > 0 and atr < float(self.a_atr_min):
                return
        except Exception:
            pass
        # Фильтр по ширине полос Боллинджера (отн.)
        try:
            if float(self.a_bb_width_min) > 0:
                width_rel = (float(self.bbu[i]) - float(self.bbl[i])) / max(close, 1e-12)
                if width_rel < float(self.a_bb_width_min):
                    return
        except Exception:
            pass
        # Фильтр по ADX
        try:
            if float(self.a_adx_min) > 0 and getattr(self, 'adx', None) is not None:
                adx_v = float(self.adx[i]) if not np.isnan(self.adx[i]) else None
                if adx_v is None or adx_v < float(self.a_adx_min):
                    return
        except Exception:
            pass
        # Фильтр по наклону средней полосы (отн.)
        try:
            if float(self.a_mid_slope_min) > 0 and int(self.a_mid_slope_len) > 0:
                k = int(self.a_mid_slope_len)
                if len(self.bbm) + i - k >= 0:  # достаточно истории
                    bbm_cur = float(self.bbm[i])
                    bbm_prev = float(self.bbm[-1 - k])
                    slope_rel = abs(bbm_cur - bbm_prev) / (max(close, 1e-12) * k)
                    if slope_rel < float(self.a_mid_slope_min):
                        return
        except Exception:
            pass

        # Long: перепроданность и выход из нижней полосы
        long_edge_ok = True
        try:
            if float(self.a_edge_mult) > 0:
                long_edge_ok = (bbl - close) >= float(self.a_edge_mult) * atr
        except Exception:
            long_edge_ok = True
        if close < bbl and rsi < float(self.rsi_os) and long_edge_ok:
            sl = close - self.atr_mult_sl * atr
            tp = close + self.rr_tp * (close - sl)
            if sl > 0 and tp > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    # Логируем сигнал входа (на закрытии бара)
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'buy',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'A_long'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    # Зафиксируем данные для BE‑трейла
                    self._open_entry = float(close)
                    self._open_risk = float(close - sl)
                    self._be_armed = False
                    self.buy(size=size, sl=sl, tp=tp, tag='A_long')
                return

        # Short: перекупленность и выход за верхнюю полосу
        short_edge_ok = True
        try:
            if float(self.a_edge_mult) > 0:
                short_edge_ok = (close - bbu) >= float(self.a_edge_mult) * atr
        except Exception:
            short_edge_ok = True
        if close > bbu and rsi > float(self.rsi_ob) and short_edge_ok:
            sl = close + self.atr_mult_sl * atr
            tp = close - self.rr_tp * (sl - close)
            if tp > 0 and sl > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    # Логируем сигнал входа (на закрытии бара)
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'sell',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'A_short'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self._open_entry = float(close)
                    self._open_risk = float(sl - close)
                    self._be_armed = False
                    self.sell(size=size, sl=sl, tp=tp, tag='A_short')
                return

    def notify_trade(self, trade):
        """Коллбек на обновление сделки (backtesting.py): ведём учёт серий/месяцев для kill‑switch и паузы."""
        try:
            if not trade.is_closed:
                return
            # Сброс данных BE при закрытии
            self._be_armed = False
            self._open_entry = None
            self._open_risk = None
            # Обновим серию
            pnl = float(trade.pl) if hasattr(trade, 'pl') else 0.0
            if pnl < 0:
                self._consec_losses = int(self._consec_losses) + 1
            else:
                self._consec_losses = 0
            # Пауза после серии
            try:
                if int(self.a_max_consec_losses) > 0 and int(self.a_cooldown_bars) > 0 and self._consec_losses >= int(self.a_max_consec_losses):
                    self._cooldown_left = int(self.a_cooldown_bars)
                    self._consec_losses = 0
            except Exception:
                pass
            # Учёт по месяцу
            try:
                ts = pd.Timestamp(getattr(trade, 'exit_time', pd.Timestamp.utcnow()))
            except Exception:
                ts = pd.Timestamp.utcnow()
            mk = ts.strftime('%Y-%m')
            st = self._month_stats.get(mk, {'trades':0, 'gp':0.0, 'gl':0.0})
            st['trades'] += 1
            if pnl >= 0:
                st['gp'] += pnl
            else:
                st['gl'] += pnl  # отрицательное
            self._month_stats[mk] = st
            try:
                if float(self.a_kill_month_pf) > 0 and int(self.a_kill_month_min_trades) > 0:
                    if st['trades'] >= int(self.a_kill_month_min_trades):
                        gp = float(st['gp'])
                        gl = float(st['gl'])
                        pf = gp / abs(gl) if gl < 0 else float('inf')
                        if pf < float(self.a_kill_month_pf):
                            self._month_blocked.add(mk)
            except Exception:
                pass
        except Exception:
            pass

class StrategyC_EMAPullback_RR3(Strategy):
    rr_tp = 3.0
    atr_mult_sl = 1.0
    ema_fast = 50
    ema_slow = 200
    risk_pct = 0.01
    fixed_size = None

    def init(self):
        self.atr = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 14)
        self.ema_fast = self.I(_ema, self.data.Close, self.ema_fast)
        self.ema_slow = self.I(_ema, self.data.Close, self.ema_slow)
        # Буфер сигналов для экспорта
        self._signals = []
        try:
            type(self).emitted_signals
        except AttributeError:
            type(self).emitted_signals = []

    def next(self):
        i = -1
        close = float(self.data.Close[i])
        atr = float(self.atr[i]) if not np.isnan(self.atr[i]) else None
        ema_f = float(self.ema_fast[i]) if not np.isnan(self.ema_fast[i]) else None
        ema_s = float(self.ema_slow[i]) if not np.isnan(self.ema_slow[i]) else None
        if atr is None or ema_f is None or ema_s is None:
            return

        if self.position:
            return

        # Ап-тренд: ema_fast > ema_slow. Вход после пересечения вверх ema_fast (pullback/cross)
        prev_close = float(self.data.Close[-2]) if len(self.data.Close) >= 2 else close
        prev_ema_f = float(self.ema_fast[-2]) if len(self.ema_fast) >= 2 else ema_f
        prev_ema_s = float(self.ema_slow[-2]) if len(self.ema_slow) >= 2 else ema_s

        # Long сигнал: тренд вверх и кросс цены выше ema_fast после отката
        if ema_f > ema_s and (prev_close <= prev_ema_f) and (close > ema_f):
            sl = close - self.atr_mult_sl * atr
            tp = close + self.rr_tp * (close - sl)
            if sl > 0 and tp > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'buy',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'C_long'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self.buy(size=size, sl=sl, tp=tp, tag='C_long')
                return

        # Short сигнал: тренд вниз и кросс ниже ema_fast после отката
        if ema_f < ema_s and (prev_close >= prev_ema_f) and (close < ema_f):
            sl = close + self.atr_mult_sl * atr
            tp = close - self.rr_tp * (sl - close)
            if tp > 0 and sl > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'sell',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'C_short'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self.sell(size=size, sl=sl, tp=tp, tag='C_short')
                return

class StrategyB_AsiaFade_RR3(Strategy):
    rr_tp = 3.0
    atr_mult_sl = 1.0
    asia_start_h = 0
    asia_end_h = 6
    london_start_h = 7
    london_end_h = 12
    risk_pct = 0.01
    fixed_size = None

    def init(self):
        self.atr = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 14)
        self.asia_high, self.asia_low = self.I(
            _asia_range, self.data.High, self.data.Low, self.data.index,
            self.asia_start_h, self.asia_end_h)
        self.london = self.I(_session_window, self.data.index,
                             self.london_start_h, self.london_end_h)
        # Буфер сигналов для экспорта
        self._signals = []

    def next(self):
        i = -1
        if not bool(self.london[i]):
            return
        close = float(self.data.Close[i])
        prev_close = float(self.data.Close[-2]) if len(self.data.Close) >= 2 else close
        atr = float(self.atr[i]) if not np.isnan(self.atr[i]) else None
        ah = float(self.asia_high[i]) if not np.isnan(self.asia_high[i]) else None
        al = float(self.asia_low[i]) if not np.isnan(self.asia_low[i]) else None
        if atr is None or ah is None or al is None:
            return

        if self.position:
            return

        # Fade ложный пробой: возврат внутрь диапазона
        # Short: предыдущая свеча выше AH, текущая закрылась <= AH
        if prev_close > ah and close <= ah:
            sl = close + self.atr_mult_sl * atr
            tp = close - self.rr_tp * (sl - close)
            if tp > 0 and sl > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'sell',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'B_short'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self.sell(size=size, sl=sl, tp=tp, tag='B_short')
                return

        # Long: предыдущая свеча ниже AL, текущая закрылась >= AL
        if prev_close < al and close >= al:
            sl = close - self.atr_mult_sl * atr
            tp = close + self.rr_tp * (close - sl)
            if sl > 0 and tp > close:
                size = _position_size_by_risk(
                    equity=self.equity, entry=close, sl=sl,
                    risk_pct=self.risk_pct, fixed_size=self.fixed_size
                )
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {
                        'timestamp': ts,
                        'side': 'buy',
                        'price': close,
                        'sl': float(sl),
                        'tp': float(tp),
                        'size': int(size),
                        'tag': 'B_long'
                    }
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self.buy(size=size, sl=sl, tp=tp, tag='B_long')
                return

class StrategyD_DonchianBreakout(Strategy):
    rr_tp = 3.0
    atr_mult_sl = 1.0
    d_len = 40
    d_buffer_atr = 0.5
    d_trail_mult = 2.0  # ATR‑трейлинг: k*ATR от экстремума
    # Фильтры/ограждения
    d_adx_min = 12.0
    d_adx_len = 14
    d_session_start = None
    d_session_end = None
    d_dow_include = None
    d_ema_len = 0            # 0 = фильтр выключен
    d_ema_trend_only = False # если True: long только выше EMA, short только ниже EMA
    d_kill_month_pf = 0.0
    d_kill_month_min_trades = 0
    d_max_consec_losses = 0
    d_cooldown_bars = 0
    # Риск
    risk_pct = 0.01
    fixed_size = None

    def init(self):
        self.atr = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 14)
        self.dcU, self.dcL = self.I(_donchian, self.data.High, self.data.Low, int(self.d_len))
        # EMA тренд-фильтр по требованию
        try:
            if int(self.d_ema_len) and int(self.d_ema_len) > 0:
                self.ema = self.I(_ema, self.data.Close, int(self.d_ema_len))
            else:
                self.ema = None
        except Exception:
            self.ema = None
        # ADX по требованию
        try:
            if float(self.d_adx_min) > 0:
                self.adx = self.I(_adx, self.data.High, self.data.Low, self.data.Close, int(self.d_adx_len))
            else:
                self.adx = None
        except Exception:
            self.adx = None
        # Сессия
        try:
            if self.d_session_start is not None and self.d_session_end is not None:
                self.session = self.I(_session_window, self.data.index,
                                      int(self.d_session_start), int(self.d_session_end))
            else:
                self.session = None
        except Exception:
            self.session = None
        # Дни недели
        self._dow_set = None
        try:
            if self.d_dow_include:
                names = [s.strip().lower() for s in str(self.d_dow_include).split(',') if s.strip()]
                map_idx = {'mon':0,'monday':0,'tue':1,'tuesday':1,'wed':2,'wednesday':2,
                           'thu':3,'thursday':3,'fri':4,'friday':4,'sat':5,'saturday':5,'sun':6,'sunday':6}
                self._dow_set = {map_idx[n[:3]] if n[:3] in map_idx else map_idx.get(n, None) for n in names}
                self._dow_set = {d for d in self._dow_set if d is not None}
        except Exception:
            self._dow_set = None
        # Служебные состояния
        self._consec_losses = 0
        self._cooldown_left = 0
        # Для ATR‑трейла
        self._trail_price = None
        self._extreme = None
        self._open_entry = None
        self._month_stats = {}
        self._month_blocked = set()
        # Буфер сигналов
        self._signals = []
        try:
            type(self).emitted_signals
        except AttributeError:
            type(self).emitted_signals = []

    def next(self):
        i = -1
        close = float(self.data.Close[i])
        high = float(self.data.High[i])
        low = float(self.data.Low[i])
        atr = float(self.atr[i]) if not np.isnan(self.atr[i]) else None
        # Используем предыдущие значения канала (классическая логика Дончиана)
        u = float(self.dcU[-2]) if len(self.dcU) >= 2 and not np.isnan(self.dcU[-2]) else None
        l = float(self.dcL[-2]) if len(self.dcL) >= 2 and not np.isnan(self.dcL[-2]) else None
        if atr is None or u is None or l is None:
            return

        # Управление позицией: ATR‑трейлинг
        if self.position:
            try:
                k = float(self.d_trail_mult)
                if k > 0 and atr is not None and np.isfinite(atr):
                    if self.position.is_long:
                        # обновляем экстремум и трейл-линию (только вверх)
                        self._extreme = max(self._extreme if self._extreme is not None else -np.inf, high)
                        trail = self._extreme - k * atr
                        self._trail_price = max(self._trail_price if self._trail_price is not None else -np.inf, trail)
                        if close <= self._trail_price:
                            self.position.close()
                            self._trail_price = None
                            self._extreme = None
                            self._open_entry = None
                            return
                    else:
                        self._extreme = min(self._extreme if self._extreme is not None else np.inf, low)
                        trail = self._extreme + k * atr
                        self._trail_price = min(self._trail_price if self._trail_price is not None else np.inf, trail)
                        if close >= self._trail_price:
                            self.position.close()
                            self._trail_price = None
                            self._extreme = None
                            self._open_entry = None
                            return
            except Exception:
                pass
            return

        # Сессионный фильтр
        if getattr(self, 'session', None) is not None:
            try:
                if not bool(self.session[i]):
                    return
            except Exception:
                pass
        # Дни недели
        try:
            if self._dow_set is not None:
                ts = pd.Timestamp(self.data.index[i])
                if ts.weekday() not in self._dow_set:
                    return
        except Exception:
            pass
        # Пауза после серии
        try:
            if int(self.d_max_consec_losses) > 0 and int(self.d_cooldown_bars) > 0 and self._cooldown_left > 0:
                self._cooldown_left -= 1
                return
        except Exception:
            pass
        # Блокировка месяца
        try:
            if float(self.d_kill_month_pf) > 0 and int(self.d_kill_month_min_trades) > 0:
                ts = pd.Timestamp(self.data.index[i])
                mk = ts.strftime('%Y-%m')
                if mk in self._month_blocked:
                    return
        except Exception:
            pass
        # ADX фильтр
        try:
            if float(self.d_adx_min) > 0 and getattr(self, 'adx', None) is not None:
                adx_v = float(self.adx[i]) if not np.isnan(self.adx[i]) else None
                if adx_v is None or adx_v < float(self.d_adx_min):
                    return
        except Exception:
            pass

        # EMA тренд-фильтр (если включён)
        try:
            if bool(self.d_ema_trend_only) and getattr(self, 'ema', None) is not None:
                ema_v = float(self.ema[i]) if not np.isnan(self.ema[i]) else None
                if ema_v is None:
                    return
        except Exception:
            ema_v = None

        # Входы по пробою канала с ATR-буфером
        buf = float(self.d_buffer_atr) * atr if float(self.d_buffer_atr) > 0 else 0.0
        thr_long = u + buf
        thr_short = l - buf
        # Long breakout: пробой прошлой верхней границы (по Close или High)
        long_ok = (close > thr_long) or (high > thr_long and float(self.data.Close[-2]) <= u)
        if long_ok:
            # EMA-тренд: разрешить long только выше EMA (если включено)
            if bool(self.d_ema_trend_only) and getattr(self, 'ema', None) is not None:
                if close <= float(self.ema[i]):
                    long_ok = False
        if long_ok:
            sl = close - self.atr_mult_sl * atr
            tp = close + self.rr_tp * (close - sl)
            if sl > 0 and tp > close:
                size = _position_size_by_risk(equity=self.equity, entry=close, sl=sl,
                                              risk_pct=self.risk_pct, fixed_size=self.fixed_size)
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {'timestamp': ts, 'side': 'buy', 'price': close, 'sl': float(sl), 'tp': float(tp), 'size': int(size), 'tag': 'D_long'}
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self._open_entry = float(close)
                    self._trail_price = None
                    self._extreme = None
                    self.buy(size=size, sl=sl, tp=tp, tag='D_long')
                return
        # Short breakout: пробой прошлой нижней границы (по Close или Low)
        short_ok = (close < thr_short) or (low < thr_short and float(self.data.Close[-2]) >= l)
        if short_ok:
            if bool(self.d_ema_trend_only) and getattr(self, 'ema', None) is not None:
                if close >= float(self.ema[i]):
                    short_ok = False
        if short_ok:
            sl = close + self.atr_mult_sl * atr
            tp = close - self.rr_tp * (sl - close)
            if tp > 0 and sl > close:
                size = _position_size_by_risk(equity=self.equity, entry=close, sl=sl,
                                              risk_pct=self.risk_pct, fixed_size=self.fixed_size)
                if size > 0:
                    try:
                        ts = pd.Timestamp(self.data.index[i])
                    except Exception:
                        ts = pd.Timestamp.utcnow()
                    rec = {'timestamp': ts, 'side': 'sell', 'price': close, 'sl': float(sl), 'tp': float(tp), 'size': int(size), 'tag': 'D_short'}
                    self._signals.append(rec)
                    type(self).emitted_signals.append(rec)
                    self._open_entry = float(close)
                    self._trail_price = None
                    self._extreme = None
                    self.sell(size=size, sl=sl, tp=tp, tag='D_short')
                return

    def notify_trade(self, trade):
        try:
            if not trade.is_closed:
                return
            # сброс трейлинга
            self._trail_price = None
            self._extreme = None
            self._open_entry = None
            pnl = float(trade.pl) if hasattr(trade, 'pl') else 0.0
            if pnl < 0:
                self._consec_losses = int(self._consec_losses) + 1
            else:
                self._consec_losses = 0
            try:
                if int(self.d_max_consec_losses) > 0 and int(self.d_cooldown_bars) > 0 and self._consec_losses >= int(self.d_max_consec_losses):
                    self._cooldown_left = int(self.d_cooldown_bars)
                    self._consec_losses = 0
            except Exception:
                pass
            try:
                ts = pd.Timestamp(getattr(trade, 'exit_time', pd.Timestamp.utcnow()))
            except Exception:
                ts = pd.Timestamp.utcnow()
            mk = ts.strftime('%Y-%m')
            st = self._month_stats.get(mk, {'trades':0, 'gp':0.0, 'gl':0.0})
            st['trades'] += 1
            if pnl >= 0:
                st['gp'] += pnl
            else:
                st['gl'] += pnl
            self._month_stats[mk] = st
            try:
                if float(self.d_kill_month_pf) > 0 and int(self.d_kill_month_min_trades) > 0:
                    if st['trades'] >= int(self.d_kill_month_min_trades):
                        gp = float(st['gp']); gl = float(st['gl'])
                        pf = gp / abs(gl) if gl < 0 else float('inf')
                        if pf < float(self.d_kill_month_pf):
                            self._month_blocked.add(mk)
            except Exception:
                pass
        except Exception:
            pass
# ------------------------------- CLI Раннер ---------------------------------

def _ohlc_to_bt_df(ohlc: pd.DataFrame) -> pd.DataFrame:
    # backtesting.py ожидает столбцы с заглавной буквы: Open, High, Low, Close, Volume
    cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    df = ohlc.copy()
    df = df[cols]
    return df

def _cost_percent_from_pips(symbol: str, pips_total: float, ref_price: float) -> float:
    # процент от цены (доля), которую ждёт Backtest(spread=...)
    return (pip_size(symbol) * pips_total) / float(ref_price)

@click.command()
@click.option('--data-root', type=click.Path(file_okay=False), default='data', show_default=True)
@click.option('--symbol', type=str, default='EURUSD', show_default=True)
@click.option('--timeframe', type=click.Choice(['M1', 'M5', 'M15', 'M30', 'H1']), default='M15', show_default=True)
@click.option('--start', type=str, default=None, help='YYYY-MM-DD')
@click.option('--end', type=str, default=None, help='YYYY-MM-DD')
@click.option('--strategy', type=click.Choice(['A', 'B', 'C', 'D', 'ALL']), default='ALL', show_default=True)
@click.option('--spread-pips', type=float, default=0.8, show_default=True)
@click.option('--slippage-pips', type=float, default=0.2, show_default=True)
@click.option('--commission-bps', type=float, default=0.0, show_default=True, help='Комиссия в б.п. (basis points) на вход и выход, передаётся в Backtest(commission=...) как доля: bps/10000')
@click.option('--cash', type=float, default=10_000, show_default=True)
@click.option('--risk-pct', type=float, default=0.01, show_default=True, help='Доля депозита на риск в одной сделке, напр. 0.01 = 1%')
@click.option('--fixed-size', type=float, default=None, help='Фиксированный размер позиции (юнитов). Если задан, перекрывает risk-pct')
@click.option('--rsi-len', type=int, default=14, show_default=True, help='Strategy A: длина RSI')
@click.option('--rsi-os', type=float, default=30.0, show_default=True, help='Strategy A: уровень перепроданности')
@click.option('--rsi-ob', type=float, default=70.0, show_default=True, help='Strategy A: уровень перекупленности')
@click.option('--bb-len', type=int, default=20, show_default=True, help='Strategy A: длина Bollinger')
@click.option('--bb-std', type=float, default=2.0, show_default=True, help='Strategy A: std Bollinger')
@click.option('--rr-tp', type=float, default=3.0, show_default=True, help='RR множитель для TP (на всех стратегиях)')
@click.option('--atr-mult-sl', type=float, default=1.0, show_default=True, help='ATR-множитель для SL (на всех стратегиях)')
@click.option('--rolling-24m', is_flag=True, default=False, help='Отчёт по месяцам за последние 24 месяца для стратегии A')
@click.option('--rolling-out', type=str, default='out/rolling_A_24m_{tag}.csv', show_default=True, help='Путь для CSV роллинга Strategy A; поддерживает плейсхолдер {tag}')
@click.option('--rolling-save-current', is_flag=True, default=False, help='Также сохранить копию rolling_A_24m.csv в корне проекта (для обратной совместимости)')
@click.option('--cache-resampled', is_flag=True, default=False, help='Кешировать ресемплированный таймфрейм (ускорение повторных прогонов)')
@click.option('--a-atr-min', type=float, default=0.0, show_default=True, help='Strategy A: минимальный ATR для входа (в ценовых единицах)')
@click.option('--a-edge-mult', type=float, default=0.0, show_default=True, help='Strategy A: мин. расстояние до полосы Боллинджера в мультипликаторах ATR')
@click.option('--a-session-start', type=int, default=None, help='Strategy A: начальный час сессии (UTC)')
@click.option('--a-session-end', type=int, default=None, help='Strategy A: конечный час сессии (UTC)')
@click.option('--a-bb-width-min', type=float, default=0.0, show_default=True, help='Strategy A: мин. относительная ширина полос Боллинджера ( (bbu-bbl)/Close )')
@click.option('--a-adx-min', type=float, default=0.0, show_default=True, help='Strategy A: мин. ADX')
@click.option('--a-adx-len', type=int, default=14, show_default=True, help='Strategy A: длина окна ADX')
@click.option('--a-mid-slope-min', type=float, default=0.0, show_default=True, help='Strategy A: мин. относительный наклон средней полосы (|Δbbm|/(Close*L))')
@click.option('--a-mid-slope-len', type=int, default=10, show_default=True, help='Strategy A: окно для оценки наклона средней полосы')
@click.option('--a-dow-include', type=str, default=None, help='Strategy A: разрешённые дни недели, напр. "Tue,Wed,Thu"')
@click.option('--a-kill-month-pf', type=float, default=0.0, show_default=True, help='Strategy A: kill‑switch — порог PF для блока месяца (после мин. числа сделок)')
@click.option('--a-kill-month-min-trades', type=int, default=0, show_default=True, help='Strategy A: kill‑switch — минимум сделок в месяце перед проверкой порога PF')
@click.option('--a-max-consec-losses', type=int, default=0, show_default=True, help='Strategy A: максимум подряд убыточных сделок перед паузой')
@click.option('--a-cooldown-bars', type=int, default=0, show_default=True, help='Strategy A: длительность паузы (в барах) после серии убыточных')
@click.option('--a-be-trail-r', type=float, default=0.0, show_default=True, help='Strategy A: BE‑трейл — перевод в безубыток при движении >= R (R в SL-единицах)')
@click.option('--a-router-prev-m', type=int, default=0, show_default=True, help='Strategy A: маршрутизатор месяцев — смотреть N предыдущих месяцев; 0=выкл')
@click.option('--a-router-prev-pf-thr', type=float, default=0.0, show_default=True, help='Strategy A: порог PF агрегата N пред. месяцев для блокировки следующего месяца')
@click.option('--a-router-min-trades', type=int, default=0, show_default=True, help='Strategy A: мин. число сделок за N пред. месяцев для активации маршрутизатора')
@click.option('--d-len', type=int, default=40, show_default=True, help='Strategy D: длина канала Дончиана')
@click.option('--d-buffer-atr', type=float, default=0.5, show_default=True, help='Strategy D: буфер на вход (в ATR) поверх/ниже канала')
@click.option('--d-trail-mult', type=float, default=2.0, show_default=True, help='Strategy D: трейлинг-стоп (множитель ATR); 0 = без трейлинга')
@click.option('--d-adx-min', type=float, default=12.0, show_default=True, help='Strategy D: мин. ADX для фильтра тренда')
@click.option('--d-adx-len', type=int, default=14, show_default=True, help='Strategy D: длина окна ADX')
@click.option('--d-session-start', type=int, default=None, help='Strategy D: начальный час сессии (UTC)')
@click.option('--d-session-end', type=int, default=None, help='Strategy D: конечный час сессии (UTC)')
@click.option('--d-dow-include', type=str, default=None, help='Strategy D: разрешённые дни недели, напр. "Tue,Wed,Thu"')
@click.option('--d-ema-len', type=int, default=0, show_default=True, help='Strategy D: длина EMA для тренд‑фильтра (0 = выкл)')
@click.option('--d-ema-trend-only', is_flag=True, default=False, help='Strategy D: входы только по направлению EMA (long выше EMA, short ниже EMA)')
@click.option('--d-kill-month-pf', type=float, default=0.0, show_default=True, help='Strategy D: kill‑switch — порог PF для блока месяца (после минимум сделок)')
@click.option('--d-kill-month-min-trades', type=int, default=0, show_default=True, help='Strategy D: минимум сделок в месяце перед проверкой порога PF')
@click.option('--d-max-consec-losses', type=int, default=0, show_default=True, help='Strategy D: максимум подряд убыточных сделок перед паузой')
@click.option('--d-cooldown-bars', type=int, default=0, show_default=True, help='Strategy D: длительность паузы (в барах) после серии убыточных')
@click.option('--export-trades', type=str, default=None, help='Путь для экспорта трейдов CSV; можно использовать {key} для имени стратегии')
@click.option('--export-equity', type=str, default=None, help='Путь для экспорта кривой капитала CSV; можно использовать {key}')
@click.option('--export-signals', type=str, default=None, help='Путь для экспорта сигналов (CSV/JSON); можно использовать {key}')
@click.option('--save-run', type=str, default=None, help='Сохранить конфиг запуска и сводные метрики в JSON; можно использовать {key} при strategy!=ALL')
@click.option('--tune-a', is_flag=True, default=False, help='Мини-грид подбор параметров Strategy A (train/OOS)')
@click.option('--tune-save', type=str, default='tune_A_results.csv', show_default=True, help='CSV с результатами подбора')
@click.option('--tune-train-start', type=str, default=None, help='Train start YYYY-MM-DD')
@click.option('--tune-train-end', type=str, default=None, help='Train end YYYY-MM-DD')
@click.option('--tune-oos-start', type=str, default=None, help='OOS start YYYY-MM-DD')
@click.option('--tune-oos-end', type=str, default=None, help='OOS end YYYY-MM-DD')
@click.option('--tune-grid', type=click.Choice(['mini', 'expanded']), default='mini', show_default=True, help='Тип сетки параметров для --tune-a')
@click.option('--session-spread', type=str, default=None, help='Сессионные множители спреда: "asia=1.2,london=1.0,ny=1.1" (используется как усреднённый множитель)')
@click.option('--mc-slip-std-pips', type=float, default=0.0, show_default=True, help='Стд. отклонение дополнительного слиппеджа (пипсы) для Монте‑Карло; на каждый прогон добавляется |N(0,σ)| пипсов к спреду')
@click.option('--mc-runs', type=int, default=0, show_default=True, help='Число Монте‑Карло прогонов (если >0, запускается серия прогонов вместо обычного)')
@click.option('--matrix-costs', is_flag=True, default=False, help='Запустить стресс‑матрицу издержек: множители (x1,x2) для spread+slippage и комиссии (0,10 б.п.)')
@click.option('--matrix-save', type=str, default='matrix_results.csv', show_default=True, help='Куда сохранить CSV с результатами стресс‑матрицы')
@click.option('--rolling-exclude-partial', is_flag=True, default=False, help='Исключать неполный текущий месяц из роллинга 24м (для честного pf_min)')
@click.option('--plot', is_flag=True, default=False, help='Показать график результата')
def cli(data_root: str, symbol: str, timeframe: str,
        start: Optional[str], end: Optional[str], strategy: str,
        spread_pips: float, slippage_pips: float, cash: float,
        commission_bps: float,
        risk_pct: float, fixed_size: Optional[float],
        rsi_len: int, rsi_os: float, rsi_ob: float, bb_len: int, bb_std: float,
        rr_tp: float, atr_mult_sl: float, rolling_24m: bool, rolling_out: str, rolling_save_current: bool,
        cache_resampled: bool,
        a_atr_min: float, a_edge_mult: float, a_session_start: Optional[int], a_session_end: Optional[int],
        a_bb_width_min: float, a_adx_min: float, a_adx_len: int,
        a_mid_slope_min: float, a_mid_slope_len: int,
        a_dow_include: Optional[str],
        a_kill_month_pf: float, a_kill_month_min_trades: int,
        a_max_consec_losses: int, a_cooldown_bars: int, a_be_trail_r: float,
        a_router_prev_m: int, a_router_prev_pf_thr: float, a_router_min_trades: int,
        d_len: int, d_buffer_atr: float, d_trail_mult: float,
        d_adx_min: float, d_adx_len: int, d_session_start: Optional[int], d_session_end: Optional[int], d_dow_include: Optional[str],
        d_ema_len: int, d_ema_trend_only: bool,
        d_kill_month_pf: float, d_kill_month_min_trades: int, d_max_consec_losses: int, d_cooldown_bars: int,
        export_trades: Optional[str], export_equity: Optional[str], export_signals: Optional[str], save_run: Optional[str],
        tune_a: bool, tune_save: str, tune_train_start: Optional[str], tune_train_end: Optional[str],
        tune_oos_start: Optional[str], tune_oos_end: Optional[str], tune_grid: str,
        session_spread: Optional[str], mc_slip_std_pips: float, mc_runs: int,
        matrix_costs: bool, matrix_save: str,
        rolling_exclude_partial: bool, plot: bool):
    # 1) Загрузка данных и ресемплинг
    pack = load_ohlc(data_root, symbol=symbol, timeframe=timeframe, start=start, end=end, use_cache_resampled=cache_resampled)
    df = _ohlc_to_bt_df(pack.df)

    if len(df) < 300:
        print('[Ошибка] Недостаточно данных после ресемплинга (меньше 300 баров).')
        sys.exit(2)

    # 2) Конвертация издержек: spread + slippage (пипсы) -> доля цены
    ref_price = float(df['Close'].median())
    base_total_pips = float(spread_pips + slippage_pips)
    base_spread_fraction = _cost_percent_from_pips(symbol, base_total_pips, ref_price)

    # Усреднение по сессионным множителям (при необходимости)
    sess_mults = _parse_session_spread(session_spread)
    sess_weight = _weighted_session_multiplier(df.index, sess_mults)
    spread_fraction = base_spread_fraction * float(sess_weight)

    commission_fraction = float(commission_bps) / 10000.0

    print(
        f"[Инфо] Используем издержки: spread≈{spread_fraction:.6f} (доля цены)\n"
        f"       (пипсы: spread={spread_pips}, slippage={slippage_pips}, ref={ref_price:.5f})\n"
        f"       (сессионный множитель={sess_weight:.3f}; commission={commission_bps:.2f} bps→{commission_fraction:.5f})"
    )

    # Вспомогательная функция запуска одной конфигурации
    def _run_one(name: str, strat, params: Dict, df_in: Optional[pd.DataFrame] = None, do_plot: bool = True,
                 spread_override: Optional[float] = None, commission_override: Optional[float] = None):
        local_df = df if df_in is None else df_in
        # Очистим буфер сигналов класса перед запуском
        try:
            setattr(strat, 'emitted_signals', [])
        except Exception:
            pass
        eff_spread = spread_fraction if spread_override is None else float(spread_override)
        eff_comm = commission_fraction if commission_override is None else float(commission_override)
        bt = Backtest(local_df, strat, cash=cash, spread=eff_spread,
                      commission=eff_comm, margin=1.0, trade_on_close=False,
                      hedging=False, exclusive_orders=True, finalize_trades=True)
        stats = bt.run(**params)
        if do_plot and plot and (local_df is df):
            bt.plot(open_browser=False, filename=f"bt_{name}.html")
        # Экспорт артефактов по запросу
        def _format_path(base: Optional[str], key: str) -> Optional[str]:
            if not base:
                return None
            if '{key}' in base:
                return base.format(key=key)
            root, ext = os.path.splitext(base)
            return f"{root}_{key}{ext}"
        try:
            if export_trades:
                path = _format_path(export_trades, name)
                tr = getattr(stats, '_trades', None)
                if tr is not None and hasattr(tr, 'to_csv'):
                    dirn = os.path.dirname(path)
                    if dirn:
                        os.makedirs(dirn, exist_ok=True)
                    tr.to_csv(path, index=False)
            if export_equity:
                path = _format_path(export_equity, name)
                eq = getattr(stats, '_equity_curve', None)
                if eq is not None and hasattr(eq, 'to_csv'):
                    dirn = os.path.dirname(path)
                    if dirn:
                        os.makedirs(dirn, exist_ok=True)
                    eq.to_csv(path, index=False)
            if export_signals:
                path = _format_path(export_signals, name)
                # Читаем накопитель на уровне класса стратегии
                sigs = list(getattr(strat, 'emitted_signals', []) or [])
                if sigs:
                    df_s = pd.DataFrame(sigs)
                    # Приводим timestamp к ISO-8601 UTC и добавляем метаданные
                    df_s['timestamp'] = pd.to_datetime(df_s['timestamp'], utc=True, errors='coerce')
                    df_s = df_s.dropna(subset=['timestamp'])
                    df_s['timestamp'] = df_s['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                    df_s.insert(0, 'symbol', symbol)
                    df_s.insert(1, 'strategy', name)
                    dirn = os.path.dirname(path)
                    if dirn:
                        os.makedirs(dirn, exist_ok=True)
                    ext = os.path.splitext(path)[1].lower()
                    if ext == '.json':
                        with open(path, 'w', encoding='utf-8') as f:
                            json.dump(df_s.to_dict(orient='records'), f, ensure_ascii=False, indent=2)
                    else:
                        df_s.to_csv(path, index=False)
        except Exception as e:
            print(f"[warn] Экспорт артефактов для {name} не удался: {e}")
        return stats

    # 3) (Опционально) Мини-грид по Strategy A
    if tune_a:
        # диапазоны train/oos
        ts = pd.DatetimeIndex(df.index)
        df_train = df.copy()
        df_oos = None
        if tune_train_start or tune_train_end or tune_oos_start or tune_oos_end:
            if tune_train_start:
                tts = pd.to_datetime(tune_train_start, utc=True)
                df_train = df_train[df_train.index >= tts]
            if tune_train_end:
                tte = pd.to_datetime(tune_train_end, utc=True)
                df_train = df_train[df_train.index <= tte]
            if tune_oos_start or tune_oos_end:
                df_oos = df.copy()
                if tune_oos_start:
                    oos_s = pd.to_datetime(tune_oos_start, utc=True)
                    df_oos = df_oos[df_oos.index >= oos_s]
                if tune_oos_end:
                    oos_e = pd.to_datetime(tune_oos_end, utc=True)
                    df_oos = df_oos[df_oos.index <= oos_e]
        else:
            # 70/30 split по времени
            split_i = int(len(df) * 0.7)
            if split_i < 100:
                split_i = len(df) // 2
            ts_sorted = ts.sort_values()
            split_ts = ts_sorted[split_i]
            df_train = df[df.index <= split_ts]
            df_oos = df[df.index > split_ts]

        def metrics(s: pd.Series) -> Dict[str, float]:
            return {
                'trades': float(s.get('# Trades', np.nan)),
                'pf': float(s.get('Profit Factor', np.nan)),
                'wr': float(s.get('Win Rate [%]', np.nan)),
                'ret': float(s.get('Return [%]', np.nan)),
                'dd': float(s.get('Max. Drawdown [%]', np.nan)),
                'sharpe': float(s.get('Sharpe Ratio', np.nan)),
            }

        # сетка параметров
        rows = []
        if tune_grid == 'expanded':
            rsi_len_list = list(range(10, 25, 2))  # 10,12,...,24
            bb_std_list = [1.8, 2.0, 2.2, 2.4]
            rsi_levels = [(25.0, 75.0), (30.0, 70.0)]
            rr_tp_list = [1.5, 1.8, 2.0]
            atr_mult_sl_list = [atr_mult_sl]  # фиксируем из CLI
            risk_pct_list = [risk_pct]        # фиксируем из CLI
            a_atr_min_list = [0.0005, 0.0007, 0.0010]
            a_edge_mult_list = [0.5, 0.75, 1.0]
            session_pairs = [(7, 18), (8, 17)]  # London окна
            combos = list(itertools.product(
                rsi_len_list, bb_std_list, rsi_levels, rr_tp_list, atr_mult_sl_list, risk_pct_list,
                a_atr_min_list, a_edge_mult_list, session_pairs
            ))
            print(f"[Инфо] Запуск расширенного подбора Strategy A: {len(combos)} комбинаций, train={len(df_train)} баров, oos={len(df_oos) if df_oos is not None else 0}")
            for rsi_len_g, bb_std_g, rsi_pair, rr_tp_g, atr_mult_sl_g, risk_pct_g, a_atr_min_g, a_edge_mult_g, sess_pair in combos:
                rsi_os_g, rsi_ob_g = rsi_pair
                sess_start_g, sess_end_g = sess_pair
                params_train = dict(rr_tp=rr_tp_g, atr_mult_sl=atr_mult_sl_g,
                                    risk_pct=risk_pct_g, fixed_size=fixed_size,
                                    rsi_len=rsi_len_g, rsi_os=rsi_os_g, rsi_ob=rsi_ob_g,
                                    bb_len=bb_len, bb_std=bb_std_g,
                                    a_atr_min=a_atr_min_g, a_edge_mult=a_edge_mult_g,
                                    a_session_start=sess_start_g, a_session_end=sess_end_g)
                s_tr = _run_one('A_train', StrategyA_BBRSI_RR3, params_train, df_in=df_train, do_plot=False)
                m_tr = metrics(s_tr)
                m_oos = {'trades': np.nan, 'pf': np.nan, 'wr': np.nan, 'ret': np.nan, 'dd': np.nan, 'sharpe': np.nan}
                if df_oos is not None and len(df_oos) >= 100:
                    s_oos = _run_one('A_oos', StrategyA_BBRSI_RR3, params_train, df_in=df_oos, do_plot=False)
                    m_oos = metrics(s_oos)
                rows.append({
                    'rsi_len': rsi_len_g, 'bb_std': bb_std_g, 'rsi_os': rsi_os_g, 'rsi_ob': rsi_ob_g,
                    'rr_tp': rr_tp_g, 'atr_mult_sl': atr_mult_sl_g, 'risk_pct': risk_pct_g,
                    'a_atr_min': a_atr_min_g, 'a_edge_mult': a_edge_mult_g,
                    'a_session_start': sess_start_g, 'a_session_end': sess_end_g,
                    **{f'train_{k}': v for k, v in m_tr.items()},
                    **{f'oos_{k}': v for k, v in m_oos.items()},
                })
        else:
            grid = {
                'rsi_len': [10, 14, 18],
                'bb_std': [1.8, 2.0, 2.2],
                'atr_mult_sl': [0.8, 1.0, 1.2],
                'risk_pct': [0.005, 0.01, 0.02],
            }
            combos = list(itertools.product(grid['rsi_len'], grid['bb_std'], grid['atr_mult_sl'], grid['risk_pct']))
            print(f"[Инфо] Запуск подбора Strategy A: {len(combos)} комбинаций, train={len(df_train)} баров, oos={len(df_oos) if df_oos is not None else 0}")
            for rsi_len_g, bb_std_g, atr_mult_sl_g, risk_pct_g in combos:
                params_train = dict(rr_tp=rr_tp, atr_mult_sl=atr_mult_sl_g,
                                    risk_pct=risk_pct_g, fixed_size=fixed_size,
                                    rsi_len=rsi_len_g, rsi_os=rsi_os, rsi_ob=rsi_ob,
                                    bb_len=bb_len, bb_std=bb_std_g,
                                    a_atr_min=a_atr_min, a_edge_mult=a_edge_mult,
                                    a_session_start=a_session_start, a_session_end=a_session_end)
                s_tr = _run_one('A_train', StrategyA_BBRSI_RR3, params_train, df_in=df_train, do_plot=False)
                m_tr = metrics(s_tr)
                m_oos = {'trades': np.nan, 'pf': np.nan, 'wr': np.nan, 'ret': np.nan, 'dd': np.nan, 'sharpe': np.nan}
                if df_oos is not None and len(df_oos) >= 100:
                    s_oos = _run_one('A_oos', StrategyA_BBRSI_RR3, params_train, df_in=df_oos, do_plot=False)
                    m_oos = metrics(s_oos)
                rows.append({
                    'rsi_len': rsi_len_g, 'bb_std': bb_std_g, 'atr_mult_sl': atr_mult_sl_g, 'risk_pct': risk_pct_g,
                    **{f'train_{k}': v for k, v in m_tr.items()},
                    **{f'oos_{k}': v for k, v in m_oos.items()},
                })

        res_df = pd.DataFrame(rows)
        # Сортировка по OOS PF убыв., затем по OOS DD возр., затем по OOS WR убыв.
        if not res_df.empty and 'oos_pf' in res_df.columns:
            res_df = res_df.sort_values(by=['oos_pf', 'oos_dd', 'oos_wr'], ascending=[False, True, False])
        try:
            res_df.to_csv(tune_save, index=False)
            print(f"[Инфо] Результаты подбора сохранены: {tune_save}")
            if not res_df.empty:
                print("Top-5 по OOS PF:")
                print(res_df.head(5))
        except Exception as e:
            print(f"[warn] Не удалось сохранить результаты подбора: {e}")
        return

    # 3b) (Опционально) Стресс-матрица издержек
    if matrix_costs:
        print("[Инфо] Запуск стресс‑матрицы издержек ...")
        # Комбинации множителей для пипсов и комиссий (в б.п.)
        pips_mults = [1.0, 2.0]
        comm_bps_list = [0.0, 10.0]
        rows = []
        def metrics(s: pd.Series) -> Dict[str, float]:
            return {
                'trades': float(s.get('# Trades', np.nan)),
                'pf': float(s.get('Profit Factor', np.nan)),
                'wr': float(s.get('Win Rate [%]', np.nan)),
                'ret': float(s.get('Return [%]', np.nan)),
                'dd': float(s.get('Max. Drawdown [%]', np.nan)),
                'sharpe': float(s.get('Sharpe Ratio', np.nan)),
            }
        common_params = dict(rr_tp=rr_tp, atr_mult_sl=atr_mult_sl,
                             risk_pct=risk_pct, fixed_size=fixed_size)
        params_a = dict(common_params, rsi_len=rsi_len, rsi_os=rsi_os, rsi_ob=rsi_ob,
                        bb_len=bb_len, bb_std=bb_std,
                        a_atr_min=a_atr_min, a_edge_mult=a_edge_mult,
                        a_session_start=a_session_start, a_session_end=a_session_end)
        for pm in pips_mults:
            for cbps in comm_bps_list:
                scen_name = f"pm{pm}_c{int(cbps)}bps"
                scen_spread = _cost_percent_from_pips(symbol, base_total_pips * pm, ref_price) * sess_weight
                scen_comm = float(cbps) / 10000.0
                print(f"  [Сценарий] {scen_name}: spread≈{scen_spread:.6f}, commission={scen_comm:.5f}")
                if strategy in ('A', 'ALL'):
                    s = _run_one(f"A_{scen_name}", StrategyA_BBRSI_RR3, params_a,
                                 spread_override=scen_spread, commission_override=scen_comm, do_plot=False)
                    m = metrics(s)
                    rows.append({'scenario': scen_name, 'strategy': 'A', **m})
                if strategy in ('C', 'ALL'):
                    s = _run_one(f"C_{scen_name}", StrategyC_EMAPullback_RR3, common_params,
                                 spread_override=scen_spread, commission_override=scen_comm, do_plot=False)
                    m = metrics(s)
                    rows.append({'scenario': scen_name, 'strategy': 'C', **m})
                if strategy in ('B', 'ALL'):
                    s = _run_one(f"B_{scen_name}", StrategyB_AsiaFade_RR3, common_params,
                                 spread_override=scen_spread, commission_override=scen_comm, do_plot=False)
                    m = metrics(s)
                    rows.append({'scenario': scen_name, 'strategy': 'B', **m})
                if strategy in ('D', 'ALL'):
                    params_d = dict(common_params,
                                    d_len=d_len, d_buffer_atr=d_buffer_atr, d_trail_mult=d_trail_mult,
                                    d_adx_min=d_adx_min, d_adx_len=d_adx_len,
                                    d_session_start=d_session_start, d_session_end=d_session_end,
                                    d_dow_include=d_dow_include,
                                    d_ema_len=d_ema_len, d_ema_trend_only=d_ema_trend_only,
                                    d_kill_month_pf=d_kill_month_pf, d_kill_month_min_trades=d_kill_month_min_trades,
                                    d_max_consec_losses=d_max_consec_losses, d_cooldown_bars=d_cooldown_bars)
                    s = _run_one(f"D_{scen_name}", StrategyD_DonchianBreakout, params_d,
                                 spread_override=scen_spread, commission_override=scen_comm, do_plot=False)
                    m = metrics(s)
                    rows.append({'scenario': scen_name, 'strategy': 'D', **m})
        mat_df = pd.DataFrame(rows)
        try:
            mat_df.to_csv(matrix_save, index=False)
            print(f"[Инфо] Результаты матрицы сохранены: {matrix_save}")
        except Exception as e:
            print(f"[warn] Не удалось сохранить матрицу: {e}")
        # Если задана матрица, завершаем выполнение после неё
        if mc_runs <= 0:
            return

    # 3c) (Опционально) Монте‑Карло по слиппеджу
    if mc_runs and int(mc_runs) > 0 and float(mc_slip_std_pips) > 0:
        print(f"[Инфо] Монте‑Карло: {mc_runs} прогонов, σ_slip={mc_slip_std_pips} пипса")
        rows = []
        rng = np.random.default_rng()
        def metrics(s: pd.Series) -> Dict[str, float]:
            return {
                'trades': float(s.get('# Trades', np.nan)),
                'pf': float(s.get('Profit Factor', np.nan)),
                'wr': float(s.get('Win Rate [%]', np.nan)),
                'ret': float(s.get('Return [%]', np.nan)),
                'dd': float(s.get('Max. Drawdown [%]', np.nan)),
                'sharpe': float(s.get('Sharpe Ratio', np.nan)),
            }
        common_params = dict(rr_tp=rr_tp, atr_mult_sl=atr_mult_sl,
                             risk_pct=risk_pct, fixed_size=fixed_size)
        params_a = dict(common_params, rsi_len=rsi_len, rsi_os=rsi_os, rsi_ob=rsi_ob,
                        bb_len=bb_len, bb_std=bb_std,
                        a_atr_min=a_atr_min, a_edge_mult=a_edge_mult,
                        a_session_start=a_session_start, a_session_end=a_session_end)
        for i_run in range(int(mc_runs)):
            extra = float(abs(rng.normal(loc=0.0, scale=float(mc_slip_std_pips))))
            scen_spread = _cost_percent_from_pips(symbol, base_total_pips + extra, ref_price) * sess_weight
            scen_name = f"mc_{i_run:03d}_extra{extra:.3f}p"
            if strategy in ('A', 'ALL'):
                s = _run_one(f"A_{scen_name}", StrategyA_BBRSI_RR3, params_a,
                             spread_override=scen_spread, commission_override=commission_fraction, do_plot=False)
                rows.append({'scenario': scen_name, 'strategy': 'A', **metrics(s)})
            if strategy in ('C', 'ALL'):
                s = _run_one(f"C_{scen_name}", StrategyC_EMAPullback_RR3, common_params,
                             spread_override=scen_spread, commission_override=commission_fraction, do_plot=False)
                rows.append({'scenario': scen_name, 'strategy': 'C', **metrics(s)})
            if strategy in ('B', 'ALL'):
                s = _run_one(f"B_{scen_name}", StrategyB_AsiaFade_RR3, common_params,
                             spread_override=scen_spread, commission_override=commission_fraction, do_plot=False)
                rows.append({'scenario': scen_name, 'strategy': 'B', **metrics(s)})
            if strategy in ('D', 'ALL'):
                params_d = dict(common_params,
                                d_len=d_len, d_buffer_atr=d_buffer_atr, d_trail_mult=d_trail_mult,
                                d_adx_min=d_adx_min, d_adx_len=d_adx_len,
                                d_session_start=d_session_start, d_session_end=d_session_end,
                                d_dow_include=d_dow_include,
                                d_ema_len=d_ema_len, d_ema_trend_only=d_ema_trend_only,
                                d_kill_month_pf=d_kill_month_pf, d_kill_month_min_trades=d_kill_month_min_trades,
                                d_max_consec_losses=d_max_consec_losses, d_cooldown_bars=d_cooldown_bars)
                s = _run_one(f"D_{scen_name}", StrategyD_DonchianBreakout, params_d,
                             spread_override=scen_spread, commission_override=commission_fraction, do_plot=False)
                rows.append({'scenario': scen_name, 'strategy': 'D', **metrics(s)})
        mc_df = pd.DataFrame(rows)
        out_path = 'mc_slippage_results.csv'
        try:
            mc_df.to_csv(out_path, index=False)
            print(f"[Инфо] Результаты Монте‑Карло сохранены: {out_path}")
        except Exception as e:
            print(f"[warn] Не удалось сохранить Монте‑Карло: {e}")
        return

    # 4) Выбор стратегии(ий)
    runs: Dict[str, pd.Series] = {}
    common_params = dict(rr_tp=rr_tp, atr_mult_sl=atr_mult_sl,
                         risk_pct=risk_pct, fixed_size=fixed_size)
    params_a = dict(common_params, rsi_len=rsi_len, rsi_os=rsi_os, rsi_ob=rsi_ob,
                    bb_len=bb_len, bb_std=bb_std,
                    a_atr_min=a_atr_min, a_edge_mult=a_edge_mult,
                    a_session_start=a_session_start, a_session_end=a_session_end,
                    a_bb_width_min=a_bb_width_min,
                    a_adx_min=a_adx_min, a_adx_len=a_adx_len,
                    a_mid_slope_min=a_mid_slope_min, a_mid_slope_len=a_mid_slope_len,
                    a_dow_include=a_dow_include,
                    a_kill_month_pf=a_kill_month_pf, a_kill_month_min_trades=a_kill_month_min_trades,
                    a_max_consec_losses=a_max_consec_losses, a_cooldown_bars=a_cooldown_bars,
                    a_be_trail_r=a_be_trail_r,
                    a_router_prev_m=a_router_prev_m, a_router_prev_pf_thr=a_router_prev_pf_thr,
                    a_router_min_trades=a_router_min_trades)


    def _print_subset(name: str, s: pd.Series):
        wanted = ['# Trades', 'Win Rate [%]', 'Return [%]', 'Return (Ann.) [%]',
                  'Max. Drawdown [%]', 'Sharpe Ratio', 'Profit Factor',
                  'SQN', 'Expectancy', 'Expectancy [R]']
        available = [k for k in wanted if k in s.index]
        print(f"\n=== {name} ===")
        print(s[available])

    if strategy in ('A', 'ALL'):
        stats_a = _run_one('A', StrategyA_BBRSI_RR3, params_a)
        runs['A'] = stats_a
        _print_subset('Стратегия A (Bollinger+RSI, RR 1:3)', stats_a)
        if rolling_24m:
            idx = pd.DatetimeIndex(df.index)
            # Приведём индекс к tz-naive, чтобы избежать предупреждений при to_period
            if getattr(idx, 'tz', None) is not None:
                idx = idx.tz_convert(None)
            periods = idx.to_period('M')
            months = periods.unique()
            # Исключить текущий неполный месяц при необходимости
            if rolling_exclude_partial:
                try:
                    now_m = pd.Timestamp.utcnow().to_period('M')
                    months = [m for m in months if m != now_m]
                except Exception:
                    pass
            # Отсортируем по времени и возьмём последние 24
            months = list(months)
            months.sort()
            months = months[-24:] if len(months) > 24 else months
            rows = []
            # Параметры маршрутизатора для логики роллинга
            r_prev_m = a_router_prev_m
            r_thr = a_router_prev_pf_thr
            r_mintr = a_router_min_trades
            for m in months:
                mask = (periods == m)
                df_m = df.loc[mask]
                if len(df_m) < 10:
                    continue
                # Router: если предыдущие N месяцев «горькие», пропускаем месяц m
                try:
                    if int(r_prev_m) > 0 and float(r_thr) > 0:
                        if len(rows) >= int(r_prev_m):
                            prev = rows[-int(r_prev_m):]
                            trades_total = int(sum(r.get('trades', 0) for r in prev))
                            if int(r_mintr) == 0 or trades_total >= int(r_mintr):
                                gp_tot = float(sum(r.get('gp', 0.0) for r in prev))
                                gl_tot = float(sum(r.get('gl', 0.0) for r in prev))
                                pf_prev = (gp_tot / abs(gl_tot)) if gl_tot < 0 else float('inf')
                                if pf_prev < float(r_thr):
                                    rows.append(dict(
                                        month=str(m), trades=0,
                                        pf=float('nan'), winrate=float('nan'), dd=float('nan'),
                                        gp=0.0, gl=0.0,
                                    ))
                                    pf_str = "nan"; wr_str = "nan"; dd_str = "nan"
                                    print(f"{m}: PF={pf_str}, WinRate={wr_str}%, DD={dd_str}%, trades=0 [router]")
                                    continue
                except Exception:
                    pass
                s_m = _run_one(f'A_{m}', StrategyA_BBRSI_RR3, params_a, df_in=df_m, do_plot=False)
                pf = s_m.get('Profit Factor', np.nan)
                wr = s_m.get('Win Rate [%]', np.nan)
                dd = s_m.get('Max. Drawdown [%]', np.nan)
                trades = s_m.get('# Trades', np.nan)
                # gp/gl из журнала сделок
                gp = np.nan; gl = np.nan
                try:
                    tr = getattr(s_m, '_trades', None)
                    if tr is not None and len(tr) > 0 and 'PnL' in tr.columns:
                        pnl = tr['PnL'].astype(float)
                        gp = float(pnl[pnl > 0].sum())
                        gl = float(pnl[pnl < 0].sum())
                except Exception:
                    pass
                rows.append(dict(
                    month=str(m),
                    trades=int(trades) if pd.notnull(trades) else 0,
                    pf=float(pf) if pd.notnull(pf) else np.nan,
                    winrate=float(wr) if pd.notnull(wr) else np.nan,
                    dd=float(dd) if pd.notnull(dd) else np.nan,
                    gp=gp, gl=gl,
                ))
            if rows:
                roll_df = pd.DataFrame(rows)
                print("\n=== Стратегия A: скользящие месяцы (последние 24м) ===")
                for r in rows:
                    pf = r['pf']; wr = r['winrate']; dd = r['dd']; tr = r['trades']
                    pf_str = f"{pf:.2f}" if np.isfinite(pf) else "nan"
                    wr_str = f"{wr:.1f}" if np.isfinite(wr) else "nan"
                    dd_str = f"{dd:.1f}" if np.isfinite(dd) else "nan"
                    print(f"{r['month']}: PF={pf_str}, WinRate={wr_str}%, DD={dd_str}%, trades={tr}")
                try:
                    # Построить тег конфигурации для имени файла
                    def _fmt(x: float, dec: int = 2) -> str:
                        s = f"{float(x):.{dec}f}".rstrip('0').rstrip('.')
                        return s if s else "0"
                    risk_pct_pct = float(risk_pct) * 100.0
                    risk_str = f"{risk_pct_pct:.2f}".rstrip('0').rstrip('.')
                    parts = [
                        f"rsi{rsi_len}",
                        f"bb{bb_std:.1f}",
                        f"atr{atr_mult_sl:.1f}",
                        f"risk{risk_str}",
                    ]
                    try:
                        if float(rr_tp) != 3.0:
                            parts.append(f"rr{rr_tp:.1f}")
                    except Exception:
                        pass
                    try:
                        if a_session_start is not None and a_session_end is not None:
                            parts.append(f"london{int(a_session_start)}-{int(a_session_end)}")
                    except Exception:
                        pass
                    try:
                        if float(a_atr_min) > 0:
                            parts.append(f"atrmin{float(a_atr_min):.4f}")
                    except Exception:
                        pass
                    try:
                        if float(a_edge_mult) > 0:
                            parts.append(f"edge{_fmt(a_edge_mult, 2)}")
                    except Exception:
                        pass
                    tag = "_".join(parts)
                    # Определить путь сохранения (поддержка плейсхолдера {tag})
                    out_path = rolling_out.format(tag=tag) if '{tag}' in str(rolling_out) else str(rolling_out)
                    out_dir = os.path.dirname(out_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                    roll_df.to_csv(out_path, index=False)
                    print(f"[Инфо] Сохранено в {out_path} (tag={tag})")
                    if rolling_save_current:
                        roll_df.to_csv('rolling_A_24m.csv', index=False)
                        print("[Инфо] Также сохранено в rolling_A_24m.csv (current)")
                except Exception as e:
                    print(f"[warn] Не удалось сохранить CSV роллинга: {e}")

    if strategy in ('C', 'ALL'):
        stats_c = _run_one('C', StrategyC_EMAPullback_RR3, common_params)
        runs['C'] = stats_c
        _print_subset('Стратегия C (EMA pullback, RR 1:3)', stats_c)

    if strategy in ('B', 'ALL'):
        stats_b = _run_one('B', StrategyB_AsiaFade_RR3, common_params)
        runs['B'] = stats_b
        _print_subset('Стратегия B (Asia fade, RR 1:3)', stats_b)

    if strategy in ('D', 'ALL'):
        params_d = dict(common_params,
                        d_len=d_len, d_buffer_atr=d_buffer_atr, d_trail_mult=d_trail_mult,
                        d_adx_min=d_adx_min, d_adx_len=d_adx_len,
                        d_session_start=d_session_start, d_session_end=d_session_end,
                        d_dow_include=d_dow_include,
                        d_ema_len=d_ema_len, d_ema_trend_only=d_ema_trend_only,
                        d_kill_month_pf=d_kill_month_pf, d_kill_month_min_trades=d_kill_month_min_trades,
                        d_max_consec_losses=d_max_consec_losses, d_cooldown_bars=d_cooldown_bars)
        stats_d = _run_one('D', StrategyD_DonchianBreakout, params_d)
        runs['D'] = stats_d
        _print_subset('Стратегия D (Donchian breakout, RR 1:3 + ATR‑buffer)', stats_d)
        if rolling_24m:
            idx = pd.DatetimeIndex(df.index)
            if getattr(idx, 'tz', None) is not None:
                idx = idx.tz_convert(None)
            periods = idx.to_period('M')
            months = periods.unique()
            if rolling_exclude_partial:
                try:
                    now_m = pd.Timestamp.utcnow().to_period('M')
                    months = [m for m in months if m != now_m]
                except Exception:
                    pass
            months = months[-24:] if len(months) > 24 else months
            rows = []
            for m in months:
                mask = (periods == m)
                df_m = df.loc[mask]
                if len(df_m) < 10:
                    continue
                s_m = _run_one(f'D_{m}', StrategyD_DonchianBreakout, params_d, df_in=df_m, do_plot=False)
                pf = s_m.get('Profit Factor', np.nan)
                wr = s_m.get('Win Rate [%]', np.nan)
                dd = s_m.get('Max. Drawdown [%]', np.nan)
                trades = s_m.get('# Trades', np.nan)
                gp = np.nan; gl = np.nan
                try:
                    tr = getattr(s_m, '_trades', None)
                    if tr is not None and len(tr) > 0 and 'PnL' in tr.columns:
                        pnl = tr['PnL'].astype(float)
                        gp = float(pnl[pnl > 0].sum())
                        gl = float(pnl[pnl < 0].sum())
                except Exception:
                    pass
                rows.append(dict(
                    month=str(m),
                    trades=int(trades) if pd.notnull(trades) else 0,
                    pf=float(pf) if pd.notnull(pf) else np.nan,
                    winrate=float(wr) if pd.notnull(wr) else np.nan,
                    dd=float(dd) if pd.notnull(dd) else np.nan,
                    gp=gp, gl=gl,
                ))
            if rows:
                roll_df = pd.DataFrame(rows)
                print("\n=== Стратегия D: скользящие месяцы (последние 24м) ===")
                for r in rows:
                    pf = r['pf']; wr = r['winrate']; dd = r['dd']; tr = r['trades']
                    pf_str = f"{pf:.2f}" if np.isfinite(pf) else "nan"
                    wr_str = f"{wr:.1f}" if np.isfinite(wr) else "nan"
                    dd_str = f"{dd:.1f}" if np.isfinite(dd) else "nan"
                    print(f"{r['month']}: PF={pf_str}, WinRate={wr_str}%, DD={dd_str}%, trades={tr}")
                try:
                    def _fmt(x: float, dec: int = 2) -> str:
                        s = f"{float(x):.{dec}f}".rstrip('0').rstrip('.')
                        return s if s else "0"
                    risk_pct_pct = float(risk_pct) * 100.0
                    risk_str = f"{risk_pct_pct:.2f}".rstrip('0').rstrip('.')
                    parts = [
                        f"dc{int(d_len)}",
                        f"buf{_fmt(d_buffer_atr, 2)}",
                        f"atr{atr_mult_sl:.1f}",
                        f"risk{risk_str}",
                    ]
                    try:
                        if float(d_trail_mult) > 0:
                            parts.append(f"trail{_fmt(d_trail_mult, 2)}")
                    except Exception:
                        pass
                    try:
                        if d_session_start is not None and d_session_end is not None:
                            parts.append(f"london{int(d_session_start)}-{int(d_session_end)}")
                    except Exception:
                        pass
                    try:
                        if float(d_adx_min) > 0:
                            parts.append(f"adx{_fmt(d_adx_min, 2)}")
                    except Exception:
                        pass
                    try:
                        if int(d_ema_len) > 0:
                            parts.append(f"ema{int(d_ema_len)}")
                        if bool(d_ema_trend_only):
                            parts.append("trend")
                    except Exception:
                        pass
                    tag = "_".join(parts)
                    out_path = rolling_out.format(tag=tag) if '{tag}' in str(rolling_out) else str(rolling_out)
                    if 'rolling_A_24m' in out_path:
                        out_path = out_path.replace('rolling_A_24m', 'rolling_D_24m')
                    out_dir = os.path.dirname(out_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                    roll_df.to_csv(out_path, index=False)
                    print(f"[Инфо] Сохранено в {out_path} (tag={tag})")
                except Exception as e:
                    print(f"[warn] Не удалось сохранить CSV роллинга D: {e}")

    # 5) Короткий вывод победителя, если ALL
    if strategy == 'ALL' and runs:
        key = max(runs, key=lambda k: float(runs[k].get('Profit Factor', 0)))
        print(f"\n[Итог] Лучший PF у стратегии: {key} (PF={float(runs[key]['Profit Factor']):.3f})")

    # 6) Сохранение конфига запуска и сводных метрик
    if save_run:
        out = {
            'args': {
                'data_root': data_root, 'symbol': symbol, 'timeframe': timeframe,
                'start': start, 'end': end, 'strategy': strategy,
                'spread_pips': spread_pips, 'slippage_pips': slippage_pips,
                'cash': cash, 'risk_pct': risk_pct, 'fixed_size': fixed_size,
                'rsi_len': rsi_len, 'rsi_os': rsi_os, 'rsi_ob': rsi_ob,
                'bb_len': bb_len, 'bb_std': bb_std,
                'rr_tp': rr_tp, 'atr_mult_sl': atr_mult_sl,
                'rolling_24m': rolling_24m,
                'rolling_out': rolling_out, 'rolling_save_current': rolling_save_current,
                'rolling_exclude_partial': rolling_exclude_partial,
                'cache_resampled': cache_resampled,
                'a_atr_min': a_atr_min, 'a_edge_mult': a_edge_mult,
                'a_session_start': a_session_start, 'a_session_end': a_session_end,
                'a_router_prev_m': a_router_prev_m, 'a_router_prev_pf_thr': a_router_prev_pf_thr,
                'a_router_min_trades': a_router_min_trades,
                'commission_bps': commission_bps,
                'session_spread': session_spread,
                'mc_slip_std_pips': mc_slip_std_pips,
                'mc_runs': mc_runs,
                'matrix_costs': matrix_costs,
                'd_len': d_len, 'd_buffer_atr': d_buffer_atr, 'd_trail_mult': d_trail_mult,
                'd_adx_min': d_adx_min, 'd_adx_len': d_adx_len,
                'd_session_start': d_session_start, 'd_session_end': d_session_end,
                'd_dow_include': d_dow_include,
                'd_ema_len': d_ema_len, 'd_ema_trend_only': d_ema_trend_only,
                'd_kill_month_pf': d_kill_month_pf, 'd_kill_month_min_trades': d_kill_month_min_trades,
                'd_max_consec_losses': d_max_consec_losses, 'd_cooldown_bars': d_cooldown_bars,
            },
            'metrics': {},
            'env': {
                'python': sys.version.split()[0],
                'pandas': pd.__version__,
                'numpy': np.__version__,
                'backtesting': getattr(btlib, '__version__', 'unknown'),
                'timestamp_utc': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            }
        }
        for k, s in runs.items():
            out['metrics'][k] = {
                'trades': float(s.get('# Trades', np.nan)),
                'pf': float(s.get('Profit Factor', np.nan)),
                'wr': float(s.get('Win Rate [%]', np.nan)),
                'ret': float(s.get('Return [%]', np.nan)),
                'ann_ret': float(s.get('Return (Ann.) [%]', np.nan)),
                'dd': float(s.get('Max. Drawdown [%]', np.nan)),
                'sharpe': float(s.get('Sharpe Ratio', np.nan)),
            }
        try:
            # Если strategy != ALL и в пути нет {key}, добавим суффикс стратегии
            path = save_run
            if strategy != 'ALL' and '{key}' in path:
                path = path.format(key=strategy)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print(f"[Инфо] Конфиг запуска сохранён: {path}")
        except Exception as e:
            print(f"[warn] Не удалось сохранить конфиг запуска: {e}")

if __name__ == '__main__':
    cli()
