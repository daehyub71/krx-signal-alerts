"""TLS 컨텍스트.

**macOS Python.org 설치본은 CA 인증서 번들이 없다.** curl은 되는데 파이썬만
`CERTIFICATE_VERIFY_FAILED`가 나는 상태가 된다 — 카카오와 Gmail 양쪽에서 똑같이 터진다.

시스템 전체를 고치려면 `/Applications/Python 3.13/Install Certificates.command`를
한 번 실행하면 되지만, CI에서도 같은 코드가 돌아야 하므로 `certifi`를 명시적으로 쓴다.
"""

from __future__ import annotations

import ssl


def context() -> ssl.SSLContext:
    """검증용 TLS 컨텍스트. `certifi`가 있으면 그 번들을 쓴다."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
