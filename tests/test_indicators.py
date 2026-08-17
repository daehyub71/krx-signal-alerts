"""indicators — 손계산 대조.

여기가 틀리면 전략 다섯 개가 전부 틀린다. 값을 눈으로 검산할 수 있는 수만 쓴다.
"""

from __future__ import annotations

import pytest

from alerts.indicators import bollinger, quantile, sma

# ── sma ─────────────────────────────────────────────────────────


def test_sma_warmup_is_none_not_zero() -> None:
    """워밍업 구간을 0으로 채우면 전략이 '종가 > MA'를 항상 참으로 본다."""
    assert sma([1.0, 2.0, 3.0, 4.0], 3) == [None, None, 2.0, 3.0]


def test_sma_matches_hand_calculation() -> None:
    # (10+20+30)/3 = 20, (20+30+40)/3 = 30, (30+40+50)/3 = 40
    assert sma([10.0, 20.0, 30.0, 40.0, 50.0], 3) == [None, None, 20.0, 30.0, 40.0]


def test_sma_period_one_is_the_series_itself() -> None:
    assert sma([3.0, 1.0, 4.0], 1) == [3.0, 1.0, 4.0]


def test_sma_shorter_than_period_is_all_none() -> None:
    """봉이 모자란 종목은 오류가 아니라 정상 skip이다 (SPEC F9 주석)."""
    assert sma([1.0, 2.0], 5) == [None, None]


def test_sma_preserves_input_length() -> None:
    """길이가 어긋나면 봉과 지표의 인덱스가 밀려 조용히 틀린다."""
    values = [float(i) for i in range(30)]
    assert len(sma(values, 20)) == len(values)


def test_sma_rejects_non_positive_period() -> None:
    with pytest.raises(ValueError):
        sma([1.0, 2.0], 0)


# ── bollinger ───────────────────────────────────────────────────


def test_bollinger_on_a_flat_series_has_zero_width() -> None:
    """변동이 없으면 밴드폭이 0이다. 스퀴즈 판정의 극단값."""
    band = bollinger([100.0] * 5, period=5, k=2.0)[-1]
    assert band is not None
    assert band.mid == 100.0
    assert band.upper == 100.0
    assert band.lower == 100.0
    assert band.width == 0.0


def test_bollinger_matches_hand_calculation() -> None:
    # [2,4,4,4,5,5,7,9] → 평균 5, 모표준편차 2 (ddof=0)
    band = bollinger([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0], period=8, k=2.0)[-1]
    assert band is not None
    assert band.mid == 5.0
    assert band.upper == 9.0  # 5 + 2*2
    assert band.lower == 1.0  # 5 - 2*2
    assert band.width == pytest.approx(8.0 / 5.0)  # (9-1)/5


def test_bollinger_warmup_is_none() -> None:
    bands = bollinger([1.0, 2.0, 3.0], period=3)
    assert bands[0] is None
    assert bands[1] is None
    assert bands[2] is not None


def test_bollinger_uses_population_stdev() -> None:
    """표본 표준편차(ddof=1)를 쓰면 밴드가 넓어져 스퀴즈 백분위가 통째로 달라진다."""
    band = bollinger([1.0, 2.0, 3.0], period=3, k=1.0)[-1]
    assert band is not None
    # 모표준편차 = sqrt(2/3) ≈ 0.8165 (표본이면 1.0)
    assert band.upper == pytest.approx(2.0 + 0.816496, abs=1e-5)


def test_bollinger_width_is_none_safe_on_zero_mid() -> None:
    """가격은 0일 수 없지만, 0으로 나누기가 배치를 죽이게 두지 않는다."""
    band = bollinger([0.0] * 3, period=3)[-1]
    assert band is not None
    assert band.width == 0.0


# ── quantile ────────────────────────────────────────────────────


def test_quantile_picks_the_low_end() -> None:
    """스퀴즈는 '최근 52주 중 하위 10%'를 본다 (F8)."""
    values = [float(i) for i in range(1, 101)]  # 1..100
    assert quantile(values, 0.10) == pytest.approx(10.9, abs=0.2)


def test_quantile_median() -> None:
    assert quantile([1.0, 2.0, 3.0], 0.5) == 2.0


def test_quantile_endpoints() -> None:
    values = [5.0, 1.0, 3.0]
    assert quantile(values, 0.0) == 1.0
    assert quantile(values, 1.0) == 5.0


def test_quantile_single_value() -> None:
    assert quantile([7.0], 0.3) == 7.0


def test_quantile_rejects_empty() -> None:
    with pytest.raises(ValueError):
        quantile([], 0.5)
