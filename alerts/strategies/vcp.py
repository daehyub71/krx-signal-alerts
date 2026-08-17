"""F7 — VCP 거래량 수축 (Volatility Contraction Pattern).

장대양봉 뒤 조정 없이 거래량과 변동성만 마르는 구간.

**다섯 전략 중 가장 깨지기 쉽다.** 특히 "몸통 50% 유지"는 판정 기준을 조금만 넓혀도
거의 모든 후보가 탈락한다. 그래서 **종가로만** 판정한다 — 장중 저가로 보면
꼬리 한 번에 패턴이 사라진다 (SPEC F7).
"""

from __future__ import annotations

from datetime import date

from alerts.models import Bar, BarSet, Signal, StrategyName, TickerMeta
from alerts.strategies.base import Checks, make_signal, ratio, won

name: StrategyName = "vcp"

SEARCH_WINDOW = 20  # 기준봉을 찾는 구간
SURGE_GAIN = 0.08  # 장대양봉 최소 상승률
SURGE_VOL_MULT = 2.0  # 기준봉 거래량 배수
VOL_BASE_WINDOW = 20  # 기준봉 거래량을 비교할 직전 평균 구간
MIN_ELAPSED, MAX_ELAPSED = 3, 15  # 기준봉 이후 경과일
HOLD_RATIO = 0.5  # 몸통 유지 비율
TAIL_WINDOW = 3  # 수축을 볼 최근 며칠
VOL_DRY = 0.30  # 거래량 수축 기준
RANGE_DRY = 0.50  # 변동성 수축 기준

MIN_DAILY = VOL_BASE_WINDOW + SEARCH_WINDOW


def runs_on(data_date: date, run_date: date) -> bool:
    """매일 돈다."""
    return True


def _find_base_bar(bars: tuple[Bar, ...]) -> int | None:
    """최근 `SEARCH_WINDOW`일 안에서 가장 최근 장대양봉의 인덱스.

    Returns:
        기준봉 인덱스. 없으면 None.
    """
    for i in range(len(bars) - 1, max(len(bars) - 1 - SEARCH_WINDOW, VOL_BASE_WINDOW) - 1, -1):
        b = bars[i]
        if b.c <= b.o:
            continue
        if (b.c - b.o) / b.o < SURGE_GAIN:
            continue
        prior = bars[i - VOL_BASE_WINDOW : i]
        avg_v = sum(x.v for x in prior) / len(prior) if prior else 0.0
        if avg_v and b.v >= avg_v * SURGE_VOL_MULT:
            return i
    return None


def _range_pct(b: Bar) -> float:
    """종가 대비 고저 폭."""
    return (b.h - b.low) / b.c if b.c else 0.0


def evaluate(meta: TickerMeta, bars: BarSet) -> Signal | None:
    """한 종목을 판정한다.

    Returns:
        기준봉 뒤 수축이 확인되면 `Signal`, 아니면 None.
    """
    daily = bars.daily
    if len(daily) < MIN_DAILY:
        return None

    idx = _find_base_bar(daily)
    if idx is None:
        return None

    base = daily[idx]
    after = daily[idx + 1 :]
    elapsed = len(after)

    ck = Checks()
    ck.add(
        f"기준봉 {base.d} — {SURGE_GAIN:.0%} 이상 장대양봉",
        True,
        f"{won(base.o)} → {won(base.c)} ({(base.c - base.o) / base.o:+.1%})",
    )
    if not ck.add(
        f"기준봉 이후 {MIN_ELAPSED}~{MAX_ELAPSED}일 경과",
        MIN_ELAPSED <= elapsed <= MAX_ELAPSED,
        f"{elapsed}일",
    ):
        return None

    # 거래정지일이 섞이면 "거래량 0.00배 · 변동성 0.00배"가 완벽한 수축으로 잡힌다.
    # 수축은 **거래가 일어나면서** 말라야 수축이다 (2026-08-17 드라이런에서 발견).
    halted = sum(1 for b in after if b.v == 0)
    if not ck.add("수축 구간에 거래정지일 없음", halted == 0, f"정지 {halted}일 / {elapsed}일"):
        return None

    hold_line = base.o + (base.c - base.o) * HOLD_RATIO
    weakest = min(float(b.c) for b in after)
    ck.add(
        f"이후 모든 종가가 몸통 {HOLD_RATIO:.0%} 위 유지",
        weakest >= hold_line,
        f"최저 종가 {won(weakest)} vs 기준선 {won(hold_line)}",
    )

    tail = after[-TAIL_WINDOW:]
    vol_ratio = (sum(b.v for b in tail) / len(tail)) / base.v if base.v else 1.0
    base_range = _range_pct(base)
    range_ratio = (
        (sum(_range_pct(b) for b in tail) / len(tail)) / base_range if base_range else 1.0
    )

    ck.add(
        f"최근 {TAIL_WINDOW}일 거래량이 기준봉의 {VOL_DRY:.0%} 이하",
        vol_ratio <= VOL_DRY,
        ratio(vol_ratio),
    )
    ck.add(
        f"최근 {TAIL_WINDOW}일 변동성이 기준봉의 {RANGE_DRY:.0%} 이하",
        range_ratio <= RANGE_DRY,
        ratio(range_ratio),
    )

    if not ck.all_ok:
        return None

    score = (1.0 - vol_ratio) * (1.0 - range_ratio)

    return make_signal(meta, name, bars, score, ck)
