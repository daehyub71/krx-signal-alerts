"""전략 다섯 개 (SPEC F5~F9).

이 패키지는 **LangGraph를 모른다.** 봉 배열을 받아 신호를 돌려주는 순수 함수뿐이다.
테스트는 여기의 함수를 직접 부른다 — 그래프를 통해 전략 로직을 시험하지 않는다 (SPEC N11).

전략을 늘리려면 모듈을 하나 만들고 아래 `ALL`에 한 줄, `graph.py`에 엣지 두 줄을 더한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from alerts.models import BarSet, Signal, StrategyName, TickerMeta
from alerts.strategies import mtf, pullback, squeeze, turnaround, vcp

Evaluate = Callable[[TickerMeta, BarSet], Signal | None]


def skip_halted(fn: Evaluate) -> Evaluate:
    """판정일에 거래가 없었으면 아예 판정하지 않는다.

    KRX 거래정지일은 거래량 0 · 시고저가 = 종가로 들어온다. 전 일봉의 **4.5%**가
    이런 행이다 (2026-08-17 실측). 이걸 막지 않으면 "거래량 0.00배 · 변동성 0.00배"가
    완벽한 수축으로 잡혀 VCP가 거래정지 종목으로 도배된다.

    거래정지 종목은 살 수도 없으니 알릴 이유가 없다.
    """

    def wrapped(meta: TickerMeta, bars: BarSet) -> Signal | None:
        if not bars.daily or bars.daily[-1].v == 0:
            return None
        return fn(meta, bars)

    return wrapped


@dataclass(frozen=True, slots=True)
class Registered:
    """등록된 전략 하나.

    모듈을 프로토콜로 직접 다루지 않고 이 값으로 감싼다 — 모듈은 타입 검사에서
    구조적 매칭이 불안정하고, 감싸 두면 테스트에서 갈아끼우기도 쉽다.
    """

    name: StrategyName
    runs_on: Callable[[date, date], bool]
    evaluate: Evaluate


ALL: tuple[Registered, ...] = (
    Registered(mtf.name, mtf.runs_on, skip_halted(mtf.evaluate)),
    Registered(pullback.name, pullback.runs_on, skip_halted(pullback.evaluate)),
    Registered(vcp.name, vcp.runs_on, skip_halted(vcp.evaluate)),
    Registered(squeeze.name, squeeze.runs_on, skip_halted(squeeze.evaluate)),
    Registered(turnaround.name, turnaround.runs_on, skip_halted(turnaround.evaluate)),
)

BY_NAME: dict[StrategyName, Registered] = {s.name: s for s in ALL}

__all__ = ["ALL", "BY_NAME", "Registered", "mtf", "pullback", "squeeze", "turnaround", "vcp"]
