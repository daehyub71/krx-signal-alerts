"""메시지 본문 생성 (SPEC N10).

**네트워크 없이 형식을 전부 시험한다.** 발송 코드를 쓰기 전에 여기서 다 잡는다.
"""

from __future__ import annotations

from datetime import date

from alerts import render
from alerts.models import Condition, Signal, StrategyName

D = date(2026, 8, 14)


def sig(
    strategy: StrategyName = "mtf",
    ticker: str = "005930",
    name: str = "삼성전자",
    close: int = 71200,
    change: float = 2.14,
    in_progress: bool = False,
) -> Signal:
    return Signal(
        d=D,
        strategy=strategy,
        ticker=ticker,
        name=name,
        score=1.0,
        conditions=(
            Condition(label="월봉 종가 > MA20", ok=True, actual="71,200 vs 68,430"),
            Condition(label="주봉 MA20 > MA60", ok=True, actual="69,100 > 66,880"),
        ),
        close=close,
        change_pct=change,
        in_progress=in_progress,
    )


# ── 카카오 본문 ─────────────────────────────────────────────────


def test_kakao_body_lists_signals_by_strategy() -> None:
    body = render.kakao_body([sig(), sig(strategy="vcp", ticker="000660", name="SK하이닉스")], D)

    assert "08/14" in body
    assert "삼성전자" in body
    assert "SK하이닉스" in body


def test_kakao_body_never_exceeds_the_limit() -> None:
    """200자를 넘으면 카카오가 400을 돌려주고 알림이 통째로 사라진다."""
    many = [sig(ticker=f"{i:05d}0", name=f"아주긴종목이름{i}") for i in range(40)]
    body = render.kakao_body(many, D)

    assert len(body) <= render.KAKAO_MAX_CHARS


def test_kakao_body_signals_that_it_was_truncated() -> None:
    """잘린 걸 모르면 '오늘은 이게 다인가 보다' 하고 넘어간다."""
    many = [sig(ticker=f"{i:05d}0", name=f"종목{i}") for i in range(40)]
    body = render.kakao_body(many, D)

    assert "…" in body or "외" in body


def test_kakao_body_says_none_when_empty() -> None:
    """침묵을 정상 상태로 두지 않는다 (D10)."""
    body = render.kakao_body([], D)

    assert "없음" in body
    assert "08/14" in body


def test_kakao_body_marks_stale_data() -> None:
    body = render.kakao_body([], D, stale=True)

    assert "지연" in body


def test_kakao_body_carries_the_failure_warning() -> None:
    """살아 있는 채널이 죽은 채널을 알려 준다 (F13c)."""
    body = render.kakao_body([sig()], D, warning="메일 발송 실패")

    assert "메일 발송 실패" in body


def test_kakao_body_warning_survives_truncation() -> None:
    """경고가 잘려 나가면 고장을 알릴 방법이 없다."""
    many = [sig(ticker=f"{i:05d}0", name=f"아주긴종목이름{i}") for i in range(40)]
    body = render.kakao_body(many, D, warning="메일 발송 실패")

    assert "메일 발송 실패" in body
    assert len(body) <= render.KAKAO_MAX_CHARS


def test_kakao_body_marks_in_progress_weekly_signals() -> None:
    body = render.kakao_body([sig(strategy="squeeze", in_progress=True)], D)

    assert "진행중" in body


# ── 메일 제목 ───────────────────────────────────────────────────


def test_email_subject_summarizes_at_a_glance() -> None:
    """제목만 보고 오늘 볼지 판단할 수 있어야 한다."""
    subject = render.email_subject([sig(), sig(strategy="vcp", ticker="000660")], D)

    assert "2건" in subject
    assert "08/14" in subject


def test_email_subject_says_none_when_empty() -> None:
    assert "없음" in render.email_subject([], D)


def test_email_subject_prefixes_the_warning() -> None:
    subject = render.email_subject([sig()], D, warning="카톡 실패")

    assert subject.startswith("⚠")
    assert "카톡 실패" in subject


def test_email_subject_has_no_newline() -> None:
    """제목에 개행이 들어가면 헤더가 깨진다 (SMTP 인젝션)."""
    subject = render.email_subject([sig(name="줄바꿈\n종목")], D)

    assert "\n" not in subject and "\r" not in subject


# ── 메일 본문 ───────────────────────────────────────────────────


def test_email_html_contains_every_signal() -> None:
    """메일은 상한이 없다. 전 신호를 담는다 (D8)."""
    many = [sig(ticker=f"{i:05d}0", name=f"종목{i}") for i in range(30)]
    html = render.email_html(many, D)

    assert all(f"종목{i}" in html for i in range(30))


def test_email_html_expands_the_evidence() -> None:
    """웹에 안 들어가도 메일에서 판단이 끝나야 한다 (F13b)."""
    html = render.email_html([sig()], D)

    assert "월봉 종가 &gt; MA20" in html
    assert "71,200 vs 68,430" in html


def test_email_html_escapes_names() -> None:
    """종목명에 &가 들어가면 메일이 깨진다."""
    html = render.email_html([sig(name="A&B <홀딩스>")], D)

    assert "A&amp;B &lt;홀딩스&gt;" in html
    assert "<홀딩스>" not in html


def test_email_html_includes_the_web_link() -> None:
    html = render.email_html([sig()], D, web_url="https://example.com/signals")

    assert "https://example.com/signals" in html


def test_email_text_is_a_readable_fallback() -> None:
    """평문 대체본이 없으면 스팸 점수가 올라간다 (D15)."""
    text = render.email_text([sig()], D)

    assert "삼성전자" in text
    assert "<" not in text


def test_email_text_says_none_when_empty() -> None:
    assert "없음" in render.email_text([], D)


def test_email_html_says_none_when_empty() -> None:
    html = render.email_html([], D)

    assert "없음" in html


def test_email_marks_stale_data() -> None:
    assert "지연" in render.email_html([], D, stale=True)
    assert "지연" in render.email_text([], D, stale=True)


def test_email_groups_by_strategy_in_a_stable_order() -> None:
    """전략 순서가 매일 바뀌면 눈이 익지 않는다."""
    signals = [sig(strategy="vcp", ticker="000010"), sig(strategy="mtf", ticker="000020")]
    a = render.email_text(signals, D)
    b = render.email_text(list(reversed(signals)), D)

    assert a == b
