"""전략 실행 주기 판정 — 순수 함수.

주봉 전략(F6)은 주가 닫힌 뒤에, 월봉 전략(F9)은 월이 닫힌 뒤에만 돈다.
진행 중인 봉으로 판정하면 다음 날 뒤집힌다.

**요일·날짜로 판정하지 않는다.** "금요일에 돈다"고 하면 금요일이 공휴일인 주를
통째로 건너뛴다. 대신 **데이터 기준일과 실행일이 다른 주/달에 있는지**를 본다 —
그러면 그 주의 마지막 거래일이 목요일이든 수요일이든 정확히 한 번 잡힌다.
"""

from __future__ import annotations

from datetime import date


def week_closed(data_date: date, run_date: date) -> bool:
    """데이터 기준일이 속한 주가 닫혔는가.

    Args:
        data_date: 마지막 거래일 (주봉의 마지막 봉이 덮는 날).
        run_date: 배치 실행일.

    Returns:
        두 날짜가 서로 다른 ISO 주에 있으면 True.

    Example:
        금요일(08-14) 데이터로 월요일(08-17)에 돌면 True — 그 주는 끝났다.
        월요일(08-17) 데이터로 화요일(08-18)에 돌면 False — 아직 주중이다.
    """
    return data_date.isocalendar()[:2] != run_date.isocalendar()[:2]


def month_closed(data_date: date, run_date: date) -> bool:
    """데이터 기준일이 속한 달이 닫혔는가.

    Args:
        data_date: 마지막 거래일.
        run_date: 배치 실행일.

    Returns:
        두 날짜가 서로 다른 달에 있으면 True.

    Note:
        월말 거래일이 며칠인지 알 필요가 없다. 달이 바뀐 첫 실행에서 한 번만 참이 된다.
    """
    return (data_date.year, data_date.month) != (run_date.year, run_date.month)
