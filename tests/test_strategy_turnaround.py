"""F9 장기 턴어라운드.

6개월 횡보 뒤 거래량·거래대금이 3배로 들어오며 박스를 넘는 달.
월봉 37개(3년) 제약 때문에 횡보 구간을 6개월로 고정했다 (SPEC R1).
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, Signal
from alerts.strategies import turnaround
from tests.conftest import bar, barset, meta

BOX = 100.0
BASE_V = 1_000_000
BASE_A = 100_000_000


def monthly(
    *,
    box_span: float = 0.0,
    breakout_close: float = 130.0,
    breakout_volume: int = 4_000_000,
    breakout_amount: int = 520_000_000,
    history: int = 18,
) -> tuple[Bar, ...]:
    """직전 12개월 이상 조용하다가 마지막 달에 터진다.

    기본값은 전부 통과하는 양성 시나리오다.
    """
    bars: list[Bar] = []
    for i in range(history):
        # 최근 6개월 박스 폭을 box_span으로 조절한다
        wobble = box_span if i % 2 and i >= history - 6 else 0.0
        c = BOX + wobble
        bars.append(bar(c, day=i * 30, h=int(c + 1), low=int(c - 1), v=BASE_V, a=BASE_A))
    bars.append(
        bar(
            breakout_close,
            day=history * 30,
            o=int(BOX),
            h=int(breakout_close),
            low=int(BOX - 2),
            v=breakout_volume,
            a=breakout_amount,
        )
    )
    return tuple(bars)


def fired(bars: tuple[Bar, ...] | None = None) -> Signal | None:
    return turnaround.evaluate(meta(), barset(monthly=bars if bars is not None else monthly()))


# ── 양성 ────────────────────────────────────────────────────────


def test_quiet_box_then_volume_surge_fires() -> None:
    sig = fired()

    assert sig is not None
    assert sig.strategy == "turnaround"
    assert all(c.ok for c in sig.conditions)


# ── 음성: 조건별 ────────────────────────────────────────────────


def test_wide_range_is_not_a_box() -> None:
    """30% 넘게 출렁였으면 횡보가 아니다."""
    assert fired(monthly(box_span=60.0)) is None


def test_no_volume_surge_does_not_fire() -> None:
    """거래량이 안 붙으면 그냥 오른 것이다."""
    assert fired(monthly(breakout_volume=1_500_000)) is None


def test_no_amount_surge_does_not_fire() -> None:
    """거래량만 3배인 저가주 오탐을 거래대금으로 거른다 (SPEC D5)."""
    assert fired(monthly(breakout_amount=150_000_000)) is None


def test_close_inside_the_box_does_not_fire() -> None:
    """박스를 못 넘으면 아직 아니다."""
    assert fired(monthly(breakout_close=100.0)) is None


# ── 음성: 봉 부족 ───────────────────────────────────────────────


def test_short_monthly_history_is_skipped() -> None:
    """12개월 평균 거래량 + 6개월 박스 → 최소 19개월이 필요하다 (SPEC R1)."""
    assert fired(monthly(history=10)) is None


def test_exactly_minimum_history_works() -> None:
    """경계에서 애매하면 나중에 다투게 된다."""
    assert fired(monthly(history=18)) is not None


def test_empty_barset_is_skipped() -> None:
    assert turnaround.evaluate(meta(), barset()) is None


# ── 점수 ────────────────────────────────────────────────────────


def test_score_prefers_bigger_surge_and_breakout() -> None:
    strong = fired(monthly(breakout_close=180, breakout_volume=9_000_000,
                           breakout_amount=1_600_000_000))
    weak = fired(monthly(breakout_close=105, breakout_volume=3_100_000,
                         breakout_amount=330_000_000))

    assert strong is not None and weak is not None
    assert strong.score > weak.score


# ── 실행 주기 ───────────────────────────────────────────────────


def test_turnaround_only_runs_after_the_month_closes() -> None:
    """월중에는 미완성 월봉이라 거래량이 과소 집계된다 (SPEC F9)."""
    assert turnaround.runs_on(date(2026, 8, 31), date(2026, 9, 1))
    assert not turnaround.runs_on(date(2026, 8, 14), date(2026, 8, 17))
