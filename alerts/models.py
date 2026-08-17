"""도메인 모델.

이 모듈은 LangGraph를 모른다. 그래프 층을 걷어내도 그대로 살아남아야 한다 (SPEC N11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

Timeframe = Literal["D", "W", "M"]
StrategyName = Literal["mtf", "pullback", "vcp", "squeeze", "turnaround"]

STRATEGY_NAMES: tuple[StrategyName, ...] = ("mtf", "pullback", "vcp", "squeeze", "turnaround")

STRATEGY_LABELS: dict[StrategyName, str] = {
    "mtf": "MTF 정배열",
    "pullback": "주봉 눌림목",
    "vcp": "VCP 수축",
    "squeeze": "밴드 스퀴즈",
    "turnaround": "장기 턴어라운드",
}


@dataclass(frozen=True, slots=True)
class Bar:
    """봉 하나. `ksc_bars` 한 행에 대응한다.

    주봉·월봉의 `d`는 해당 구간의 마지막 거래일이다.
    """

    d: date
    o: int
    h: int
    low: int  # `l`은 ruff E741(ambiguous name)에 걸려 low로 쓴다
    c: int
    v: int
    a: int | None = None  # 거래대금(원). 2026-08-16 백필로 현재 100% 채워져 있다


@dataclass(frozen=True, slots=True)
class BarSet:
    """한 종목의 일·주·월봉 묶음."""

    ticker: str
    daily: tuple[Bar, ...] = ()
    weekly: tuple[Bar, ...] = ()
    monthly: tuple[Bar, ...] = ()

    def by_timeframe(self, tf: Timeframe) -> tuple[Bar, ...]:
        """주기 코드로 봉 배열을 꺼낸다."""
        return {"D": self.daily, "W": self.weekly, "M": self.monthly}[tf]


@dataclass(frozen=True, slots=True)
class TickerMeta:
    """종목 메타. `ksc_tickers` 한 행."""

    ticker: str
    name: str
    market: str
    sector: str = ""


@dataclass(frozen=True, slots=True)
class Condition:
    """전략 조건 하나의 판정 결과.

    웹 상세 화면(F16)과 메일 표(F13b)가 이걸 그대로 렌더한다.
    `actual`을 문자열로 두는 것은 의도적이다 — 숫자 포맷을 배치에서 확정해
    두 화면이 다르게 보이는 사고를 막는다 (PLAN §4).
    """

    label: str
    ok: bool
    actual: str


@dataclass(frozen=True, slots=True)
class Signal:
    """전략이 판정한 신호 하나."""

    d: date
    strategy: StrategyName
    ticker: str
    name: str
    score: float
    conditions: tuple[Condition, ...] = ()
    close: int = 0
    change_pct: float = 0.0
    volume: int = 0
    amount: int = 0
    in_progress: bool = False  # 진행 중인 주봉 기준 판정 (F8)

    def evidence(self) -> dict[str, Any]:
        """`ksa_signals.evidence`에 저장할 형태로 편다 (PLAN §4 공유 계약)."""
        return {
            "conditions": [
                {"label": c.label, "ok": c.ok, "actual": c.actual} for c in self.conditions
            ],
            "price": {"close": self.close, "change_pct": self.change_pct},
            "volume": {"value": self.volume, "amount": self.amount},
            "meta": {"in_progress": self.in_progress},
        }


@dataclass(frozen=True, slots=True)
class SendResult:
    """발송 채널 하나의 결과.

    발송 노드는 예외를 밖으로 내지 않고 이 값을 상태에 적는다 (SPEC F13c).
    """

    channel: str
    ok: bool
    sent_n: int = 0
    error: str = ""


@dataclass(slots=True)
class RunRecord:
    """`ksa_runs` 한 행. 안 온 게 정상인지 고장인지를 사후에 가리는 기록이다."""

    data_date: date | None
    universe_n: int
    signal_n: int
    sent_kakao_n: int
    sent_email_n: int
    status: str
    detail: dict[str, Any] = field(default_factory=dict)
