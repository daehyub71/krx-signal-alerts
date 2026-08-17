"""F7 VCP 거래량 수축.

장대양봉 뒤 몸통 절반을 지키면서 거래량과 변동성만 마르는 구간.
다섯 전략 중 조건이 가장 많고 가장 잘 깨진다.
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, Signal
from alerts.strategies import vcp
from tests.conftest import bar, barset, meta

QUIET_V = 1_000_000
BASE = 100.0


def scenario(
    *,
    surge_gain: float = 0.12,
    surge_volume_mult: float = 3.0,
    days_since: int = 6,
    drift_close: float | None = None,
    tail_volume_mult: float = 0.20,
    tail_range: float = 0.004,
    lead_days: int = 60,
) -> tuple[Bar, ...]:
    """평온 → 장대양봉 → 조용한 수축.

    기본값은 전부 통과하는 양성 시나리오다.
    """
    bars: list[Bar] = []
    for i in range(lead_days):
        bars.append(bar(BASE, day=i, h=int(BASE + 1), low=int(BASE - 1), v=QUIET_V))

    # 장대양봉
    surge_open = BASE
    surge_close = BASE * (1 + surge_gain)
    bars.append(
        bar(
            surge_close,
            day=lead_days,
            o=int(surge_open),
            h=int(surge_close),
            low=int(surge_open),
            v=int(QUIET_V * surge_volume_mult),
        )
    )

    # 이후 조용한 구간 — 몸통 중간값 위에서 버틴다
    mid = surge_open + (surge_close - surge_open) * 0.5
    close = drift_close if drift_close is not None else mid + 3
    half_range = max(close * tail_range / 2, 0.5)
    for j in range(days_since):
        bars.append(
            bar(
                close,
                day=lead_days + 1 + j,
                h=int(close + half_range),
                low=int(close - half_range),
                v=int(QUIET_V * surge_volume_mult * tail_volume_mult),
            )
        )
    return tuple(bars)


def fired(daily: tuple[Bar, ...] | None = None) -> Signal | None:
    return vcp.evaluate(meta(), barset(daily=daily if daily is not None else scenario()))


# ── 양성 ────────────────────────────────────────────────────────


def test_surge_then_contraction_fires() -> None:
    sig = fired()

    assert sig is not None
    assert sig.strategy == "vcp"
    assert all(c.ok for c in sig.conditions)


def test_evidence_names_the_base_bar() -> None:
    """'왜 잡혔나'를 보려면 기준봉이 언제였는지가 있어야 한다."""
    sig = fired()

    assert sig is not None
    assert any("기준봉" in c.label for c in sig.conditions)


# ── 음성: 조건별 ────────────────────────────────────────────────


def test_no_surge_bar_does_not_fire() -> None:
    """8% 미만 상승은 장대양봉이 아니다."""
    assert fired(scenario(surge_gain=0.03)) is None


def test_surge_without_volume_does_not_fire() -> None:
    """거래량이 안 붙은 상승은 기준봉이 될 수 없다."""
    assert fired(scenario(surge_volume_mult=1.2)) is None


def test_too_soon_after_surge_does_not_fire() -> None:
    """3일이 안 지나면 수축을 판정할 표본이 없다."""
    assert fired(scenario(days_since=2)) is None


def test_too_long_after_surge_does_not_fire() -> None:
    """15일을 넘기면 패턴이 소멸한 것으로 본다."""
    assert fired(scenario(days_since=20)) is None


def test_close_below_half_body_does_not_fire() -> None:
    """몸통 절반을 내주면 수축이 아니라 되돌림이다. 이 조건이 가장 잘 깨진다."""
    assert fired(scenario(drift_close=BASE + 1)) is None


def test_volume_not_dry_does_not_fire() -> None:
    """거래량이 기준봉의 30%를 넘으면 마른 게 아니다."""
    assert fired(scenario(tail_volume_mult=0.60)) is None


def test_volatility_not_contracted_does_not_fire() -> None:
    """변동성이 안 줄면 VCP가 아니다."""
    assert fired(scenario(tail_range=0.20)) is None


# ── 음성: 봉 부족 ───────────────────────────────────────────────


def test_short_history_is_skipped() -> None:
    assert fired(scenario(lead_days=20)) is None


def test_empty_barset_is_skipped() -> None:
    assert vcp.evaluate(meta(), barset()) is None


def test_no_bars_after_surge_is_skipped() -> None:
    assert fired(scenario(days_since=0)) is None


# ── 점수 ────────────────────────────────────────────────────────


def test_score_prefers_drier_contraction() -> None:
    dry = fired(scenario(tail_volume_mult=0.05, tail_range=0.002))
    damp = fired(scenario(tail_volume_mult=0.28, tail_range=0.008))

    assert dry is not None and damp is not None
    assert dry.score > damp.score


# ── 실행 주기 ───────────────────────────────────────────────────


def test_vcp_runs_every_day() -> None:
    assert vcp.runs_on(date(2026, 8, 14), date(2026, 8, 17))


# ── 거래정지 (2026-08-17 드라이런에서 발견) ─────────────────────


def halted_tail(days: int = 3) -> tuple[Bar, ...]:
    """장대양봉 뒤 거래정지 — 거래량 0, 시고저가 = 종가."""
    bars = list(scenario(days_since=0))
    last = bars[-1]
    for _ in range(days):
        bars.append(bar(last.c, day=len(bars), o=last.c, h=last.c, low=last.c, v=0))
    return tuple(bars)


def test_halted_days_are_not_a_contraction() -> None:
    """거래정지는 수축이 아니다. 거래량 0·변동폭 0이 '완벽한 수축'으로 잡히던 버그."""
    assert fired(halted_tail()) is None


def test_halted_judgement_day_is_skipped_by_the_registry() -> None:
    """살 수도 없는 종목을 알릴 이유가 없다."""
    from alerts.strategies import BY_NAME

    assert BY_NAME["vcp"].evaluate(meta(), barset(daily=halted_tail())) is None


def test_registry_skips_halted_day_for_every_strategy() -> None:
    from alerts.strategies import ALL

    halted = barset(daily=halted_tail())
    assert all(s.evaluate(meta(), halted) is None for s in ALL)
