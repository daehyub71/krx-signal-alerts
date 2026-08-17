"""유니버스 선정 (SPEC F1) — 순수 함수.

전 종목에서 전략이 성립하지 않는 종목을 뺀다.
DB를 모른다 — 종목 목록과 거래대금 사전을 받아 판정만 한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from alerts.models import TickerMeta

# 20일 평균 거래대금 하한. 저가·소외주의 거래량 급증 오탐을 막는다.
# 초기값이며 M2 드라이런에서 실측 분포를 보고 조정한다 (SPEC R8).
MIN_AMOUNT_KRW = 500_000_000


class ExcludeReason(StrEnum):
    """제외 사유. 사유별 건수를 로그로 남겨야 필터가 과했는지 알 수 있다."""

    SPAC = "spac"
    PREFERRED = "preferred"
    ILLIQUID = "illiquid"
    NO_DATA = "no_data"


@dataclass(slots=True)
class UniverseResult:
    """유니버스 판정 결과."""

    kept: list[TickerMeta] = field(default_factory=list)
    excluded: dict[ExcludeReason, int] = field(default_factory=dict)

    def summary(self) -> str:
        """로그 한 줄."""
        parts = ", ".join(f"{r.value} {n}" for r, n in sorted(self.excluded.items()))
        return f"유니버스 {len(self.kept)}종목 (제외: {parts or '없음'})"


def is_spac(name: str) -> bool:
    """스팩인가.

    합병 전까지 공모가 근처에 묶여 있어 추세 전략이 성립하지 않는다.
    """
    return "스팩" in name


def is_preferred(ticker: str, name: str = "") -> bool:
    """우선주인가.

    Args:
        ticker: 6자리 종목 코드.
        name: 종목명. 현재 판정에 쓰지 않는다 — 아래 Note 참조.

    Returns:
        우선주면 True.

    Note:
        **티커 6번째 자리만 본다.** KRX 보통주는 0으로 끝나고, 우선주는
        1/5/7 또는 신형우선주의 `K`·`B` 등으로 끝난다.

        이름으로 판정하면 안 된다 — `미래에셋대우`처럼 '우'로 끝나는 보통주가 있어
        멀쩡한 종목이 통째로 빠진다. SPEC F1은 이름 규칙을 OR로 적었지만,
        실제로 넣어 보면 오탐이 나서 티커 규칙만 쓴다 (2026-08-17).
    """
    return len(ticker) == 6 and ticker[5] != "0"


def build(
    tickers: Sequence[TickerMeta],
    amounts: Mapping[str, int],
    min_amount: int = MIN_AMOUNT_KRW,
) -> UniverseResult:
    """유니버스를 만든다.

    Args:
        tickers: 전 종목 메타.
        amounts: 종목별 최근 20거래일 평균 거래대금(원). 없는 종목은 데이터 부족으로 본다.
        min_amount: 거래대금 하한. 이 값 **이상**이면 남긴다.

    Returns:
        남은 종목과 사유별 제외 건수. 입력 순서를 유지한다 (멱등 — SPEC N6).

    Note:
        사유는 **한 종목당 하나만** 센다. 스팩이면서 거래대금도 미달인 종목을
        두 번 세면 합계가 입력 수와 맞지 않아 필터를 검산할 수 없다.
    """
    result = UniverseResult()

    def drop(reason: ExcludeReason) -> None:
        result.excluded[reason] = result.excluded.get(reason, 0) + 1

    for meta in tickers:
        if is_spac(meta.name):
            drop(ExcludeReason.SPAC)
        elif is_preferred(meta.ticker, meta.name):
            drop(ExcludeReason.PREFERRED)
        elif meta.ticker not in amounts:
            drop(ExcludeReason.NO_DATA)
        elif amounts[meta.ticker] < min_amount:
            drop(ExcludeReason.ILLIQUID)
        else:
            result.kept.append(meta)

    return result
