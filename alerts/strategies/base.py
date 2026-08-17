"""전략 공통 뼈대.

전략 하나는 세 가지를 안다: 이름 · 언제 도는가 · 어떻게 판정하는가.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from alerts.indicators import pct_change
from alerts.models import Bar, BarSet, Condition, Signal, StrategyName, TickerMeta


class Strategy(Protocol):
    """전략 하나. 구현은 모듈 수준 함수로 두고 이 프로토콜에 맞춘다."""

    name: StrategyName

    def runs_on(self, data_date: date, run_date: date) -> bool:
        """오늘 이 전략을 돌리는가 (진행 중인 봉으로 판정하지 않기 위해)."""
        ...

    def evaluate(self, meta: TickerMeta, bars: BarSet) -> Signal | None:
        """한 종목을 판정한다. 신호가 아니면 None."""
        ...


@dataclass(slots=True)
class Checks:
    """조건을 순서대로 모으는 상자.

    조건이 하나라도 깨지면 신호가 아니지만, **깨진 조건도 기록해 둔다** —
    임계값을 조정할 때 "무엇 때문에 떨어졌나"를 보려면 필요하다.
    """

    items: list[Condition]

    def __init__(self) -> None:
        self.items = []

    def add(self, label: str, ok: bool, actual: str) -> bool:
        """조건 하나를 기록하고 그 결과를 그대로 돌려준다."""
        self.items.append(Condition(label=label, ok=ok, actual=actual))
        return ok

    @property
    def all_ok(self) -> bool:
        """전부 통과했는가."""
        return all(c.ok for c in self.items)

    def freeze(self) -> tuple[Condition, ...]:
        """불변 튜플로 굳힌다."""
        return tuple(self.items)


def won(value: float) -> str:
    """원 단위 숫자를 사람이 읽는 형태로.

    포맷을 배치에서 확정한다 — 메일과 웹이 다르게 보이면 안 된다 (PLAN §4).
    """
    return f"{value:,.0f}"


def ratio(value: float) -> str:
    """배수 표기."""
    return f"{value:.2f}배"


def make_signal(
    meta: TickerMeta,
    strategy: StrategyName,
    bars: Sequence[Bar],
    score: float,
    checks: Checks,
    *,
    in_progress: bool = False,
) -> Signal:
    """판정 결과를 `Signal`로 만든다.

    Args:
        meta: 종목 메타.
        strategy: 전략 이름.
        bars: 기준이 되는 봉 배열 (보통 일봉). 마지막 봉의 값을 신호에 담는다.
        score: 전략 내 점수. 정규화는 rank 단계가 한다.
        checks: 조건 기록.
        in_progress: 진행 중인 봉으로 판정했는가 (F8).
    """
    last = bars[-1]
    prev_close = bars[-2].c if len(bars) >= 2 else last.c
    return Signal(
        d=last.d,
        strategy=strategy,
        ticker=meta.ticker,
        name=meta.name,
        score=score,
        conditions=checks.freeze(),
        close=last.c,
        change_pct=round(pct_change(prev_close, last.c), 2),
        volume=last.v,
        amount=last.a or 0,
        in_progress=in_progress,
    )
