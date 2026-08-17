"""메시지 본문 생성 — 순수 함수 (SPEC N10).

네트워크를 모른다. 신호 목록을 받아 문자열을 돌려줄 뿐이다.
덕분에 200자 절단·0건 문구·HTML 이스케이프를 발송 없이 전부 테스트한다.

**두 채널은 담는 것이 다르다** (D8)
  카카오: 상위 10건 요약 — 본문 200자 상한
  메일:   전 신호 + 조건별 근거값 — 길이 제한 없음
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from html import escape

from alerts.models import STRATEGY_LABELS, STRATEGY_NAMES, Signal, StrategyName

# 카카오 텍스트 템플릿 본문 상한. 넘으면 400을 받고 알림이 통째로 사라진다.
KAKAO_MAX_CHARS = 200

STALE_LINE = "⚠ 데이터 지연 — 시세가 갱신되지 않아 신호를 만들지 않았습니다"

# "…외 N건"을 붙일 자리. 잘린 사실을 못 알리면 "오늘은 이게 다인가 보다"가 된다.
_OMITTED_RESERVE = 10


def _md(d: date) -> str:
    """`08/14` 형태."""
    return f"{d.month:02d}/{d.day:02d}"


def _grouped(signals: Sequence[Signal]) -> list[tuple[StrategyName, list[Signal]]]:
    """전략별로 묶는다. **순서는 항상 같다** — 매일 바뀌면 눈이 익지 않는다."""
    out: list[tuple[StrategyName, list[Signal]]] = []
    for name in STRATEGY_NAMES:
        items = [s for s in signals if s.strategy == name]
        if items:
            out.append((name, items))
    return out


def _one_line(sig: Signal) -> str:
    """카카오 한 줄. 공백 대신 개행을 쓴다 — 길이는 같고 훨씬 읽기 쉽다."""
    mark = "(진행중)" if sig.in_progress else ""
    return f"\n {sig.name} {sig.change_pct:+.1f}%{mark}"


# ── 카카오 ──────────────────────────────────────────────────────


def kakao_body(
    signals: Sequence[Signal],
    data_date: date,
    *,
    stale: bool = False,
    warning: str = "",
) -> str:
    """카카오톡 본문 (F13).

    Args:
        signals: 발송 대상 (이미 상위 N건으로 잘려 있다).
        data_date: 데이터 기준일.
        stale: 데이터가 낡아 신호를 만들지 않았는가.
        warning: 다른 채널의 실패를 알리는 한 줄 (F13c).

    Returns:
        200자 이하 본문. **경고는 절대 잘리지 않는다** — 잘리면 고장을 알릴 방법이 없다.

    Note:
        웹 링크는 본문이 아니라 템플릿의 link 객체로 보낸다. 200자를 아끼기 위해서다.
    """
    tail = f"\n⚠ {warning}" if warning else ""

    if stale:
        return f"[{_md(data_date)}] {STALE_LINE}{tail}"[:KAKAO_MAX_CHARS]
    if not signals:
        return f"[{_md(data_date)}] 오늘 신호 없음{tail}"[:KAKAO_MAX_CHARS]

    head = f"[{_md(data_date)}] 신호 {len(signals)}건"
    budget = KAKAO_MAX_CHARS - len(head) - len(tail)

    # **종목 단위로 채운다.** 블록 단위로 자르면 8건짜리 그룹 하나가 안 들어간다는
    # 이유로 통째로 버려져, 200자 중 100자 넘게 놀리는 일이 생긴다 (2026-08-17 실측).
    lines: list[str] = []
    used = 0
    dropped = 0
    for name, items in _grouped(signals):
        header = f"\n▸ {STRATEGY_LABELS[name]} ({len(items)})"
        header_used = False
        for s in items:
            line = _one_line(s)
            need = len(line) + (0 if header_used else len(header))
            # "…외 N건" 자리를 남겨 둔다 — 잘린 사실 자체를 못 알리면 안 된다.
            if used + need > budget - _OMITTED_RESERVE:
                dropped += 1
                continue
            if not header_used:
                lines.append(header)
                used += len(header)
                header_used = True
            lines.append(line)
            used += len(line)

    body = head + "".join(lines)
    if dropped:
        body += f"\n…외 {dropped}건"
    return (body + tail)[:KAKAO_MAX_CHARS]


# ── 메일 ────────────────────────────────────────────────────────


def email_subject(
    signals: Sequence[Signal],
    data_date: date,
    *,
    stale: bool = False,
    warning: str = "",
) -> str:
    """메일 제목 — 제목만 보고 오늘 볼지 판단할 수 있어야 한다 (F13b).

    Note:
        개행을 지운다. 제목에 `\\n`이 들어가면 SMTP 헤더가 깨진다.
    """
    prefix = f"⚠ {warning} · " if warning else ""
    if stale:
        subject = f"{prefix}[데이터 지연] {_md(data_date)}"
    elif not signals:
        subject = f"{prefix}[신호 없음] {_md(data_date)}"
    else:
        parts = " · ".join(
            f"{STRATEGY_LABELS[n]} {len(v)}" for n, v in _grouped(signals)
        )
        subject = f"{prefix}[신호 {len(signals)}건] {_md(data_date)} — {parts}"
    return subject.replace("\n", " ").replace("\r", " ")


def email_text(
    signals: Sequence[Signal],
    data_date: date,
    *,
    web_url: str = "",
    stale: bool = False,
) -> str:
    """평문 대체본 (D15). 없으면 스팸 점수가 올라간다."""
    if stale:
        return f"[{_md(data_date)}] {STALE_LINE}\n"
    if not signals:
        return f"[{_md(data_date)}] 오늘 신호 없음\n"

    out = [f"[{_md(data_date)}] 신호 {len(signals)}건", ""]
    for name, items in _grouped(signals):
        out.append(f"■ {STRATEGY_LABELS[name]} ({len(items)}건)")
        for s in items:
            mark = " (진행중)" if s.in_progress else ""
            out.append(
                f"  {s.name} [{s.ticker}] {s.close:,}원 {s.change_pct:+.2f}%{mark}"
            )
            for c in s.conditions:
                out.append(f"      {'O' if c.ok else 'X'} {c.label}: {c.actual}")
        out.append("")
    if web_url:
        out.append(f"전체 보기: {web_url}")
    return "\n".join(out) + "\n"


def email_html(
    signals: Sequence[Signal],
    data_date: date,
    *,
    web_url: str = "",
    stale: bool = False,
) -> str:
    """HTML 본문 — 조건별 근거값을 표로 편다 (F13b).

    Note:
        종목명은 반드시 이스케이프한다. `A&B <홀딩스>` 같은 이름이 실재한다.
    """
    css = (
        "font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
        "color:#121829;line-height:1.6"
    )
    head = f'<div style="{css}">'

    if stale:
        return f"{head}<h2>[{_md(data_date)}]</h2><p>{escape(STALE_LINE)}</p></div>"
    if not signals:
        return f"{head}<h2>[{_md(data_date)}]</h2><p>오늘 신호 없음</p></div>"

    parts = [head, f"<h2>[{_md(data_date)}] 신호 {len(signals)}건</h2>"]
    for name, items in _grouped(signals):
        parts.append(
            f'<h3 style="border-bottom:2px solid #C9283E;padding-bottom:4px">'
            f"{escape(STRATEGY_LABELS[name])} ({len(items)}건)</h3>"
        )
        for s in items:
            mark = ' <span style="color:#626D8A">(진행중)</span>' if s.in_progress else ""
            color = "#C9283E" if s.change_pct >= 0 else "#1F63A8"
            parts.append(
                f'<div style="margin:12px 0 18px">'
                f"<b>{escape(s.name)}</b> "
                f'<span style="color:#626D8A">[{escape(s.ticker)}]</span> '
                f"{s.close:,}원 "
                f'<span style="color:{color}">{s.change_pct:+.2f}%</span>{mark}'
            )
            parts.append('<ul style="margin:6px 0;padding-left:20px;color:#3D465F">')
            for c in s.conditions:
                parts.append(
                    f"<li>{'✓' if c.ok else '✗'} {escape(c.label)}: "
                    f"<code>{escape(c.actual)}</code></li>"
                )
            parts.append("</ul></div>")
    if web_url:
        parts.append(f'<p><a href="{escape(web_url)}">전체 보기 →</a></p>')
    parts.append("</div>")
    return "".join(parts)
