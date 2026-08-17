"""그래프 배선 테스트.

**여기서 검사하는 것은 배관이지 도메인 로직이 아니다** (SPEC N11).
전략 판정은 `tests/test_strategies_*.py`가 순수 함수를 직접 불러 검사한다.

이 파일이 지키는 세 가지:
  ① 신선도 게이트의 양쪽 경로가 실제로 갈라진다
  ② 전략 5개의 결과가 **전부** 합쳐진다 — 리듀서 누락은 예외 없이 조용히 틀린다
  ③ 발송 노드가 실패해도 record_run에 도달한다 — 안 그러면 실패 기록이 사라진다
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from alerts.graph import build_graph
from alerts.models import STRATEGY_NAMES, SendResult, Signal, StrategyName
from alerts.nodes import AlertRunError
from alerts.state import (
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_STALE,
    AlertState,
    initial_state,
)

RUN_DATE = date(2026, 8, 17)


def a_signal(strategy: StrategyName, ticker: str) -> Signal:
    """테스트용 신호 하나."""
    return Signal(d=RUN_DATE, strategy=strategy, ticker=ticker, name=ticker, score=1.0)


def trace_node(name: str, log: list[str], patch: dict[str, Any] | None = None) -> Any:
    """호출되면 이름을 기록하고, 주어진 값을 상태에 쓰는 스텁 노드."""

    def node(state: AlertState) -> dict[str, Any]:
        log.append(name)
        return dict(patch or {})

    return node


def const_node(patch: dict[str, Any]) -> Any:
    """상태에 고정값을 쓰는 스텁 노드."""

    def node(state: AlertState) -> dict[str, Any]:
        return dict(patch)

    return node


def signal_node(strategy: StrategyName, ticker: str) -> Any:
    """신호 하나를 내는 전략 스텁 노드."""

    def node(state: AlertState) -> dict[str, Any]:
        return {"signals": [a_signal(strategy, ticker)]}

    return node


def failed_send_node(channel: str, error: str = "boom") -> Any:
    """발송에 실패했지만 **예외를 내지 않는** 스텁 노드 (F13c)."""

    def node(state: AlertState) -> dict[str, Any]:
        return {"results": {channel: SendResult(channel=channel, ok=False, error=error)}}

    return node


# ── ① 분기 ──────────────────────────────────────────────────────


def test_fresh_path_runs_the_screening_nodes() -> None:
    log: list[str] = []
    overrides = {n: trace_node(n, log) for n in ("abort_stale", "build_universe", "load_bars")}
    build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao"]))

    assert "build_universe" in log
    assert "load_bars" in log
    assert "abort_stale" not in log


def test_stale_path_skips_the_screening_nodes() -> None:
    log: list[str] = []
    overrides: dict[str, Any] = {
        n: trace_node(n, log) for n in ("abort_stale", "build_universe", "load_bars")
    }
    overrides["load_meta"] = const_node({"stale": True})

    build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao"]))

    assert "abort_stale" in log
    assert "build_universe" not in log
    assert "load_bars" not in log


def test_stale_path_still_reaches_the_send_nodes() -> None:
    """낡은 데이터일 때 조용히 END로 빠지면 고장을 몇 주간 못 알아챈다 (D10)."""
    log: list[str] = []
    overrides: dict[str, Any] = {
        "load_meta": const_node({"stale": True}),
        "send_kakao": trace_node("send_kakao", log),
        "send_email": trace_node("send_email", log),
    }
    build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert log.count("send_kakao") == 1
    assert log.count("send_email") == 1


# ── ② 리듀서 합류 ───────────────────────────────────────────────


def test_all_five_strategy_results_are_merged() -> None:
    """리듀서를 빼먹으면 마지막 전략 하나만 남고 **예외가 나지 않는다.**

    이 테스트가 그걸 잡는 유일한 장치다. 지우지 말 것.
    """
    overrides: dict[str, Any] = {
        f"strategy_{name}": signal_node(name, f"T_{name}") for name in STRATEGY_NAMES
    }
    final = build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao"]))

    assert len(final["signals"]) == len(STRATEGY_NAMES) == 5
    assert {s.strategy for s in final["signals"]} == set(STRATEGY_NAMES)


def test_strategy_node_returning_nothing_does_not_drop_the_others() -> None:
    """한 전략이 0건이어도 나머지 결과가 살아 있어야 한다."""
    overrides: dict[str, Any] = {
        f"strategy_{n}": const_node({"signals": []}) for n in STRATEGY_NAMES
    }
    overrides["strategy_mtf"] = signal_node("mtf", "005930")

    final = build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao"]))

    assert len(final["signals"]) == 1
    assert final["signals"][0].ticker == "005930"


def test_send_results_from_both_channels_are_merged() -> None:
    final = build_graph().invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert set(final["results"]) == {"kakao", "email"}


# ── ③ 발송 실패 격리 ────────────────────────────────────────────


def test_channel_failure_still_reaches_record_run() -> None:
    """발송 노드가 raise하면 record_run에 닿지 못해 실패 기록이 통째로 사라진다."""
    log: list[str] = []
    overrides: dict[str, Any] = {
        "send_kakao": failed_send_node("kakao", "KOE322"),
        "record_run": trace_node("record_run", log, {"status": STATUS_PARTIAL}),
    }
    with pytest.raises(AlertRunError):
        build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert log == ["record_run"], "실패해도 기록이 먼저다"


def test_one_channel_down_the_other_still_runs() -> None:
    log: list[str] = []
    overrides: dict[str, Any] = {
        "send_kakao": failed_send_node("kakao", "KOE322"),
        "send_email": trace_node(
            "send_email",
            log,
            {"results": {"email": SendResult(channel="email", ok=True, sent_n=7)}},
        ),
    }
    with pytest.raises(AlertRunError):
        build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert log == ["send_email"], "카카오가 죽어도 메일은 간다"


def test_partial_failure_is_not_reported_as_success() -> None:
    overrides: dict[str, Any] = {
        "send_kakao": failed_send_node("kakao", "KOE322"),
        "finalize": const_node({}),  # 예외를 막고 status만 본다
    }
    final = build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert final["status"] == STATUS_PARTIAL


def test_all_channels_failed_is_send_failed() -> None:
    overrides: dict[str, Any] = {
        "send_kakao": failed_send_node("kakao"),
        "send_email": failed_send_node("email"),
        "finalize": const_node({}),
    }
    final = build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert final["status"] == STATUS_FAILED


# ── 완주 ────────────────────────────────────────────────────────


def test_skeleton_completes_end_to_end() -> None:
    final = build_graph().invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert final["status"] == STATUS_OK
    assert final["run_date"] == RUN_DATE
    assert final["signals"] == []


def test_stale_run_ends_with_stale_status() -> None:
    overrides: dict[str, Any] = {"load_meta": const_node({"stale": True})}
    final = build_graph(overrides).invoke(initial_state(RUN_DATE, ["kakao", "email"]))

    assert final["status"] == STATUS_STALE


def test_single_channel_only_sends_that_channel() -> None:
    final = build_graph().invoke(initial_state(RUN_DATE, ["email"]))

    assert set(final["results"]) == {"email"}


def test_graph_exposes_every_node() -> None:
    """노드가 실수로 빠지면 엣지만 남아 조용히 건너뛴다."""
    names = set(build_graph().get_graph().nodes)
    expected = {
        "load_meta", "abort_stale", "build_universe", "load_bars",
        "suppress", "rank", "persist",
        "send_kakao", "send_email", "record_run", "finalize",
        *(f"strategy_{n}" for n in STRATEGY_NAMES),
    }
    assert expected <= names
