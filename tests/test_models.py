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
