"""F5 MTF 트리플 정배열.

양성 1개 + **조건 수만큼의 음성**. 조건 하나를 지워도 통과하는 테스트는
그 조건을 검증하지 않는 것이다 (PLAN §6).
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, Signal
from alerts.strategies import mtf
from tests.conftest import barset, flat, meta, rising, series


def good_monthly() -> tuple[Bar, ...]:
    """월봉: 종가가 MA20 위, MA20이 상승 중."""
    return series(rising(24, start=100, step=5))


def good_weekly() -> tuple[Bar, ...]:
    """주봉: 종가 > MA20 > MA60."""
    return series(rising(70, start=100, step=2))


def good_daily(step: float = 1.0) -> tuple[Bar, ...]:
    """일봉: 종가 > MA20 > MA60."""
    return series(rising(70, start=100, step=step))


def fired(
    daily: tuple[Bar, ...] | None = None,
    weekly: tuple[Bar, ...] | None = None,
    monthly: tuple[Bar, ...] | None = None,
) -> Signal | None:
    """판정을 돌린다."""
    return mtf.evaluate(
        meta(),
        barset(
            daily=daily if daily is not None else good_daily(),
            weekly=weekly if weekly is not None else good_weekly(),
            monthly=monthly if monthly is not None else good_monthly(),
        ),
    )


# ── 양성 ────────────────────────────────────────────────────────


def test_all_three_axes_aligned_fires() -> None:
    """세 축이 전부 정배열이고 오늘 막 전환됐으면 신호다.

    일봉을 오래 눕혀 두었다가 마지막 하루에 띄운다. 완만히 오르는 수열은
    **어제 이미 정배열**이라 전환일 조건에 걸린다.
    """
    sig = fired(daily=series(list(flat(64, 100)) + [130]))

    assert sig is not None
    assert sig.strategy == "mtf"
    assert sig.ticker == "005930"
    assert all(c.ok for c in sig.conditions)


def test_signal_carries_readable_evidence() -> None:
    sig = fired(daily=series(list(flat(64, 100)) + [130]))

    assert sig is not None
    labels = [c.label for c in sig.conditions]
    assert any("월봉" in label for label in labels)
    assert any("주봉" in label for label in labels)
    assert any("일봉" in label for label in labels)
    assert all(c.actual for c in sig.conditions), "근거값이 빈 조건이 있으면 화면이 비어 보인다"


# ── 음성: 조건별로 하나씩 깨뜨린다 ──────────────────────────────


def test_monthly_close_below_ma20_does_not_fire() -> None:
    monthly = series(list(rising(23, start=100, step=5)) + [50])
    assert fired(monthly=monthly) is None


def test_monthly_ma20_not_rising_does_not_fire() -> None:
    """월선이 눕거나 꺾이면 장기 추세가 아니다."""
    monthly = series(list(rising(23, start=200, step=-5)) + [300])
    assert fired(monthly=monthly) is None


def test_weekly_ma20_below_ma60_does_not_fire() -> None:
    weekly = series(list(rising(70, start=200, step=-2)) + [400])
    assert fired(weekly=weekly) is None


def test_daily_close_below_ma20_does_not_fire() -> None:
    daily = series(list(rising(69, start=100, step=1)) + [50])
    assert fired(daily=daily) is None


def test_daily_ma20_below_ma60_does_not_fire() -> None:
    daily = series(list(rising(70, start=200, step=-1)) + [400])
    assert fired(daily=daily) is None


# ── 음성: 신규 진입만 알린다 ────────────────────────────────────


def test_already_aligned_yesterday_does_not_fire() -> None:
    """몇 달째 정배열인 종목을 매일 보내면 알림이 무의미해진다 (SPEC F5)."""
    assert fired(daily=good_daily()) is None


def test_transition_day_fires_but_the_next_day_does_not() -> None:
    """전환 다음 날에는 이미 어제도 충족이므로 조용해야 한다."""
    base = list(flat(64, 100))
    transition = series(base + [130])
    day_after = series(base + [130, 131])

    assert fired(daily=transition) is not None
    assert fired(daily=day_after) is None


# ── 음성: 봉 부족은 오류가 아니라 skip ──────────────────────────


def test_short_monthly_history_is_skipped() -> None:
    """월봉 21개가 안 되면 전월 MA20을 만들 수 없다."""
    assert fired(monthly=series(rising(15, start=100, step=5))) is None


def test_short_weekly_history_is_skipped() -> None:
    assert fired(weekly=series(rising(30, start=100, step=2))) is None


def test_short_daily_history_is_skipped() -> None:
    assert fired(daily=series(rising(30, start=100, step=1))) is None


def test_empty_barset_is_skipped() -> None:
    assert mtf.evaluate(meta(), barset()) is None


# ── 점수 ────────────────────────────────────────────────────────


def test_score_prefers_the_less_extended_stock() -> None:
    """막 전환해 덜 오른 종목을 위로 올린다 (SPEC F5)."""
    base = list(flat(64, 100))
    near = fired(daily=series(base + [112]))
    far = fired(daily=series(base + [180]))

    assert near is not None and far is not None
    assert near.score > far.score


# ── 실행 주기 ───────────────────────────────────────────────────


def test_mtf_runs_every_day() -> None:
    assert mtf.runs_on(date(2026, 8, 14), date(2026, 8, 17))
    assert mtf.runs_on(date(2026, 8, 17), date(2026, 8, 18))
