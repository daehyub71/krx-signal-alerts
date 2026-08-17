"""schedule — 주·월 마감 판정.

공휴일이 낀 주를 통째로 놓치지 않는지가 핵심이다.
"""

from __future__ import annotations

from datetime import date

from alerts.schedule import month_closed, week_closed


def test_week_is_closed_on_monday_with_friday_data() -> None:
    assert week_closed(date(2026, 8, 14), date(2026, 8, 17))


def test_week_is_open_midweek() -> None:
    """진행 중인 주봉으로 판정하면 다음 날 뒤집힌다."""
    assert not week_closed(date(2026, 8, 18), date(2026, 8, 19))


def test_week_closes_even_when_friday_is_a_holiday() -> None:
    """금요일이 휴장이라 목요일이 마지막 거래일인 주.

    '금요일에 돈다'는 요일 규칙이었다면 이 주를 통째로 건너뛴다.
    """
    thursday = date(2026, 12, 24)
    next_monday = date(2026, 12, 28)
    assert week_closed(thursday, next_monday)


def test_week_boundary_across_the_year() -> None:
    """ISO 주는 연도를 넘어간다. (연, 주) 쌍으로 비교해야 한다."""
    assert week_closed(date(2026, 12, 31), date(2027, 1, 4))


def test_same_iso_week_different_year_is_not_closed() -> None:
    """2026-12-28(월)과 2026-12-31(목)은 같은 ISO 주다."""
    assert not week_closed(date(2026, 12, 28), date(2026, 12, 31))


def test_month_is_closed_on_the_first_run_of_a_new_month() -> None:
    assert month_closed(date(2026, 8, 31), date(2026, 9, 1))


def test_month_is_open_within_the_month() -> None:
    assert not month_closed(date(2026, 8, 14), date(2026, 8, 17))


def test_month_closes_across_the_year() -> None:
    assert month_closed(date(2026, 12, 30), date(2027, 1, 4))


def test_same_month_different_year_is_closed() -> None:
    """(연, 월) 쌍으로 비교하지 않으면 1년 전 데이터를 '이번 달'로 본다."""
    assert month_closed(date(2025, 8, 29), date(2026, 8, 17))
