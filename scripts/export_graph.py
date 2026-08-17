"""그래프 구조를 `docs/GRAPH.md`로 내보낸다 (SPEC N12).

그래프를 고쳤으면 반드시 다시 돌린다. 문서가 낡으면 거짓말을 한다.

    python scripts/export_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alerts.config import PROJECT_ROOT  # noqa: E402
from alerts.graph import build_graph  # noqa: E402

OUT = PROJECT_ROOT / "docs" / "GRAPH.md"

HEADER = """# GRAPH.md — 그래프 구조

> **이 파일은 `scripts/export_graph.py`가 생성한다. 직접 고치지 않는다.**
> 그래프를 바꿨으면 스크립트를 다시 돌려 커밋한다 (SPEC N12).
>
> 설계 의도와 각 노드가 하는 일은 `PLAN.md` §1-1을 본다.

```mermaid
"""

FOOTER = """```
"""


def main() -> int:
    """그래프를 mermaid로 그려 파일에 쓴다."""
    mermaid = build_graph().get_graph().draw_mermaid()
    OUT.write_text(HEADER + mermaid.rstrip() + "\n" + FOOTER, encoding="utf-8")
    print(f"[export_graph] {OUT.relative_to(PROJECT_ROOT)} 갱신")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
