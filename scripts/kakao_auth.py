"""카카오 최초 인가 — 리프레시 토큰을 받는다 (SPEC F13).

브라우저에서 사람이 동의를 눌러야 하므로 **최초 1회는 자동화할 수 없다.**
이후에는 배치가 리프레시 토큰으로 알아서 갱신한다.

    python scripts/kakao_auth.py            # 최초 1회
    python scripts/kakao_auth.py --force    # 동의 화면을 강제로 다시 띄운다
    python scripts/kakao_auth.py --check    # 현재 토큰과 동의항목만 확인

선행 프로젝트에서 이 순서로 막혔다. 오류가 나면 여기부터 본다:

| 오류 | 원인 | 해결 |
|------|------|------|
| `KOE004` | 카카오 로그인 비활성 | 카카오 로그인 > 일반 > 사용 설정 ON |
| `KOE205` | 동의항목 미설정 | 동의항목 > 카카오톡 메시지 전송 |
| `KOE006` | 리다이렉트 URI 미등록 | **앱 설정 > 플랫폼 키 > REST API 키**
           (카카오 로그인 메뉴가 아니다) |
| `insufficient scopes` | 이미 연결된 앱이라 동의 화면을 건너뜀 | `--force` |
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alerts import config  # noqa: E402
from alerts.notify.kakao import TOKEN_URL, KakaoError, _post  # noqa: E402
from alerts.notify.tls import context as ssl_context  # noqa: E402

AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
SCOPES_URL = "https://kapi.kakao.com/v2/user/scopes"
SCOPE = "talk_message"
TOKENS_FILE = config.PROJECT_ROOT / ".tokens.json"

_code: str = ""


class Handler(BaseHTTPRequestHandler):
    """인가 코드를 한 번만 받아 내는 최소 서버."""

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler 규약
        global _code
        query = urllib.parse.urlparse(self.path).query
        _code = urllib.parse.parse_qs(query).get("code", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = "인가 완료. 터미널로 돌아가세요." if _code else "인가 코드를 받지 못했습니다."
        self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode())

    def log_message(self, *args: Any) -> None:
        """요청 로그를 찍지 않는다 — URL에 인가 코드가 들어 있다."""


def authorize(force: bool) -> str:
    """브라우저를 열어 인가 코드를 받는다."""
    redirect = config.optional("KAKAO_REDIRECT_URI", "http://localhost:8080/callback")
    params = {
        "client_id": config.require("KAKAO_REST_API_KEY"),
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
    }
    if force:
        # 이미 연결된 앱은 동의 화면을 건너뛴다. 그러면 나중에 추가한 동의항목이
        # 미동의로 남아 `insufficient scopes`가 난다.
        params["prompt"] = "login"

    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    port = urllib.parse.urlparse(redirect).port or 8080
    print(f"브라우저에서 동의해 주세요 (안 열리면 아래 주소를 직접 여세요):\n  {url}\n")
    webbrowser.open(url)

    server = HTTPServer(("localhost", port), Handler)
    server.handle_request()
    server.server_close()
    if not _code:
        raise KakaoError("인가 코드를 받지 못했다. 리다이렉트 URI 등록을 확인하라 (KOE006).")
    return _code


def exchange(code: str) -> dict[str, Any]:
    """인가 코드를 토큰으로 바꾼다."""
    data = {
        "grant_type": "authorization_code",
        "client_id": config.require("KAKAO_REST_API_KEY"),
        "redirect_uri": config.optional("KAKAO_REDIRECT_URI", "http://localhost:8080/callback"),
        "code": code,
    }
    if secret := config.optional("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = secret
    result: dict[str, Any] = _post(TOKEN_URL, data)
    return result


def show_scopes(access_token: str) -> None:
    """현재 동의 상태를 확인한다.

    `allowed_scopes`가 비어 있으면 동의항목은 설정돼 있어도 실제로는 미동의다.
    """
    req = urllib.request.Request(SCOPES_URL, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=15, context=ssl_context()) as r:
        scopes = json.loads(r.read().decode()).get("scopes", [])
    print("\n동의 상태:")
    for s in scopes:
        mark = "✓" if s.get("agreed") else "✗"
        print(f"  {mark} {s.get('id')} — {s.get('display_name', '')}")
    if not any(s.get("id") == SCOPE and s.get("agreed") for s in scopes):
        print(f"\n  ⚠ {SCOPE}에 동의되지 않았다. `--force`로 다시 인증하라.")


def save(tokens: dict[str, Any]) -> None:
    """토큰을 파일에 저장한다. `.gitignore` 대상이다."""
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    TOKENS_FILE.chmod(0o600)
    print(f"\n토큰을 {TOKENS_FILE.name}에 저장했다 (권한 600).")
    print("\n다음을 .env에 넣으세요 (GitHub Secrets에도 같은 값):")
    print(f"  KAKAO_REFRESH_TOKEN={tokens['refresh_token']}")


def main(argv: list[str] | None = None) -> int:
    """인가를 수행하고 토큰을 저장한다."""
    p = argparse.ArgumentParser(prog="kakao_auth")
    p.add_argument("--force", action="store_true", help="동의 화면을 강제로 다시 띄운다")
    p.add_argument("--check", action="store_true", help="저장된 토큰의 동의 상태만 본다")
    args = p.parse_args(argv)
    config.load_env()

    if args.check:
        if not TOKENS_FILE.is_file():
            print(f"{TOKENS_FILE.name}이 없다. 먼저 인가하라.")
            return 1
        show_scopes(json.loads(TOKENS_FILE.read_text())["access_token"])
        return 0

    try:
        tokens = exchange(authorize(args.force))
    except KakaoError as e:
        print(f"실패: {e}", file=sys.stderr)
        print("\n위 문서의 오류 표를 확인하세요.", file=sys.stderr)
        return 1

    save(tokens)
    show_scopes(tokens["access_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
