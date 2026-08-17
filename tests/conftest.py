"""전략 테스트용 봉 생성기.

손으로 만든 시나리오로 양성·음성을 모두 검증한다. 실DB에 붙지 않는다.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from alerts.models import Bar, BarSet, TickerMeta

START = date(2024, 1, 1)


def bar(
    close: float,
    *,
    day: int = 0,
    o: float | None = None,
    h: float | None = None,
    low: float | None = None,
    v: int = 1_000_000,
    a: int | None = None,
) -> Bar:
    """봉 하나. 지정하지 않은 값은 종가에서 유도한다."""
    c = int(close)
    open_ = int(o if o is not None else c)
    high = int(h if h is not None else max(open_, c))
    lo = int(low if low is not None else min(open_, c))
    return Bar(
        d=START + timedelta(days=day),
        o=open_,
        h=high,
        low=lo,
        c=c,
        v=v,
        a=a if a is not None else c * v,
    )


def series(closes: Sequence[float], *, v: int = 1_000_000) -> tuple[Bar, ...]:
    """종가 수열로 봉 배열을 만든다. 날짜는 하루씩 증가한다."""
    return tuple(bar(c, day=i, v=v) for i, c in enumerate(closes))


def rising(n: int, start: float = 100.0, step: float = 1.0) -> list[float]:
    """꾸준히 오르는 종가 수열."""
    return [start + step * i for i in range(n)]


def flat(n: int, value: float = 100.0) -> list[float]:
    """평평한 종가 수열."""
    return [value] * n


def barset(
    ticker: str = "005930",
    *,
    daily: Sequence[Bar] = (),
    weekly: Sequence[Bar] = (),
    monthly: Sequence[Bar] = (),
) -> BarSet:
    """봉 묶음."""
    return BarSet(ticker=ticker, daily=tuple(daily), weekly=tuple(weekly), monthly=tuple(monthly))


def meta(ticker: str = "005930", name: str = "삼성전자") -> TickerMeta:
    """종목 메타."""
    return TickerMeta(ticker=ticker, name=name, market="KOSPI")
