"""M1 실측 — 유니버스 건수·조회 시간·메모리 (TASKS 「측정 기록」).

추정으로 판단하지 않기 위해 실제로 잰다. 발송하지 않고 읽기만 한다.

    python scripts/measure_m1.py
"""

from __future__ import annotations

import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alerts import config, store, universe  # noqa: E402
from alerts.models import Bar, BarSet  # noqa: E402


def main() -> int:
    """M1 완료 기준을 실측으로 확인한다."""
    config.load_env()

    with store.db() as conn:
        print("=== 1. 데이터 기준일 (F3 — ksc_meta가 아니라 실제 max(d)) ===")
        t0 = time.time()
        data_date = store.fetch_data_date(conn)
        print(f"  ksc_bars 최신 일봉: {data_date}  ({time.time() - t0:.2f}s)")

        print("\n=== 2. 종목 메타 ===")
        t0 = time.time()
        tickers = store.fetch_tickers(conn)
        print(f"  {len(tickers)}종목  ({time.time() - t0:.2f}s)")

        print("\n=== 3. SQL 직접 카운트와 대조 (REST로 세지 않는다 — R6) ===")

        def count(where: str = "true") -> int:
            row = conn.execute(f"select count(*) from ksc_tickers where {where}").fetchone()  # noqa: S608
            return int(row[0]) if row else 0

        sql_total = count()
        sql_spac = count("name like '%%스팩%%'")
        sql_pref = count("substring(ticker, 6, 1) <> '0'")
        print(f"  SQL: 전체 {sql_total} · 스팩 {sql_spac} · 우선주 {sql_pref}")
        if len(tickers) != sql_total:
            print(f"  ✗ 조회 {len(tickers)} ≠ SQL {sql_total} — 절단 의심")
            return 1
        print("  ✓ 조회 건수 일치 (절단 없음)")

        print("\n=== 4. 20일 평균 거래대금 ===")
        t0 = time.time()
        amounts = store.fetch_avg_amounts(conn, days=20)
        print(f"  {len(amounts)}종목  ({time.time() - t0:.2f}s)")

        print("\n=== 5. 유니버스 (F1) ===")
        result = universe.build(tickers, amounts)
        print(f"  {result.summary()}")
        py_spac = result.excluded.get(universe.ExcludeReason.SPAC, 0)
        py_pref = result.excluded.get(universe.ExcludeReason.PREFERRED, 0)
        print(f"  대조 — 스팩 {py_spac} vs SQL {sql_spac} "
              f"{'✓' if py_spac == sql_spac else '✗'}")
        # 스팩이 우선주보다 먼저 걸러지므로 파이썬 쪽이 SQL보다 적을 수 있다
        print(f"  대조 — 우선주 {py_pref} vs SQL {sql_pref} "
              f"(스팩 우선 판정으로 차이 {sql_pref - py_pref} 허용)")
        total = len(result.kept) + sum(result.excluded.values())
        print(f"  합계 검산 — 유지 {len(result.kept)} + 제외 {sum(result.excluded.values())}"
              f" = {total} {'✓' if total == len(tickers) else '✗'}")

        print("\n=== 6. 전 종목 봉 조회 (F2) — 시간·메모리 ===")
        codes = [m.ticker for m in result.kept]
        tracemalloc.start()
        t0 = time.time()
        barsets = store.fetch_barsets(conn, codes)
        elapsed = time.time() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        rows = sum(len(b.daily) + len(b.weekly) + len(b.monthly) for b in barsets.values())
        print(f"  {len(barsets)}종목 · {rows:,}행  ({elapsed:.1f}s)")
        print(f"  tracemalloc 최대 {peak / 1024 / 1024:.0f}MB")
        print(f"  R7 목표 5분 이내: {'✓' if elapsed < 300 else '✗'}")

        print("\n=== 7. 봉 부족 종목 (정상 skip — 오류가 아니다) ===")
        specs: list[tuple[str, int, Callable[[BarSet], tuple[Bar, ...]]]] = [
            ("일봉 120", 120, lambda b: b.daily),
            ("주봉 60", 60, lambda b: b.weekly),
            ("월봉 20", 20, lambda b: b.monthly),
        ]
        for label, need, get in specs:
            met = sum(1 for b in barsets.values() if len(get(b)) >= need)
            pct = 100 * met / len(barsets) if barsets else 0.0
            print(f"  {label:9} 충족 {met}/{len(barsets)} ({pct:.0f}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
