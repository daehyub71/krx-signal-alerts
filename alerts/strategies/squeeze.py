"""F8 — 밴드 스퀴즈 & 확장.

주봉 볼린저밴드가 52주 중 가장 좁아졌다가 상단을 뚫는 주.

주봉 기반이지만 **매일 판정한다** — 진행 중인 주봉이 매일 갱신되므로 주중에도 돌파가 잡힌다.
다만 주가 끝나기 전에 뒤집힐 수 있으므로 `in_progress=True`로 표시해 본문에 `(진행중)`을 적는다.
"""

from __future__ import annotations

from datetime import date

from alerts.indicators import bollinger, quantile
from alerts.models import BarSet, Signal, StrategyName, TickerMeta
from alerts.strategies.base import Checks, make_signal, ratio, won

name: StrategyName = "squeeze"

PERIOD = 20
K = 2.0
LOOKBACK = 52  # 밴드폭 분포를 만드는 창
SQUEEZE_Q = 0.10  # 하위 10 백분위 이하
AMOUNT_MULT = 1.5  # 거래대금 확인 배수
AMOUNT_WINDOW = 4

MIN_WEEKLY = PERIOD + LOOKBACK


def runs_on(data_date: date, run_date: date) -> bool:
    """매일 돈다."""
    return True


def evaluate(meta: TickerMeta, bars: BarSet) -> Signal | None:
    """한 종목을 판정한다.

    Returns:
        스퀴즈 뒤 상단 돌파 주면 `Signal`, 아니면 None.
    """
    if len(bars.weekly) < MIN_WEEKLY + 1:
        return None

    closes = [float(b.c) for b in bars.weekly]
    bands = bollinger(closes, PERIOD, K)
    now, prev = bands[-1], bands[-2]
    if now is None or prev is None:
        return None

    # 직전 주 밴드폭이 최근 52주 분포에서 어디쯤인가.
    # 직전 주 자신을 포함해야 "지금이 그 바닥이다"를 말할 수 있다.
    history = [b.width for b in bands[-LOOKBACK - 1 : -1] if b is not None]
    if len(history) < LOOKBACK:
        return None
    threshold = quantile(history, SQUEEZE_Q)

    amounts = [float(b.a or 0) for b in bars.weekly]
    base_amount = sum(amounts[-AMOUNT_WINDOW - 1 : -1]) / AMOUNT_WINDOW
    amount_mult = amounts[-1] / base_amount if base_amount else 0.0

    ck = Checks()
    ck.add(
        f"직전 주 밴드폭이 52주 하위 {int(SQUEEZE_Q * 100)}%",
        prev.width <= threshold,
        f"{prev.width:.4f} vs 기준 {threshold:.4f}",
    )
    ck.add("이번 주 밴드 확장", now.width > prev.width, f"{prev.width:.4f} → {now.width:.4f}")
    ck.add("종가가 상단 밴드 돌파", closes[-1] > now.upper,
           f"{won(closes[-1])} vs 상단 {won(now.upper)}")
    ck.add(
        f"거래대금 {AMOUNT_MULT}배 이상",
        amount_mult >= AMOUNT_MULT,
        f"{ratio(amount_mult)} (4주 평균 대비)",
    )

    if not ck.all_ok:
        return None

    expansion = now.width / prev.width if prev.width else 1.0
    score = expansion * amount_mult

    return make_signal(meta, name, bars, score, ck, in_progress=True)
