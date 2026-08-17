"""F8 밴드 스퀴즈 & 확장.

주봉 밴드폭이 52주 최저 수준까지 좁혀졌다가 상단을 뚫는 주.
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, Signal
from alerts.strategies import squeeze
from tests.conftest import bar, barset, meta

QUIET = 100.0


def weekly_bars(closes: list[float], amounts: list[int] | None = None) -> tuple[Bar, ...]:
    """주봉 배열. 거래대금을 따로 줄 수 있다."""
    amts = amounts if amounts is not None else [1_000_000_000] * len(closes)
    return tuple(
        bar(c, day=i * 7, h=int(c), low=int(c), v=1_000_000, a=amts[i])
        for i, c in enumerate(closes)
    )


def squeezing_then_breakout(
    *,
    breakout_close: float = 130.0,
    breakout_amount: int = 5_000_000_000,
    tail_weeks: int = 0,
) -> tuple[Bar, ...]:
    """앞은 출렁이고, 최근 20주는 아주 조용하다가, 마지막 주에 뚫는다.

    52주 분포를 만들려면 MA 워밍업 20주가 더 필요해 전체가 73주를 넘어야 한다.
    """
    # 앞 60주: 넓은 변동 → BandWidth 분포의 위쪽을 만든다
    noisy = [QUIET + (12 if i % 2 else -12) for i in range(60)]
    # 다음 20주: 거의 정지 → 밴드가 최대로 좁혀진다
    calm = [QUIET + (0.2 if i % 2 else -0.2) for i in range(20)]
    # 꼬리가 짧으면 20주 창의 대부분이 여전히 조용해 밴드가 안 벌어진다.
    tail = [QUIET + (10 if i % 2 else -10) for i in range(tail_weeks)]
    closes = noisy + calm + tail + [breakout_close]
    amounts = [1_000_000_000] * (len(closes) - 1) + [breakout_amount]
    return weekly_bars(closes, amounts)


def fired(weekly: tuple[Bar, ...] | None = None) -> Signal | None:
    return squeeze.evaluate(
        meta(), barset(weekly=weekly if weekly is not None else squeezing_then_breakout())
    )


# ── 양성 ────────────────────────────────────────────────────────


def test_squeeze_then_breakout_fires() -> None:
    sig = fired()

    assert sig is not None
    assert sig.strategy == "squeeze"
    assert all(c.ok for c in sig.conditions)


def test_signal_is_marked_in_progress() -> None:
    """진행 중인 주봉으로도 판정한다. 뒤집힐 수 있으니 본문에 표기해야 한다 (SPEC F8)."""
    sig = fired()

    assert sig is not None
    assert sig.in_progress is True
    assert sig.evidence()["meta"]["in_progress"] is True


# ── 음성: 조건별 ────────────────────────────────────────────────


def test_no_breakout_does_not_fire() -> None:
    """밴드가 좁아도 상단을 못 뚫으면 신호가 아니다."""
    assert fired(squeezing_then_breakout(breakout_close=100.5)) is None


def test_wide_band_before_breakout_does_not_fire() -> None:
    """직전 주 밴드폭이 하위 10%가 아니면 스퀴즈가 아니다."""
    assert fired(squeezing_then_breakout(tail_weeks=14)) is None


def test_no_volume_confirmation_does_not_fire() -> None:
    """거래대금이 안 따라오면 가짜 돌파일 가능성이 크다."""
    assert fired(squeezing_then_breakout(breakout_amount=900_000_000)) is None


def test_band_must_expand() -> None:
    """밴드가 오히려 더 좁아지는 주에는 '확장'이라 부를 수 없다."""
    flat_closes = [QUIET] * 75
    assert fired(weekly_bars(flat_closes)) is None


# ── 음성: 봉 부족 ───────────────────────────────────────────────


def test_short_history_is_skipped() -> None:
    """52주 분포를 만들려면 20 + 52주가 필요하다."""
    assert fired(weekly_bars([QUIET + i for i in range(40)])) is None


def test_empty_barset_is_skipped() -> None:
    assert squeeze.evaluate(meta(), barset()) is None


# ── 점수 ────────────────────────────────────────────────────────


def test_score_prefers_stronger_expansion() -> None:
    strong = fired(squeezing_then_breakout(breakout_close=160, breakout_amount=9_000_000_000))
    weak = fired(squeezing_then_breakout(breakout_close=112, breakout_amount=1_600_000_000))

    assert strong is not None and weak is not None
    assert strong.score > weak.score


# ── 실행 주기 ───────────────────────────────────────────────────


def test_squeeze_runs_every_day() -> None:
    """주봉 기반이지만 진행 중인 주봉이 매일 갱신되므로 매일 본다 (SPEC F8)."""
    assert squeeze.runs_on(date(2026, 8, 17), date(2026, 8, 18))
