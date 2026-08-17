"""F6 — 주봉 추세 눌림목.

상승 추세 중 20주선까지 밀렸다가 아래꼬리를 달고 되돌린 주.

**주가 닫힌 뒤에만 돈다.** 진행 중인 주봉으로 판정하면 다음 날 뒤집힌다.
"금요일"이 아니라 "주가 바뀌었는가"로 보므로 금요일이 휴장인 주도 놓치지 않는다.
"""

from __future__ import annotations

from datetime import date

from alerts.indicators import sma
from alerts.models import BarSet, Signal, StrategyName, TickerMeta
from alerts.schedule import week_closed
from alerts.strategies.base import Checks, make_signal, ratio, won

name: StrategyName = "pullback"

FAST, SLOW = 20, 60
TREND_LOOKBACK = 4  # MA60이 오르고 있는지 볼 구간
# 부호만 보면 안 된다. 평평한 종목도 봉 하나에 MA60이 0.03% 오르며 '상승'으로 잡힌다
# (2026-08-17 테스트로 발견). 4주에 최소 0.5%는 올라야 추세로 인정한다.
TREND_MIN_SLOPE = 0.005
TOUCH_TOLERANCE = 1.02  # 저가가 MA20의 102% 이내까지 내려왔으면 '터치'
TAIL_MIN_RATIO = 0.30  # 아래꼬리가 전체 범위의 30% 이상
VOLUME_DRY = 0.80  # 직전 4주 평균의 80% 이하
VOLUME_WINDOW = 4

MIN_WEEKLY = SLOW + TREND_LOOKBACK


def runs_on(data_date: date, run_date: date) -> bool:
    """주가 닫힌 뒤에만 돈다."""
    return week_closed(data_date, run_date)


def evaluate(meta: TickerMeta, bars: BarSet) -> Signal | None:
    """한 종목을 판정한다.

    Returns:
        눌림목 주면 `Signal`, 아니면 None.
    """
    if len(bars.weekly) < MIN_WEEKLY:
        return None

    closes = [float(b.c) for b in bars.weekly]
    fast, slow = sma(closes, FAST), sma(closes, SLOW)
    f, s = fast[-1], slow[-1]
    s_old = slow[-1 - TREND_LOOKBACK]
    if f is None or s is None or s_old is None:
        return None

    last = bars.weekly[-1]
    body_low = float(min(last.o, last.c))
    span = float(last.h - last.low)
    tail = body_low - float(last.low)
    tail_ratio = tail / span if span else 0.0

    vols = [float(b.v) for b in bars.weekly]
    base_vol = sum(vols[-VOLUME_WINDOW - 1 : -1]) / VOLUME_WINDOW
    vol_ratio = vols[-1] / base_vol if base_vol else 0.0

    ck = Checks()
    slope = (s - s_old) / s_old if s_old else 0.0
    ck.add("주봉 MA20 > MA60 (상승 추세)", f > s, f"{won(f)} > {won(s)}")
    ck.add(
        f"MA60이 {TREND_LOOKBACK}주간 {TREND_MIN_SLOPE:.1%} 이상 상승",
        slope >= TREND_MIN_SLOPE,
        f"{slope:+.2%} ({won(s_old)} → {won(s)})",
    )
    ck.add("저가가 MA20 터치", float(last.low) <= f * TOUCH_TOLERANCE,
           f"저가 {won(last.low)} vs MA20 {won(f)}")
    ck.add("종가는 MA20 위에서 마감", float(last.c) >= f, f"{won(last.c)} vs {won(f)}")
    ck.add(f"아래꼬리 {int(TAIL_MIN_RATIO * 100)}% 이상", tail_ratio >= TAIL_MIN_RATIO,
           f"{tail_ratio:.0%} (꼬리 {won(tail)} / 범위 {won(span)})")
    ck.add(f"거래량 {int(VOLUME_DRY * 100)}% 이하로 감소", vol_ratio <= VOLUME_DRY,
           f"{ratio(vol_ratio)} (4주 평균 대비)")

    if not ck.all_ok:
        return None

    # 꼬리가 길고 거래량이 마를수록 높은 점수.
    score = tail_ratio * (1.0 - vol_ratio)

    return make_signal(meta, name, bars, score, ck)
