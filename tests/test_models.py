"""models — evidence 공유 계약 (PLAN §4).

`evidence` 키 이름은 배치와 웹이 만나는 유일한 지점이다.
이름을 바꾸면 과거 이력이 통째로 깨지므로 여기서 못 박아 둔다.
"""

from __future__ import annotations

from datetime import date

from alerts.models import STRATEGY_LABELS, STRATEGY_NAMES, Bar, BarSet, Condition, Signal


def test_evidence_shape_is_the_web_contract() -> None:
    sig = Signal(
        d=date(2026, 8, 17),
        strategy="mtf",
        ticker="005930",
        name="삼성전자",
        score=0.82,
        conditions=(
            Condition(label="월봉 종가 > MA20", ok=True, actual="71,200 > 68,430"),
            Condition(label="주봉 MA20 > MA60", ok=False, actual="69,100 < 70,050"),
        ),
        close=71200,
        change_pct=2.14,
        volume=12_345_678,
        amount=879_000_000_000,
    )
    ev = sig.evidence()

    assert set(ev) == {"conditions", "price", "volume", "meta"}
    assert ev["conditions"][0] == {
        "label": "월봉 종가 > MA20",
        "ok": True,
        "actual": "71,200 > 68,430",
    }
    assert ev["price"] == {"close": 71200, "change_pct": 2.14}
    assert ev["volume"] == {"value": 12_345_678, "amount": 879_000_000_000}
    assert ev["meta"] == {"in_progress": False}


def test_evidence_actual_is_a_string() -> None:
    """숫자 포맷을 배치에서 확정한다 — 메일과 웹이 다르게 보이면 안 된다."""
    sig = Signal(
        d=date(2026, 8, 17),
        strategy="vcp",
        ticker="000660",
        name="SK하이닉스",
        score=0.5,
        conditions=(Condition(label="거래량 수축", ok=True, actual="0.24배"),),
    )
    assert isinstance(sig.evidence()["conditions"][0]["actual"], str)


def test_barset_by_timeframe() -> None:
    bar = Bar(d=date(2026, 8, 14), o=1, h=2, low=1, c=2, v=10)
    bs = BarSet(ticker="005930", daily=(bar,), weekly=(), monthly=(bar, bar))

    assert bs.by_timeframe("D") == (bar,)
    assert bs.by_timeframe("W") == ()
    assert len(bs.by_timeframe("M")) == 2


def test_every_strategy_has_a_label() -> None:
    assert set(STRATEGY_LABELS) == set(STRATEGY_NAMES)


def test_signal_carries_the_name_for_the_web() -> None:
    """`ksa_signals`에 외래키가 없어 웹이 조인을 못 한다. 이름을 함께 저장한다 (DESIGN §1)."""
    from alerts.models import Signal

    sig = Signal(d=date(2026, 8, 17), strategy="mtf", ticker="005930",
                 name="삼성전자", score=1.0)
    assert sig.name == "삼성전자"


def test_display_values_always_come_from_the_daily_bar() -> None:
    """전략마다 기준 봉이 달라도 표의 공통 열은 비교 가능해야 한다.

    주봉 눌림목이 주간 거래대금을, MTF가 일간 거래대금을 담으면
    한 표에서 거래대금 정렬이 무의미해진다 (2026-08-17 화면에서 발견).
    """
    from alerts.models import BarSet, TickerMeta
    from alerts.strategies.base import Checks, make_signal

    daily = Bar(d=date(2026, 8, 14), o=100, h=110, low=95, c=105, v=1000, a=105_000)
    prev = Bar(d=date(2026, 8, 13), o=100, h=100, low=100, c=100, v=900, a=90_000)
    weekly = Bar(d=date(2026, 8, 14), o=80, h=110, low=80, c=105, v=9000, a=945_000)

    bars = BarSet(ticker="005930", daily=(prev, daily), weekly=(weekly,))
    sig = make_signal(
        TickerMeta(ticker="005930", name="삼성전자", market="KOSPI"),
        "pullback", bars, 1.0, Checks(),
    )

    assert sig.amount == 105_000, "주봉 합계(945,000)가 아니라 일봉 값이어야 한다"
    assert sig.volume == 1000
    assert sig.change_pct == 5.0, "전일 대비여야 한다 (주간 대비가 아니라)"
