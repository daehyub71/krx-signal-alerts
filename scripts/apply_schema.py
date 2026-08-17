"""`supabase/schema.sql`을 적용한다 (멱등).

supabase-py는 DDL을 지원하지 않아 psycopg로 직접 붙는다.

    python scripts/apply_schema.py          # 적용
    python scripts/apply_schema.py --check  # 적용하지 않고 현재 상태만 본다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from alerts import config  # noqa: E402

SCHEMA = config.PROJECT_ROOT / "supabase" / "schema.sql"
OWNED = ("ksa_signals", "ksa_runs")

INSPECT = """
select c.relname,
       c.relrowsecurity,
       (select count(*) from pg_policies p
         where p.schemaname = 'public' and p.tablename = c.relname),
       (select count(*) from pg_index i where i.indrelid = c.oid)
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
 where n.nspname = 'public' and c.relname = any(%s)
 order by c.relname
"""


def connect() -> psycopg.Connection[tuple[object, ...]]:
    """DB에 붙는다.

    Note:
        `.env`의 URL은 트랜잭션 풀러(6543)다. 풀러는 프리페어드 스테이트먼트를
        재사용하지 못하므로 `prepare_threshold=None`으로 끈다.
    """
    return psycopg.connect(config.require("SUPABASE_DATABASE_URL"), prepare_threshold=None)


def report(conn: psycopg.Connection[tuple[object, ...]]) -> None:
    """소유 테이블의 현재 상태를 출력한다."""
    rows = conn.execute(INSPECT, (list(OWNED),)).fetchall()
    if not rows:
        print("  (ksa_* 테이블이 아직 없다)")
        return
    for name, rls, policies, indexes in rows:
        print(f"  {name:14} RLS={'on' if rls else 'OFF'}  정책 {policies}개  인덱스 {indexes}개")


def main(argv: list[str] | None = None) -> int:
    """스키마를 적용하고 결과를 보고한다."""
    parser = argparse.ArgumentParser(prog="apply_schema")
    parser.add_argument("--check", action="store_true", help="적용하지 않고 상태만 본다")
    args = parser.parse_args(argv)

    config.load_env()
    with connect() as conn:
        print("[적용 전]")
        report(conn)

        if args.check:
            return 0

        conn.execute(SCHEMA.read_text(encoding="utf-8"))  # type: ignore[arg-type]
        conn.commit()

        print("\n[적용 후]")
        report(conn)

    print("\n스키마 적용 완료. ksc_* 테이블은 건드리지 않았다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
