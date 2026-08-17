"""그래프 상태 정의.

**여러 노드가 동시에 쓰는 키에는 반드시 리듀서가 붙어야 한다.**
리듀서가 없으면 LangGraph는 마지막에 도착한 값으로 조용히 덮어쓴다 — 예외도 나지 않는다.
`signals`는 전략 5개가, `results`는 발송 2개가 동시에 쓴다.
"""

from __future__ import annotations

import operator
from datetime import date
from typing import Annotated, TypedDict

from alerts.models import BarSet, SendResult, Signal, TickerMeta

STATUS_OK = "ok"
STATUS_STALE = "stale_data"
STATUS_PARTIAL = "partial_send_failed"
STATUS_FAILED = "send_failed"


def merge_results(
    left: dict[str, SendResult], right: dict[str, SendResult]
) -> dict[str, SendResult]:
    """발송 결과를 채널 이름으로 합친다.

    Args:
        left: 먼저 도착한 결과.
        right: 나중에 도착한 결과.

    Returns:
        두 결과를 합친 새 사전. 원본을 변형하지 않는다.
    """
    return {**left, **right}


class AlertState(TypedDict, total=False):
    """그래프를 흐르는 상태.

    `total=False`인 것은 노드가 자기가 바꾼 키만 반환하기 때문이다.
    초기 상태는 `initial_state()`로 만든다.
    """

    # 입력 — main이 주입한다. 전략은 "오늘"을 직접 알지 못한다.
    run_date: date
    channels: list[str]
    dry_run: bool

    # 준비 단계 산출
    data_date: date | None
    stale: bool
    universe: list[TickerMeta]
    bars: dict[str, BarSet]

    # 전략 5개가 동시에 쓰는 유일한 키 — 리듀서 필수
    signals: Annotated[list[Signal], operator.add]

    ranked: list[Signal]
    kakao_top: list[Signal]        # 카카오에 담을 상위 N건 (D8)

    # 발송 노드가 각자 쓰는 키. 순차 실행이지만 리듀서를 유지한다 —
    # 없으면 뒤 노드가 앞 노드의 결과를 덮어써 실패 기록이 사라진다.
    results: Annotated[dict[str, SendResult], merge_results]
    status: str

    # 카카오가 새로 발급한 리프레시 토큰. 저장하지 않으면 2개월 뒤 조용히 죽는다 (R2).
    kakao_refresh: str


def initial_state(
    run_date: date,
    channels: list[str],
    *,
    dry_run: bool = False,
) -> AlertState:
    """그래프에 넣을 초기 상태를 만든다.

    Args:
        run_date: 배치 기준일. 드라이런은 과거 날짜를 넣는다.
        channels: 발송 채널 목록 (`kakao` / `email`).
        dry_run: True면 실제로 발송하지 않는다.

    Returns:
        모든 키가 채워진 초기 상태.
    """
    return AlertState(
        run_date=run_date,
        channels=list(channels),
        dry_run=dry_run,
        data_date=None,
        stale=False,
        universe=[],
        bars={},
        signals=[],
        ranked=[],
        kakao_top=[],
        results={},
        status=STATUS_OK,
        kakao_refresh="",
    )
