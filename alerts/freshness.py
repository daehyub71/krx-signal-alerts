"""데이터 신선도 판정 (SPEC F3) — 순수 함수.

낡은 데이터로 만든 신호를 보내지 않는다. 다만 **침묵하지도 않는다** —
판정 결과는 "데이터 지연"으로 알린다 (D10).
"""

from __future__ import annotations

from datetime import date, timedelta

SATURDAY = 5


def weekdays_between(start: date, end: date) -> int:
    """`start`와 `end` **사이**의 평일 수 (양 끝 제외).

    Args:
        start: 시작일.
        end: 종료일.

    Returns:
        두 날짜 사이에 낀 평일 수. `end <= start`면 0.
    """
    n = 0
    cur = start + timedelta(days=1)
    while cur < end:
        if cur.weekday() < SATURDAY:
            n += 1
        cur += timedelta(days=1)
    return n


def is_stale(data_date: date | None, run_date: date) -> bool:
    """데이터가 낡았는가.

    Args:
        data_date: `ksc_bars`의 실제 최신 거래일. None이면 데이터가 없는 것이다.
        run_date: 배치 기준일.

    Returns:
        낡았으면 True.

    Note:
        평일이 하루라도 사이에 끼면 낡은 것으로 본다. **공휴일을 모르므로**
        연휴 다음 날에는 멀쩡한 데이터를 낡았다고 볼 수 있다.

        일부러 이쪽으로 틀리게 했다. 잘못 "최신"이라고 보면 **낡은 데이터로 만든
        신호를 보내게** 되고, 잘못 "낡음"이라고 보면 그날 알림 한 통이 "데이터 지연"으로
        올 뿐이다. 두 오류의 값이 다르다.
    """
    if data_date is None:
        return True
    if data_date >= run_date:
        return False
    return weekdays_between(data_date, run_date) > 0
