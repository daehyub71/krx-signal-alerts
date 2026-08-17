"""F5 — MTF 트리플 정배열.

월·주·일 세 시간축이 **동시에** 상승 정렬인 종목. 매일 판정한다.

**전환일만 알린다.** 이미 몇 달째 정배열인 종목을 매일 보내면 알림이 무의미해진다.
"오늘 충족 + 어제 미충족"인 날만 신호로 본다.
"""

from __future__ import annotations

from datetime import date

from alerts.indicators import sma
from alerts.models import Bar, BarSet, Signal, StrategyName, TickerMeta
from alerts.strategies.base import Checks, make_signal, won

name: StrategyName = "mtf"

MONTH_MA = 20
WEEK_FAST, WEEK_SLOW = 20, 60
DAY_FAST, DAY_SLOW = 20, 60

# 전월 MA20과 비교하려면 월봉이 MA 기간보다 하나 더 있어야 한다.
MIN_MONTHLY = MONTH_MA + 1
MIN_WEEKLY = WEEK_SLOW
# 어제 상태를 보려면 일봉도 하나 더 필요하다.
MIN_DAILY = DAY_SLOW + 1


def runs_on(data_date: date, run_date: date) -> bool:
    """매일 돈다."""
    return True


def _closes(bars: tuple[Bar, ...]) -> list[float]:
    return [float(b.c) for b in bars]


def _daily_aligned(closes: list[float], fast: list[float | None],
                   slow: list[float | None], i: int) -> bool:
    """일봉 축이 `i` 시점에 정배열인가."""
    f, s = fast[i], slow[i]
    return f is not None and s is not None and closes[i] > f > s


def evaluate(meta: TickerMeta, bars: BarSet) -> Signal | None:
    """한 종목을 판정한다.

    Args:
        meta: 종목 메타.
        bars: 일·주·월봉.

    Returns:
        정배열로 **전환된 날**이면 `Signal`, 아니면 None.
        봉이 모자라면 None — 오류가 아니라 정상 skip이다.
    """
    if (
        len(bars.monthly) < MIN_MONTHLY
        or len(bars.weekly) < MIN_WEEKLY
        or len(bars.daily) < MIN_DAILY
    ):
        return None

    mc = _closes(bars.monthly)
    m_ma = sma(mc, MONTH_MA)
    wc = _closes(bars.weekly)
    w_fast, w_slow = sma(wc, WEEK_FAST), sma(wc, WEEK_SLOW)
    dc = _closes(bars.daily)
    d_fast, d_slow = sma(dc, DAY_FAST), sma(dc, DAY_SLOW)

    m_now, m_prev = m_ma[-1], m_ma[-2]
    w_f, w_s = w_fast[-1], w_slow[-1]
    d_f, d_s = d_fast[-1], d_slow[-1]
    if m_now is None or m_prev is None or w_f is None or w_s is None:
        return None
    if d_f is None or d_s is None:
        return None

    ck = Checks()
    ck.add("월봉 종가 > MA20", mc[-1] > m_now, f"{won(mc[-1])} vs {won(m_now)}")
    ck.add("월봉 MA20 상승", m_now > m_prev, f"{won(m_now)} vs 전월 {won(m_prev)}")
    ck.add("주봉 종가 > MA20 > MA60", wc[-1] > w_f > w_s,
           f"{won(wc[-1])} > {won(w_f)} > {won(w_s)}")
    ck.add("일봉 종가 > MA20 > MA60", dc[-1] > d_f > d_s,
           f"{won(dc[-1])} > {won(d_f)} > {won(d_s)}")

    # 전환일 판정 — 일봉 축이 어제는 정배열이 아니었어야 한다.
    was_aligned = _daily_aligned(dc, d_fast, d_slow, -2)
    ck.add("어제는 미정배열 (전환일)", not was_aligned,
           "전환" if not was_aligned else "이미 정배열")

    if not ck.all_ok:
        return None

    # 이격도가 작을수록 높은 점수 — 막 전환해 덜 오른 종목을 위로 올린다.
    disparity = (dc[-1] - d_f) / d_f * 100.0
    score = 1.0 / (1.0 + max(disparity, 0.0))

    return make_signal(meta, name, bars.daily, score, ck)
