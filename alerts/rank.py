"""F10 중복 억제 · F11 랭킹 — 순수 함수.

DB를 모른다. 최근 신호 키를 받아 판정만 한다 — 조회는 노드가 한다.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import date, timedelta

from alerts.models import Signal, StrategyName

# 같은 종목·전략을 며칠 안에 다시 알리지 않는가 (F10).
# 산출 주기가 긴 전략일수록 길게 잡는다 — 월 1회 전략을 10일로 두면 의미가 없다.
SUPPRESS_DAYS: dict[StrategyName, int] = {
    "mtf": 10,
    "vcp": 10,
    "squeeze": 10,
    "pullback": 28,
    "turnaround": 90,
}
DEFAULT_SUPPRESS_DAYS = 10

# 이력을 얼마나 거슬러 읽을지 — 가장 긴 창에 맞춘다.
MAX_SUPPRESS_DAYS = max(SUPPRESS_DAYS.values())

# 카카오 한 통에 담을 상한 (D8). 나머지는 메일과 웹에서 본다.
KAKAO_LIMIT = 10


def suppress(
    signals: Sequence[Signal],
    recent: Iterable[tuple[str, str, date]],
) -> list[Signal]:
    """최근에 이미 나온 신호를 발송 대상에서 뺀다 (F10).

    Args:
        signals: 오늘 판정된 신호.
        recent: `ksa_signals`에서 읽은 (종목, 전략, 날짜) 키.

    Returns:
        `suppressed` 플래그가 채워진 신호 목록. **저장은 하되 발송만 뺀다** —
        웹 이력에서는 보여야 한다.

    Note:
        같은 날짜의 기존 행은 억제 근거로 쓰지 않는다. 배치를 두 번 돌렸을 때
        두 번째 실행이 전부 억제되면 멱등이 깨진다 (SPEC N6).
    """
    seen = list(recent)
    out: list[Signal] = []
    for sig in signals:
        window = SUPPRESS_DAYS.get(sig.strategy, DEFAULT_SUPPRESS_DAYS)
        cutoff = sig.d - timedelta(days=window)
        hit = any(
            ticker == sig.ticker and strategy == sig.strategy and cutoff <= d < sig.d
            for ticker, strategy, d in seen
        )
        out.append(replace(sig, suppressed=hit) if hit else sig)
    return out


def _percentile_within(scores: list[float], value: float) -> float:
    """같은 전략 안에서 이 점수가 상위 몇 %인가 (0.0 ~ 1.0).

    전략마다 점수 스케일이 완전히 다르다 — VCP는 0~1, 턴어라운드는 3~30이다.
    그대로 합쳐 정렬하면 스케일이 큰 전략이 상위를 독식한다.
    """
    if len(scores) <= 1:
        return 1.0
    below = sum(1 for s in scores if s < value)
    return below / (len(scores) - 1)


def rank(signals: Sequence[Signal], limit: int = KAKAO_LIMIT) -> tuple[list[Signal], list[Signal]]:
    """정규화해 정렬하고 발송 상한을 적용한다 (F11).

    Args:
        signals: 억제 판정이 끝난 신호.
        limit: 카카오에 담을 상한.

    Returns:
        `(전체 정렬본, 카카오용 상위 N건)`. 전체에는 억제된 신호도 순위 없이 들어간다.

    Note:
        상위 N건에 **전략별 최소 1건을 보장**한다. 한 전략이 상위를 독식하면
        나머지 전략의 신호를 영영 못 본다.
    """
    live = [s for s in signals if not s.suppressed]
    by_strategy: dict[StrategyName, list[float]] = {}
    for s in live:
        by_strategy.setdefault(s.strategy, []).append(s.score)

    scored = sorted(
        (
            (_percentile_within(by_strategy[s.strategy], s.score), s.amount, s)
            for s in live
        ),
        key=lambda t: (-t[0], -t[1], t[2].ticker),
    )
    ordered = [s for _, _, s in scored]

    # 전략별 대표 1건을 먼저 자리 잡고, 남은 자리를 순위대로 채운다.
    picked: list[Signal] = []
    for name in dict.fromkeys(s.strategy for s in ordered):
        picked.append(next(s for s in ordered if s.strategy == name))
    picked = picked[:limit]
    for s in ordered:
        if len(picked) >= limit:
            break
        if s not in picked:
            picked.append(s)

    top = sorted(picked, key=lambda s: ordered.index(s))
    numbered = {id(s): i + 1 for i, s in enumerate(top)}
    all_ranked = [
        replace(s, rank_no=numbered.get(id(s)), sent_kakao=id(s) in numbered) for s in ordered
    ]
    suppressed = [s for s in signals if s.suppressed]
    return all_ranked + suppressed, [s for s in all_ranked if s.sent_kakao]
