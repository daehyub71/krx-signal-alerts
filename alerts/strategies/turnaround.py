"""F9 — 장기 턴어라운드.

오래 눌려 있던 종목에 대량 거래가 들어오며 박스를 넘는 달.

**월봉 3년(37개) 제약의 직접적 대가**: 12개월 평균 거래량을 쓰면 판정 가능 구간이
19개월밖에 남지 않아, 원안의 "6~12개월 횡보"를 **6개월로 고정**했다 (SPEC R1).
신호가 드물게 나오는 것이 정상이다. 월 0건이 여러 달 이어져도 고장이 아니다.

**월이 닫힌 뒤에만 돈다.** 월중에는 미완성 월봉이라 거래량이 과소 집계된다.
"""

from __future__ import annotations

from datetime import date

from alerts.models import BarSet, Signal, StrategyName, TickerMeta
from alerts.schedule import month_closed
from alerts.strategies.base import Checks, make_signal, ratio, won

name: StrategyName = "turnaround"

BOX_MONTHS = 6  # 횡보 구간 (원안 6~12에서 좁힘 — R1)
AVG_MONTHS = 12  # 거래량·거래대금 평균 구간
BOX_MAX_RANGE = 0.30  # 박스 폭 상한 (평균 종가 대비)
SURGE_MULT = 3.0  # 거래량·거래대금 급증 배수

MIN_MONTHLY = AVG_MONTHS + BOX_MONTHS + 1


def runs_on(data_date: date, run_date: date) -> bool:
    """월이 닫힌 뒤에만 돈다."""
    return month_closed(data_date, run_date)


def evaluate(meta: TickerMeta, bars: BarSet) -> Signal | None:
    """한 종목을 판정한다.

    Returns:
        횡보 뒤 대량 거래로 박스를 넘은 달이면 `Signal`, 아니면 None.
    """
    if len(bars.monthly) < MIN_MONTHLY:
        return None

    last = bars.monthly[-1]
    box = bars.monthly[-BOX_MONTHS - 1 : -1]
    prior = bars.monthly[-AVG_MONTHS - 1 : -1]

    box_high = max(float(b.h) for b in box)
    box_low = min(float(b.low) for b in box)
    box_mean = sum(float(b.c) for b in box) / len(box)
    box_range = (box_high - box_low) / box_mean if box_mean else 1.0

    avg_v = sum(float(b.v) for b in prior) / len(prior)
    avg_a = sum(float(b.a or 0) for b in prior) / len(prior)
    v_mult = float(last.v) / avg_v if avg_v else 0.0
    a_mult = float(last.a or 0) / avg_a if avg_a else 0.0

    ck = Checks()
    ck.add(
        f"직전 {BOX_MONTHS}개월 횡보 (폭 {BOX_MAX_RANGE:.0%} 이내)",
        box_range <= BOX_MAX_RANGE,
        f"{box_range:.1%} ({won(box_low)} ~ {won(box_high)})",
    )
    ck.add(
        f"거래량 {SURGE_MULT:.0f}배 급증",
        v_mult >= SURGE_MULT,
        f"{ratio(v_mult)} ({AVG_MONTHS}개월 평균 대비)",
    )
    ck.add(
        f"거래대금 {SURGE_MULT:.0f}배 급증",
        a_mult >= SURGE_MULT,
        f"{ratio(a_mult)} (저가주 오탐 차단)",
    )
    ck.add(
        "종가가 박스 상단 돌파",
        float(last.c) > box_high,
        f"{won(last.c)} vs 상단 {won(box_high)}",
    )

    if not ck.all_ok:
        return None

    breakout = float(last.c) / box_high if box_high else 1.0
    score = v_mult * breakout

    return make_signal(meta, name, bars, score, ck)
