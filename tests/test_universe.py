"""universe — F1 유니버스 필터.

실제로 존재하는 함정을 케이스로 박아 둔다.
"""

from __future__ import annotations

from alerts.models import TickerMeta
from alerts.universe import ExcludeReason, build, is_preferred, is_spac

MIN_AMOUNT = 500_000_000  # 5억


def t(ticker: str, name: str, market: str = "KOSPI") -> TickerMeta:
    return TickerMeta(ticker=ticker, name=name, market=market)


# ── 스팩 ────────────────────────────────────────────────────────


def test_spac_is_detected_by_name() -> None:
    assert is_spac("교보14호스팩")
    assert is_spac("하나금융25호스팩")


def test_ordinary_names_are_not_spac() -> None:
    assert not is_spac("삼성전자")
    assert not is_spac("SK하이닉스")


# ── 우선주 ──────────────────────────────────────────────────────


def test_preferred_is_detected_by_ticker_suffix() -> None:
    """KRX 우선주는 6번째 자리가 0이 아니다."""
    assert is_preferred("005935", "삼성전자우")
    assert is_preferred("000215", "DL우")
    assert is_preferred("00088K", "한화3우B")  # 신형우선주는 문자로 끝난다


def test_common_stock_is_not_preferred() -> None:
    assert not is_preferred("005930", "삼성전자")
    assert not is_preferred("000660", "SK하이닉스")


def test_letter_ticker_common_stock_is_not_preferred() -> None:
    """0126Z0(삼성에피스홀딩스)처럼 문자가 섞인 보통주가 실재한다.

    티커를 숫자로 가정하면 종목이 조용히 누락된다.
    """
    assert not is_preferred("0126Z0", "삼성에피스홀딩스")


def test_name_ending_in_woo_is_not_enough() -> None:
    """'미래에셋대우'는 이름이 '우'로 끝나지만 보통주다.

    이름만으로 판정하면 멀쩡한 종목이 통째로 빠진다.
    """
    assert not is_preferred("006800", "미래에셋대우")


# ── build ───────────────────────────────────────────────────────


def test_build_keeps_liquid_common_stocks() -> None:
    tickers = [t("005930", "삼성전자"), t("000660", "SK하이닉스", "KOSPI")]
    amounts = {"005930": 8_000_000_000_000, "000660": 3_000_000_000_000}

    result = build(tickers, amounts, min_amount=MIN_AMOUNT)

    assert [m.ticker for m in result.kept] == ["005930", "000660"]
    assert result.excluded == {}


def test_build_excludes_each_reason_and_counts_it() -> None:
    tickers = [
        t("005930", "삼성전자"),
        t("005935", "삼성전자우"),
        t("123456", "교보14호스팩"),
        t("111110", "소외주"),
        t("222220", "봉없는종목"),
    ]
    amounts = {
        "005930": 8_000_000_000_000,
        "005935": 900_000_000,
        "123456": 900_000_000,
        "111110": 100_000_000,  # 1억 — 하한 미달
        # 222220은 거래대금 자체가 없다 (신규 상장 등)
    }

    result = build(tickers, amounts, min_amount=MIN_AMOUNT)

    assert [m.ticker for m in result.kept] == ["005930"]
    assert result.excluded[ExcludeReason.PREFERRED] == 1
    assert result.excluded[ExcludeReason.SPAC] == 1
    assert result.excluded[ExcludeReason.ILLIQUID] == 1
    assert result.excluded[ExcludeReason.NO_DATA] == 1


def test_build_reason_precedence_counts_once() -> None:
    """스팩이면서 거래대금도 미달인 종목이 두 번 세어지면 합계가 안 맞는다."""
    tickers = [t("123456", "교보14호스팩")]
    result = build(tickers, {"123456": 1_000}, min_amount=MIN_AMOUNT)

    assert sum(result.excluded.values()) == 1
    assert result.excluded[ExcludeReason.SPAC] == 1


def test_build_totals_add_up() -> None:
    """제외 합계 + 유지 = 입력. 안 맞으면 어딘가로 종목이 샌 것이다."""
    tickers = [
        t("005930", "삼성전자"), t("005935", "삼성전자우"),
        t("123456", "교보14호스팩"), t("111110", "소외주"), t("222220", "봉없는종목"),
    ]
    amounts = {"005930": 9_9e12, "005935": 9e8, "123456": 9e8, "111110": 1e8}

    result = build(tickers, {k: int(v) for k, v in amounts.items()}, min_amount=MIN_AMOUNT)

    assert len(result.kept) + sum(result.excluded.values()) == len(tickers)


def test_build_boundary_amount_is_inclusive() -> None:
    """하한과 정확히 같으면 남긴다. 경계에서 애매하면 나중에 다투게 된다."""
    tickers = [t("111110", "딱하한")]
    result = build(tickers, {"111110": MIN_AMOUNT}, min_amount=MIN_AMOUNT)

    assert len(result.kept) == 1


def test_build_is_stable_in_input_order() -> None:
    """순서가 흔들리면 같은 날 두 번 돌린 결과가 달라 보인다 (N6 멱등)."""
    # 끝자리는 반드시 0으로 — 아니면 우선주로 걸러진다 (is_preferred)
    tickers = [t(f"1111{i}0", f"종목{i}") for i in range(5)]
    amounts = {m.ticker: 10_000_000_000 for m in tickers}

    a = [m.ticker for m in build(tickers, amounts, MIN_AMOUNT).kept]
    b = [m.ticker for m in build(tickers, amounts, MIN_AMOUNT).kept]

    assert a == b == [m.ticker for m in tickers]
