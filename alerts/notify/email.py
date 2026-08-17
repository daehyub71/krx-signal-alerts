"""Gmail SMTP 발송 (SPEC F13b · D13).

표준 라이브러리 `smtplib` + `email.message`만 쓴다 — 새 의존성이 없다.

**계정 비밀번호가 아니라 앱 비밀번호**를 쓴다. 구글은 2022년부터 일반 비밀번호로
SMTP 인증을 거부한다. 앱 비밀번호는 2단계 인증이 켜져 있어야 발급된다 (R10).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from alerts import config
from alerts.notify.tls import context as tls_context

HOST = "smtp.gmail.com"
PORT = 587  # STARTTLS
TIMEOUT = 30


class EmailError(RuntimeError):
    """메일 발송 오류. `notify` 층 바깥으로 나가지 않는다."""


def recipients() -> list[str]:
    """수신자 목록. 쉼표로 여러 명을 넣을 수 있다 (D14).

    Raises:
        EmailError: 수신자가 하나도 없을 때.
    """
    raw = config.optional("RECIPIENTS")
    people = [x.strip() for x in raw.split(",") if x.strip()]
    if not people:
        raise EmailError("RECIPIENTS가 비어 있다. .env를 확인하라.")
    return people


def build(subject: str, text: str, html: str, sender: str, to: list[str]) -> EmailMessage:
    """multipart/alternative 메시지를 만든다 (D15).

    Note:
        평문 대체본을 먼저 넣고 HTML을 나중에 넣는다 — 이 순서가 규격이다.
        평문이 없으면 스팸 점수가 올라간다 (R11).
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def send(subject: str, text: str, html: str) -> int:
    """메일을 보낸다.

    Args:
        subject: 제목. 개행이 없어야 한다 (`render.email_subject`가 지운다).
        text: 평문 대체본.
        html: HTML 본문.

    Returns:
        보낸 수신자 수.

    Raises:
        EmailError: 인증 실패·연결 실패 등.
    """
    sender = config.require("GMAIL_ADDRESS")
    password = config.require("GMAIL_APP_PASSWORD")
    to = recipients()
    msg = build(subject, text, html, sender, to)

    try:
        with smtplib.SMTP(HOST, PORT, timeout=TIMEOUT) as smtp:
            smtp.starttls(context=tls_context())
            smtp.login(sender, password)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailError(
            f"SMTP 인증 실패 ({e.smtp_code}) — 계정 비밀번호가 아니라 "
            "**앱 비밀번호**인지, 2단계 인증이 켜져 있는지 확인하라."
        ) from e
    except (smtplib.SMTPException, OSError) as e:
        raise EmailError(f"{type(e).__name__}: {e}") from e

    return len(to)
