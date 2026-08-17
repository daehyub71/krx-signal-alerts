"""F10 중복 억제 · F11 랭킹.

경계일에서 off-by-one이 나기 쉬워 9/10/11일을 하나씩 짚는다.
"""

from __future__ import annotations

from datetime import date, timedelta

from alerts.models import STRATEGY_NAMES, Signal, StrategyName
from alerts.rank import SUPPRESS_DAYS, rank, suppress

TODAY = date(2026, 8, 17)


def sig(
    strategy: StrategyName = "mtf",
    ticker: str = "005930",
    score: float = 1.0,
    amount: int = 1_000_000_000,
    d: date = TODAY,
) -> Signal:
    return Signal(d=d, strategy=strategy, ticker=ticker, name=ticker, score=score, amount=amount)


def key(ticker: str, strategy: str, days_ago: int) -> tuple[str, str, date]:
    return (ticker, strategy, TODAY - timedelta(days=days_ago))


# ── F10 중복 억제 ───────────────────────────────────────────────


def test_no_history_means_no_suppression() -> None:
    assert suppress([sig()], [])[0].suppressed is False


def test_signal_inside_the_window_is_suppressed() -> None:
    out = suppress([sig()], [key("005930", "mtf", 9)])
    assert out[0].suppressed is True


def test_signal_at_the_window_edge_is_suppressed() -> None:
    """mtf는 10일. 정확히 10일 전은 억제한다."""
    assert SUPPRESS_DAYS["mtf"] == 10
    out = suppress([sig()], [key("005930", "mtf", 10)])
    assert out[0].suppressed is True


def test_signal_beyond_the_window_is_not_suppressed() -> None:
    out = suppress([sig()], [key("005930", "mtf", 11)])
    assert out[0].suppressed is False


def test_same_day_history_does_not_suppress() -> None:
    """배치를 두 번 돌렸을 때 두 번째가 전부 억제되면 멱등이 깨진다 (SPEC N6)."""
    out = suppress([sig()], [key("005930", "mtf", 0)])
    assert out[0].suppressed is False


def test_other_strategy_does_not_suppress() -> None:
    out = suppress([sig(strategy="mtf")], [key("005930", "vcp", 3)])
    assert out[0].suppressed is False


def test_other_ticker_does_not_suppress() -> None:
    out = suppress([sig(ticker="005930")], [key("000660", "mtf", 3)])
    assert out[0].suppressed is False


def test_monthly_strategy_uses_a_long_window() -> None:
    """턴어라운드를 10일로 두면 억제가 사실상 없는 것과 같다."""
    assert SUPPRESS_DAYS["turnaround"] == 90
    out = suppress([sig(strategy="turnaround")], [key("005930", "turnaround", 45)])
    assert out[0].suppressed is True


def test_every_strategy_has_a_window() -> None:
    assert set(SUPPRESS_DAYS) == set(STRATEGY_NAMES)


# ── F11 랭킹 ────────────────────────────────────────────────────


def test_suppressed_signals_are_kept_but_never_sent() -> None:
    """저장은 하되 발송만 뺀다. 웹 이력에서는 보여야 한다."""
    signals = suppress([sig(ticker="005930")], [key("005930", "mtf", 3)])
    all_ranked, top = rank(signals)

    assert len(all_ranked) == 1
    assert all_ranked[0].suppressed is True
    assert top == []


def test_top_is_capped_at_the_limit() -> None:
    signals = [sig(ticker=f"{i:05d}0", score=float(i)) for i in range(30)]
    _, top = rank(signals, limit=10)

    assert len(top) == 10


def test_percentile_normalization_stops_one_strategy_taking_over() -> None:
    """전략마다 점수 스케일이 다르다. 그대로 합치면 큰 쪽이 상위를 독식한다."""
    big = [sig(strategy="turnaround", ticker=f"1000{i}0", score=100.0 + i) for i in range(9)]
    small = [sig(strategy="vcp", ticker="200000", score=0.9)]
    _, top = rank(big + small, limit=5)

    assert "vcp" in {s.strategy for s in top}


def test_every_strategy_gets_at_least_one_slot() -> None:
    signals = [
        sig(strategy=name, ticker=f"{i:05d}0", score=float(i))
        for i, name in enumerate(STRATEGY_NAMES)
    ]
    _, top = rank(signals, limit=5)

    assert {s.strategy for s in top} == set(STRATEGY_NAMES)


def test_rank_numbers_are_sequential_from_one() -> None:
    signals = [sig(ticker=f"{i:05d}0", score=float(i)) for i in range(5)]
    _, top = rank(signals, limit=3)

    assert [s.rank_no for s in top] == [1, 2, 3]


def test_only_the_top_is_marked_for_kakao() -> None:
    signals = [sig(ticker=f"{i:05d}0", score=float(i)) for i in range(6)]
    all_ranked, top = rank(signals, limit=2)

    assert sum(1 for s in all_ranked if s.sent_kakao) == 2
    assert len(top) == 2


def test_higher_score_within_a_strategy_ranks_first() -> None:
    low = sig(ticker="000010", score=1.0)
    high = sig(ticker="000020", score=9.0)
    _, top = rank([low, high], limit=2)

    assert top[0].ticker == "000020"


def test_ties_break_on_amount() -> None:
    thin = sig(ticker="000010", score=5.0, amount=1_000_000)
    thick = sig(ticker="000020", score=5.0, amount=9_000_000_000)
    _, top = rank([thin, thick], limit=2)

    assert top[0].ticker == "000020"


def test_empty_input_is_empty_output() -> None:
    assert rank([]) == ([], [])


def test_rank_is_stable_across_runs() -> None:
    """같은 입력이면 같은 순서. 아니면 재실행 결과가 달라 보인다 (SPEC N6)."""
    signals = [sig(ticker=f"{i:05d}0", score=float(i % 3)) for i in range(12)]
    a = [s.ticker for s in rank(signals, limit=5)[1]]
    b = [s.ticker for s in rank(signals, limit=5)[1]]

    assert a == b
