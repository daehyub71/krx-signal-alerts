"""Supabase 읽기·쓰기.

**두 경로를 쓴다.**

| 경로 | 쓰는 곳 | 이유 |
|------|---------|------|
| psycopg (직접 SQL) | 봉 대량 조회 · 완결성 카운트 | REST로 받으면 1,000행씩 수백 번 왕복 |
| supabase-py (REST) | `ksa_*` 쓰기 · 메타 조회 | 소량이고 RLS·인증을 클라이언트가 처리해 준다 |

REST로 대량 조회를 하면 **1,000행에서 오류 없이 조용히 잘린다.** 완결성 검사를 REST로 하면
"데이터가 없다"는 오탐이 난다 (선행 프로젝트에서 실제 발생).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from typing import Any

import psycopg
from supabase import Client, create_client

from alerts import config
from alerts.models import Bar, BarSet, Signal, TickerMeta, Timeframe

# 티커 .in() 필터는 쿼리 문자열에 실린다. 2,763개를 한 번에 넣으면 URL 19KB로 400이 난다.
TICKER_CHUNK = 300

# REST 페이지네이션 크기. Supabase는 1,000행을 넘겨주지 않는다.
PAGE = 1000


# ── 연결 ────────────────────────────────────────────────────────


def rest_client() -> Client:
    """service_role 클라이언트. RLS를 우회한다 — 웹 번들에 절대 넣지 않는다."""
    return create_client(config.require("SUPABASE_URL"), config.require("SUPABASE_SERVICE_KEY"))


@contextmanager
def db() -> Iterator[psycopg.Connection[Any]]:
    """psycopg 연결 (스크립트용 — 열고 닫는다).

    Note:
        URL은 트랜잭션 풀러(6543)다. 프리페어드 스테이트먼트를 재사용하지 못하므로
        `prepare_threshold=None`으로 끈다.
    """
    conn = psycopg.connect(config.require("SUPABASE_DATABASE_URL"), prepare_threshold=None)
    try:
        yield conn
    finally:
        conn.close()


_conn: psycopg.Connection[Any] | None = None


def conn() -> psycopg.Connection[Any]:
    """배치용 공유 연결.

    노드마다 새로 붙으면 한 번 실행에 연결이 넷이 된다. 노드를 얇게 유지하려면
    (N11) 연결 수명을 여기서 관리하는 편이 낫다. `close()`로 닫는다.
    """
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg.connect(
            config.require("SUPABASE_DATABASE_URL"), prepare_threshold=None
        )
    return _conn


def close() -> None:
    """공유 연결을 닫는다. `main`이 끝낼 때 부른다."""
    global _conn
    if _conn is not None and not _conn.closed:
        _conn.close()
    _conn = None


# ── 읽기 (ksc_* — 읽기만 한다) ──────────────────────────────────


def fetch_data_date(conn: psycopg.Connection[Any]) -> date | None:
    """적재된 데이터의 실제 최신 거래일 (F3).

    `ksc_meta`를 믿지 않는다 — 마지막 실행이 무엇을 했는지를 적을 뿐,
    데이터가 최신인지를 보증하지 않는다. 실제로 종목 확장 이전 기록이
    "최신"이라고 말하고 있었다 (2026-08-17 확인, SPEC F3).
    """
    row = conn.execute("select max(d) from ksc_bars where timeframe = 'D'").fetchone()
    return row[0] if row else None


def fetch_tickers(conn: psycopg.Connection[Any]) -> list[TickerMeta]:
    """전 종목 메타. SQL로 직접 읽어 1,000행 절단을 피한다."""
    rows = conn.execute(
        "select ticker, name, market, coalesce(sector, '') from ksc_tickers order by ticker"
    ).fetchall()
    return [TickerMeta(ticker=t, name=n, market=m, sector=s) for t, n, m, s in rows]


def fetch_avg_amounts(conn: psycopg.Connection[Any], days: int = 20) -> dict[str, int]:
    """종목별 최근 N거래일 평균 거래대금 (F1 유동성 필터).

    Args:
        conn: DB 연결.
        days: 평균을 낼 거래일 수.

    Returns:
        종목 → 평균 거래대금(원). 봉이 없는 종목은 키 자체가 없다.
    """
    rows = conn.execute(
        """
        select ticker, avg(a)::bigint
          from (select ticker, a,
                       row_number() over (partition by ticker order by d desc) rn
                  from ksc_bars where timeframe = 'D' and a is not null) t
         where rn <= %s
         group by ticker
        """,
        (days,),
    ).fetchall()
    return {t: int(v) for t, v in rows if v is not None}


def fetch_bars(
    conn: psycopg.Connection[Any],
    tickers: Sequence[str],
    timeframe: Timeframe,
    limit_per_ticker: int,
) -> dict[str, tuple[Bar, ...]]:
    """종목별 최근 N개 봉을 한 번의 쿼리로 읽는다 (F2).

    Args:
        conn: DB 연결.
        tickers: 대상 종목.
        timeframe: `D` / `W` / `M`.
        limit_per_ticker: 종목당 최근 몇 개를 읽을지. MA 워밍업 여유를 포함해 넉넉히 준다.

    Returns:
        종목 → 봉 튜플. **오래된 것부터** 정렬돼 있다 (지표 계산 순서).
    """
    rows = conn.execute(
        """
        select ticker, d, o, h, l, c, v, a
          from (select *, row_number() over (partition by ticker order by d desc) rn
                  from ksc_bars
                 where timeframe = %s and ticker = any(%s)) t
         where rn <= %s
         order by ticker, d
        """,
        (timeframe, list(tickers), limit_per_ticker),
    ).fetchall()

    out: dict[str, list[Bar]] = {}
    for ticker, d, o, h, low, c, v, a in rows:
        out.setdefault(ticker, []).append(Bar(d=d, o=o, h=h, low=low, c=c, v=v, a=a))
    return {t: tuple(bars) for t, bars in out.items()}


def fetch_barsets(
    conn: psycopg.Connection[Any],
    tickers: Sequence[str],
    *,
    daily: int = 250,
    weekly: int = 80,
    monthly: int = 37,
) -> dict[str, BarSet]:
    """일·주·월봉을 묶어 읽는다.

    Returns:
        종목 → `BarSet`. 세 주기 중 하나라도 있으면 항목이 생긴다.
    """
    d = fetch_bars(conn, tickers, "D", daily)
    w = fetch_bars(conn, tickers, "W", weekly)
    m = fetch_bars(conn, tickers, "M", monthly)
    keys = set(d) | set(w) | set(m)
    return {
        t: BarSet(ticker=t, daily=d.get(t, ()), weekly=w.get(t, ()), monthly=m.get(t, ()))
        for t in sorted(keys)
    }


# ── 쓰기 (ksa_* — 이 프로젝트 소유) ─────────────────────────────


def upsert_signals(client: Client, signals: Sequence[Signal]) -> int:
    """신호를 저장한다 (F12). PK 기준 upsert라 재실행해도 같은 결과다 (N6).

    Returns:
        저장한 행 수.
    """
    if not signals:
        return 0

    rows: list[Any] = [
        {
            "d": s.d.isoformat(),
            "strategy": s.strategy,
            "ticker": s.ticker,
            # 웹이 조인 없이 읽는다 — 이 테이블은 그날의 스냅샷이다 (DESIGN §1)
            "name": s.name,
            "score": s.score,
            "rank_no": s.rank_no,
            "sent_kakao": s.sent_kakao,
            "sent_email": s.sent_email,
            "suppressed": s.suppressed,
            "evidence": s.evidence(),
        }
        for s in signals
    ]
    for i in range(0, len(rows), PAGE):
        client.table("ksa_signals").upsert(rows[i : i + PAGE]).execute()
    return len(rows)


def fetch_recent_signal_keys(
    conn: psycopg.Connection[Any], since: date
) -> set[tuple[str, str, date]]:
    """중복 억제(F10)용 최근 신호 키.

    Note:
        판정 근거는 메모리가 아니라 DB다. 배치를 재실행해도 같은 결과가 나와야 한다.
    """
    rows = conn.execute(
        "select ticker, strategy, d from ksa_signals where d >= %s", (since,)
    ).fetchall()
    return {(t, s, d) for t, s, d in rows}


def insert_run(client: Client, record: dict[str, Any]) -> None:
    """실행 기록을 남긴다 (F13c). 실패해도 이것부터 쓴다."""
    client.table("ksa_runs").insert(record).execute()
