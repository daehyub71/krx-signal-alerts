"""지표 계산 — 순수 함수.

전략 다섯 개가 전부 여기에 기댄다. 여기가 틀리면 전부 틀린다.
`pandas`를 쓰지 않는다 — 이동평균·표준편차·분위수뿐이라 표준 라이브러리로 충분하다 (PLAN §2).

**워밍업 구간은 `None`이다.** 0으로 채우면 "종가 > MA20"이 항상 참이 되어
데이터가 모자란 종목이 전부 신호로 잡힌다.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Band:
    """볼린저밴드 한 지점."""

    mid: float
    upper: float
    lower: float
    width: float  # (upper - lower) / mid — 스퀴즈 판정에 쓴다 (F8)


def sma(values: Sequence[float], period: int) -> list[float | None]:
    """단순이동평균.

    Args:
        values: 원본 수열 (보통 종가).
        period: 기간.

    Returns:
        입력과 **길이가 같은** 리스트. 앞 `period - 1`개는 `None`.
        길이를 맞추는 것이 중요하다 — 어긋나면 봉과 지표의 인덱스가 밀려 조용히 틀린다.

    Raises:
        ValueError: `period`가 1 미만일 때.
    """
    if period < 1:
        raise ValueError(f"period는 1 이상이어야 한다: {period}")

    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out

    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def bollinger(values: Sequence[float], period: int = 20, k: float = 2.0) -> list[Band | None]:
    """볼린저밴드.

    Args:
        values: 원본 수열 (종가).
        period: 이동평균 기간.
        k: 표준편차 배수.

    Returns:
        입력과 길이가 같은 리스트. 워밍업 구간은 `None`.

    Note:
        **모표준편차(ddof=0)**를 쓴다. 표본 표준편차로 바꾸면 밴드가 넓어져
        "52주 중 하위 10%"(F8) 백분위가 통째로 달라진다.
    """
    if period < 1:
        raise ValueError(f"period는 1 이상이어야 한다: {period}")

    out: list[Band | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mid = statistics.fmean(window)
        sd = statistics.pstdev(window, mu=mid)
        upper, lower = mid + k * sd, mid - k * sd
        # 가격은 0일 수 없지만, 0으로 나누기가 배치를 죽이게 두지 않는다.
        width = (upper - lower) / mid if mid else 0.0
        out[i] = Band(mid=mid, upper=upper, lower=lower, width=width)
    return out


def quantile(values: Sequence[float], q: float) -> float:
    """선형 보간 분위수.

    Args:
        values: 표본. 정렬돼 있지 않아도 된다.
        q: 0.0 ~ 1.0.

    Returns:
        `q` 분위 값.

    Raises:
        ValueError: 표본이 비었거나 `q`가 범위를 벗어날 때.
    """
    if not values:
        raise ValueError("빈 표본의 분위수는 정의되지 않는다")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q는 0..1이어야 한다: {q}")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]

    pos = q * (len(ordered) - 1)
    low = int(pos)
    if low >= len(ordered) - 1:
        return ordered[-1]
    frac = pos - low
    return ordered[low] + (ordered[low + 1] - ordered[low]) * frac


def pct_change(prev: float, curr: float) -> float:
    """전일 대비 변동률(%). `prev`가 0이면 0.0."""
    return (curr - prev) / prev * 100.0 if prev else 0.0
