"""state — 리듀서와 초기 상태."""

from __future__ import annotations

from datetime import date

from alerts.models import SendResult
from alerts.state import STATUS_OK, initial_state, merge_results


def test_merge_results_combines_channels() -> None:
    left = {"kakao": SendResult(channel="kakao", ok=True, sent_n=10)}
    right = {"email": SendResult(channel="email", ok=True, sent_n=42)}

    assert set(merge_results(left, right)) == {"kakao", "email"}


def test_merge_results_does_not_mutate_inputs() -> None:
    left = {"kakao": SendResult(channel="kakao", ok=True)}
    right = {"email": SendResult(channel="email", ok=True)}
    merge_results(left, right)

    assert set(left) == {"kakao"}
    assert set(right) == {"email"}


def test_initial_state_fills_every_key() -> None:
    """빈 키가 남으면 노드가 KeyError로 늦게 터진다."""
    state = initial_state(date(2026, 8, 17), ["kakao", "email"])

    expected = {
        "run_date", "channels", "dry_run", "data_date", "stale",
        "universe", "bars", "signals", "ranked", "kakao_top", "results", "status",
        "kakao_refresh",
    }
    assert set(state) == expected
    assert state["status"] == STATUS_OK


def test_initial_state_copies_the_channel_list() -> None:
    channels = ["kakao"]
    state = initial_state(date(2026, 8, 17), channels)
    channels.append("email")

    assert state["channels"] == ["kakao"]
