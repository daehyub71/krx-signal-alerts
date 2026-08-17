"""카카오톡 나에게 보내기 (SPEC F13).

표준 라이브러리만 쓴다 (`urllib`). 요청이 두 종류뿐이라 requests를 끌어올 이유가 없다.

**리프레시 토큰이 약 2개월**이다. 매일 쓰면 갱신되지만 끊기면 `KOE322`가 나고
인가 코드부터 수동 재발급해야 한다. 갱신된 토큰은 **반드시 저장**한다 (R2).
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from alerts import config
from alerts.notify.tls import context as _ssl_context

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
TIMEOUT = 15
RETRIES = 3

# 리프레시 토큰이 죽었다는 신호. 조용히 넘기면 안 된다 — 사람이 재인증해야 한다.
DEAD_TOKEN = "KOE322"

# scripts/kakao_auth.py가 만드는 파일. 로컬 전용이며 .gitignore 대상이다.
TOKENS_FILE = ".tokens.json"


class KakaoError(RuntimeError):
    """카카오 API 오류. `notify` 층 바깥으로 나가지 않는다."""


@dataclass(frozen=True, slots=True)
class Tokens:
    """토큰 한 쌍.

    `refresh` 가 비어 있으면 카카오가 새 리프레시 토큰을 주지 않은 것이다 —
    아직 유효하다는 뜻이므로 기존 것을 계속 쓴다.
    """

    access: str
    refresh: str = ""


def _post(url: str, data: dict[str, str], headers: dict[str, str] | None = None) -> Any:
    """POST 한 번. 네트워크 오류만 재시도한다.

    Raises:
        KakaoError: 4xx/5xx 응답 또는 재시도 후에도 실패.
    """
    body = urllib.parse.urlencode(data).encode()
    last = ""
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context()) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            # 4xx는 재시도해도 같은 답이다. 인증·요청 문제이므로 바로 올린다.
            raise KakaoError(f"HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, ssl.SSLError) as e:
            last = f"{type(e).__name__}: {e}"
            if attempt == RETRIES - 1:
                raise KakaoError(f"{RETRIES}회 시도 후 실패 — {last}") from e
    raise KakaoError(last)


def load_refresh_token() -> str:
    """리프레시 토큰을 찾는다.

    Returns:
        리프레시 토큰.

    Raises:
        KakaoError: 어느 쪽에도 없을 때.

    Note:
        **환경변수가 먼저다.** CI에는 `.tokens.json`이 없고 GitHub Secrets만 있다.
        로컬에서는 `scripts/kakao_auth.py`가 만든 파일을 그대로 쓴다 —
        인가 직후 손으로 `.env`에 복사하는 단계를 하나 없애기 위해서다.
    """
    if token := config.optional("KAKAO_REFRESH_TOKEN"):
        return token

    path = config.PROJECT_ROOT / TOKENS_FILE
    if path.is_file():
        saved = json.loads(path.read_text(encoding="utf-8")).get("refresh_token", "")
        if saved:
            return str(saved)

    raise KakaoError(
        "리프레시 토큰이 없다. `python scripts/kakao_auth.py`로 인가하거나 "
        "KAKAO_REFRESH_TOKEN을 설정하라."
    )


def save_refresh_token(token: str) -> None:
    """갱신된 리프레시 토큰을 `.tokens.json`에 반영한다 (로컬 전용).

    안 하면 옛 토큰으로 계속 시도하다 2개월 뒤 조용히 죽는다 (R2).
    CI에서는 파일이 없으므로 아무 일도 하지 않는다 — Secret 갱신은 M4에서 다룬다.
    """
    path = config.PROJECT_ROOT / TOKENS_FILE
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data["refresh_token"] = token
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    path.chmod(0o600)


def refresh_access_token(refresh_token: str) -> Tokens:
    """리프레시 토큰으로 액세스 토큰을 재발급한다.

    Args:
        refresh_token: 저장해 둔 리프레시 토큰.

    Returns:
        새 액세스 토큰과, 카카오가 새로 준 경우에 한해 새 리프레시 토큰.

    Raises:
        KakaoError: 재발급 실패. `KOE322`면 리프레시 토큰이 죽은 것이라
            인가 코드부터 다시 받아야 한다 (`scripts/kakao_auth.py`).
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": config.require("KAKAO_REST_API_KEY"),
        "refresh_token": refresh_token,
    }
    if secret := config.optional("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = secret

    try:
        res = _post(TOKEN_URL, data)
    except KakaoError as e:
        if DEAD_TOKEN in str(e):
            raise KakaoError(
                f"{DEAD_TOKEN} — 리프레시 토큰이 만료됐다. "
                "`python scripts/kakao_auth.py --force`로 재인증하라."
            ) from e
        raise

    return Tokens(access=res["access_token"], refresh=res.get("refresh_token", ""))


def send_text(access_token: str, text: str, web_url: str = "") -> None:
    """나와의 채팅방에 텍스트를 보낸다.

    Args:
        access_token: 유효한 액세스 토큰.
        text: 본문. **호출 전에 200자 이하로 잘라 둔다** (`render.kakao_body`).
        web_url: 버튼과 말풍선이 연결될 링크.

    Raises:
        KakaoError: 발송 실패.

    Note:
        링크는 본문이 아니라 템플릿의 `link` 객체로 보낸다 — 200자를 아끼기 위해서다.
        카카오는 `web_url`이 비면 링크를 무시한다.
    """
    template: dict[str, Any] = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": web_url, "mobile_web_url": web_url} if web_url else {},
    }
    _post(
        SEND_URL,
        {"template_object": json.dumps(template, ensure_ascii=False)},
        {"Authorization": f"Bearer {access_token}"},
    )
