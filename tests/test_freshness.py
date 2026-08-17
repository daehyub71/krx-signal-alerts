"""freshness — F3 신선도 판정.

경계일에서 틀리기 쉬워 요일을 하나씩 짚는다.
"""

from __future__ import annotations

from datetime import date

from alerts.freshness import is_stale, weekdays_between

FRI = date(2026, 8, 14)
SAT = date(2026, 8, 15)
SUN = date(2026, 8, 16)
MON = date(2026, 8, 17)
TUE = date(2026, 8, 18)
WED = date(2026, 8, 19)


def test_weekdays_between_excludes_both_ends() -> None:
    assert weekdays_between(FRI, MON) == 0  # 토·일만 낀다
    assert weekdays_between(FRI, TUE) == 1  # 월요일 하나
    assert weekdays_between(FRI, WED) == 2  # 월·화


def test_weekdays_between_is_zero_when_end_is_not_after_start() -> None:
    assert weekdays_between(MON, MON) == 0
    assert weekdays_between(TUE, MON) == 0


def test_monday_morning_with_friday_data_is_fresh() -> None:
    """주말을 건너뛴 것은 낡은 게 아니다. 실제 운영에서 가장 흔한 경우다."""
    assert not is_stale(FRI, MON)


def test_tuesday_with_friday_data_is_stale() -> None:
    """월요일 수집이 실패한 상태. 이걸 놓치면 낡은 신호를 보낸다."""
    assert is_stale(FRI, TUE)


def test_same_day_data_is_fresh() -> None:
    assert not is_stale(MON, MON)


def test_future_data_is_not_stale() -> None:
    """드라이런으로 과거 날짜를 돌리면 데이터가 기준일보다 최신일 수 있다."""
    assert not is_stale(WED, MON)


def test_missing_data_is_stale() -> None:
    """데이터가 아예 없으면 신호를 만들 수 없다."""
    assert is_stale(None, MON)


def test_saturday_run_with_friday_data_is_fresh() -> None:
    assert not is_stale(FRI, SAT)


def test_sunday_run_with_friday_data_is_fresh() -> None:
    assert not is_stale(FRI, SUN)
