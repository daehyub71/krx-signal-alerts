"""LangGraph 상태 그래프 조립.

구조는 `docs/PLAN.md` §1-1, 그림은 `docs/GRAPH.md`를 본다.
이 모듈은 배선만 한다 — 판정 로직은 노드 밖 도메인 모듈에 있다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from alerts import nodes
from alerts.models import STRATEGY_NAMES
from alerts.state import AlertState

# 네트워크를 타는 노드에만 재시도를 건다. 순수 계산은 재시도해도 같은 결과다.
# 발송 노드는 예외를 밖으로 내지 않으므로(F13c) 노드 단위 재시도가 걸리지 않는다 —
# 전송 재시도는 notify/ 클라이언트 안에서 한다.
NETWORK_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0)

SEND_NODES = ("send_kakao", "send_email")


def build_graph(overrides: Mapping[str, Callable[[AlertState], Any]] | None = None) -> Any:
    """그래프를 만들어 컴파일한다.

    Args:
        overrides: 노드 이름 → 대체 함수. 테스트가 노드를 스텁으로 갈아끼워
            **배선만** 검사할 때 쓴다. 운영에서는 넘기지 않는다.

    Returns:
        컴파일된 그래프.
    """
    sub = dict(overrides or {})

    def pick(name: str, fn: Callable[[AlertState], Any]) -> Any:
        # 반환형이 Any인 것은 의도적이다. LangGraph의 add_node 오버로드가
        # 평범한 Callable을 받아들이지 못해 strict 모드에서 걸린다 — 프레임워크
        # 경계에서만 완화하고, 우리 쪽 타입은 overrides 시그니처가 지킨다.
        return sub.get(name, fn)

    g: StateGraph[AlertState, Any, Any, Any] = StateGraph(AlertState)

    g.add_node("load_meta", pick("load_meta", nodes.load_meta), retry_policy=NETWORK_RETRY)
    g.add_node("abort_stale", pick("abort_stale", nodes.abort_stale))
    g.add_node("build_universe", pick("build_universe", nodes.build_universe))
    g.add_node("load_bars", pick("load_bars", nodes.load_bars), retry_policy=NETWORK_RETRY)

    for name in STRATEGY_NAMES:
        key = f"strategy_{name}"
        g.add_node(key, pick(key, nodes.make_strategy_node(name)))

    g.add_node("suppress", pick("suppress", nodes.suppress))
    g.add_node("rank", pick("rank", nodes.rank))
    g.add_node("persist", pick("persist", nodes.persist))
    g.add_node("send_kakao", pick("send_kakao", nodes.send_kakao))
    g.add_node("send_email", pick("send_email", nodes.send_email))
    g.add_node("record_run", pick("record_run", nodes.record_run))
    g.add_node("finalize", pick("finalize", nodes.finalize))

    g.add_edge(START, "load_meta")

    # 신선도 게이트 — 판정이 그래프 위에 드러나 있다 (F3)
    g.add_conditional_edges(
        "load_meta",
        pick("check_freshness", nodes.check_freshness),
        {"stale": "abort_stale", "fresh": "build_universe"},
    )

    g.add_edge("build_universe", "load_bars")

    # 전략 fan-out → suppress에서 합류. signals 리듀서가 결과를 합친다.
    for name in STRATEGY_NAMES:
        g.add_edge("load_bars", f"strategy_{name}")
        g.add_edge(f"strategy_{name}", "suppress")

    g.add_edge("suppress", "rank")
    g.add_edge("rank", "persist")

    # 정상 경로와 중단 경로가 여기서 만난다. 낡은 데이터여도 침묵하지 않는다 (D10).
    for send in SEND_NODES:
        g.add_edge("persist", send)
        g.add_edge("abort_stale", send)
        g.add_edge(send, "record_run")

    g.add_edge("record_run", "finalize")
    g.add_edge("finalize", END)

    return g.compile()
