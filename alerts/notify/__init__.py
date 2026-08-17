"""발송 채널 (SPEC F13 · F13b).

**이 층의 함수는 예외를 밖으로 내지 않는다** (F13c). 실패도 `SendResult`로 돌려준다 —
발송 노드가 raise하면 `record_run`에 닿지 못해 실패 기록 자체가 사라진다.
"""

from alerts.notify import email, kakao, tls

__all__ = ["email", "kakao", "tls"]
