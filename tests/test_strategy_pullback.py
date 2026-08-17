"""F6 주봉 추세 눌림목.

상승 추세 중 20주선까지 밀렸다가 아래꼬리를 달고 되돌린 주.
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, Signal
from alerts.strategies import pullback
from tests.conftest import bar, barset, meta

BASE_V = 1_000_000


def uptrend(n: int = 70, start: float = 100.0, step: float = 2.0) -> list[Bar]:
    """MA20 > MA60이고 MA60도 오르는 주봉 배열."""
    return [bar(start + step * i, day=i * 7, v=BASE_V) for i in range(n)]


def scenario(
    *,
    low: float | None = None,
    close: float | None = None,
    open_: float | None = None,
    high: float | None = None,
    volume: int = 600_000,
    trend: list[Bar] | None = None,
) -> tuple[Bar, ...]:
    """추세 뒤에 '눌림목 주' 하나를 붙인다.

    기본값은 전부 통과하는 양성 시나리오다. 인자 하나만 바꿔 음성을 만든다.
    """
    bars = list(trend if trend is not None else uptrend())
    n = len(bars)
    # 이 시점 MA20 근처가 대략 어디인지 알고 값을 잡는다 (step 2, 20주 → 약 -19)
    last_close = bars[-1].c
    c = close if close is not None else last_close + 2
    return tuple(
        [
            *bars,
            bar(
                c,
                day=n * 7,
                o=open_ if open_ is not None else c + 4,
                h=high if high is not None else c + 5,
                low=low if low is not None else c - 30,
                v=volume,
            ),
        ]
    )


def fired(weekly: tuple[Bar, ...] | None = None) -> Signal | None:
    return pullback.evaluate(meta(), barset(weekly=weekly if weekly is not None else scenario()))


# ── 양성 ────────────────────────────────────────────────────────


def test_pullback_with_long_tail_and_dry_volume_fires() -> None:
    sig = fired()

    assert sig is not None
    assert sig.strategy == "pullback"
    assert all(c.ok for c in sig.conditions)


# ── 음성: 조건별 ────────────────────────────────────────────────


def test_downtrend_does_not_fire() -> None:
    """MA20이 MA60 아래면 눌림목이 아니라 하락이다."""
    down = [bar(300 - 2 * i, day=i * 7, v=BASE_V) for i in range(70)]
    assert fired(scenario(trend=down)) is None


def test_flat_ma60_does_not_fire() -> None:
    """MA60이 눕고 있으면 추세가 아니다."""
    flat_trend = [bar(100, day=i * 7, v=BASE_V) for i in range(70)]
    assert fired(scenario(trend=flat_trend)) is None


def test_low_never_touches_ma20_does_not_fire() -> None:
    """20선까지 안 밀렸으면 눌림목이 아니다.

    이 시나리오의 MA20은 약 221이다. 저가 232는 허용치(225)를 넘지만
    꼬리 비율은 여전히 통과하므로 **터치 조건만** 떨어진다.
    """
    assert fired(scenario(low=232)) is None


def test_close_below_ma20_does_not_fire() -> None:
    """되돌리지 못하고 20선 아래에서 끝나면 실패한 눌림목이다."""
    assert fired(scenario(close=150, open_=155, high=156, low=140)) is None


def test_short_lower_tail_does_not_fire() -> None:
    """아래꼬리가 짧으면 매수세가 들어온 증거가 약하다."""
    sig = fired(scenario(low=None, open_=None, high=None))
    assert sig is not None  # 기본은 통과

    # 꼬리를 없앤다: 저가 = min(시가, 종가)
    trend = uptrend()
    c = trend[-1].c + 2
    no_tail = (*trend, bar(c, day=len(trend) * 7, o=c + 4, h=c + 5, low=c, v=600_000))
    assert fired(no_tail) is None


def test_high_volume_does_not_fire() -> None:
    """거래량이 붙은 하락은 눌림목이 아니라 이탈일 수 있다."""
    assert fired(scenario(volume=3_000_000)) is None


# ── 음성: 봉 부족 ───────────────────────────────────────────────


def test_short_history_is_skipped() -> None:
    assert fired(scenario(trend=uptrend(n=30))) is None


def test_empty_barset_is_skipped() -> None:
    assert pullback.evaluate(meta(), barset()) is None


# ── 점수 ────────────────────────────────────────────────────────


def test_score_prefers_longer_tail_and_drier_volume() -> None:
    strong = fired(scenario(low=None, volume=300_000))
    weak = fired(scenario(low=None, volume=780_000))

    assert strong is not None and weak is not None
    assert strong.score > weak.score


# ── 실행 주기 ───────────────────────────────────────────────────


def test_pullback_only_runs_after_the_week_closes() -> None:
    """진행 중인 주봉으로 판정하면 다음 날 뒤집힌다 (SPEC F6)."""
    assert pullback.runs_on(date(2026, 8, 14), date(2026, 8, 17))  # 금 → 월
    assert not pullback.runs_on(date(2026, 8, 18), date(2026, 8, 19))  # 주중


def test_pullback_runs_when_friday_was_a_holiday() -> None:
    """목요일이 그 주 마지막 거래일이어도 놓치지 않는다."""
    assert pullback.runs_on(date(2026, 12, 24), date(2026, 12, 28))
