"""드라이런 — 과거 N거래일을 재현해 전략별 신호량을 잰다 (SPEC R8).

**M2의 진짜 완료 조건이다.** 임계값이 초기 추정치라, 신호가 0건이거나 수백 건일 수 있다.
발송하지 않고 저장도 하지 않는다.

    python scripts/dryrun.py --days 60
    python scripts/dryrun.py --days 20 --strategy vcp --show 5
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alerts import (  # noqa: E402
    config,  # noqa: E402
    store,
    strategies,
    universe,
)
from alerts import rank as ranking  # noqa: E402
from alerts.models import Bar, BarSet, Signal, TickerMeta  # noqa: E402


def trim(bars: tuple[Bar, ...], asof: date) -> tuple[Bar, ...]:
    """`asof` 이후 봉을 잘라낸다 — 그날 시점의 시야를 재현한다."""
    return tuple(b for b in bars if b.d <= asof)


def as_of(barset: BarSet, asof: date) -> BarSet:
    """그날까지만 보이는 봉 묶음."""
    return BarSet(
        ticker=barset.ticker,
        daily=trim(barset.daily, asof),
        weekly=trim(barset.weekly, asof),
        monthly=trim(barset.monthly, asof),
    )


def run_one_day(
    metas: list[TickerMeta],
    barsets: dict[str, BarSet],
    data_date: date,
    run_date: date,
) -> list[Signal]:
    """하루치를 판정한다."""
    found: list[Signal] = []
    for strategy in strategies.ALL:
        if not strategy.runs_on(data_date, run_date):
            continue
        for m in metas:
            bs = barsets.get(m.ticker)
            if bs is None:
                continue
            sig = strategy.evaluate(m, as_of(bs, data_date))
            if sig is not None:
                found.append(sig)
    return found


def main(argv: list[str] | None = None) -> int:
    """드라이런을 돌리고 전략별 신호량을 보고한다."""
    p = argparse.ArgumentParser(prog="dryrun")
    p.add_argument("--days", type=int, default=60, help="되짚을 거래일 수")
    p.add_argument("--strategy", help="한 전략만 본다")
    p.add_argument("--show", type=int, default=3, help="전략별로 예시 몇 건을 보여줄지")
    args = p.parse_args(argv)

    config.load_env()
    with store.db() as conn:
        print("데이터를 읽는 중…")
        t0 = time.time()
        metas = universe.build(
            store.fetch_tickers(conn), store.fetch_avg_amounts(conn)
        ).kept
        codes = [m.ticker for m in metas]
        # 과거를 되짚으려면 그날 시점에도 워밍업이 남아 있어야 한다 — 넉넉히 읽는다.
        barsets = store.fetch_barsets(conn, codes, daily=250 + args.days, weekly=110, monthly=37)
        print(f"  유니버스 {len(metas)}종목 ({time.time() - t0:.1f}s)\n")

        trading_days = sorted({b.d for bs in barsets.values() for b in bs.daily})[-args.days :]
        if not trading_days:
            print("거래일을 찾지 못했다.")
            return 1

        raw: Counter[str] = Counter()
        fresh: Counter[str] = Counter()
        days_seen: dict[str, set[date]] = {}
        last_seen: dict[tuple[str, str], date] = {}
        samples: dict[str, list[Signal]] = {}

        t0 = time.time()
        for i, d in enumerate(trading_days):
            # 그 다음 거래일 아침에 돌린 셈으로 친다 (주·월 마감 판정에 쓰인다)
            run_date = trading_days[i + 1] if i + 1 < len(trading_days) else d + timedelta(days=1)
            for sig in run_one_day(metas, barsets, d, run_date):
                if args.strategy and sig.strategy != args.strategy:
                    continue
                raw[sig.strategy] += 1

                # F10 중복 억제를 그대로 흉내 낸다 — 실제로 알림에 담기는 건수가 이쪽이다
                k = (sig.ticker, sig.strategy)
                window = ranking.SUPPRESS_DAYS.get(sig.strategy, ranking.DEFAULT_SUPPRESS_DAYS)
                prev = last_seen.get(k)
                if prev is not None and (d - prev).days <= window:
                    continue
                last_seen[k] = d
                fresh[sig.strategy] += 1
                days_seen.setdefault(sig.strategy, set()).add(d)
                samples.setdefault(sig.strategy, []).append(sig)
        elapsed = time.time() - t0

    n = len(trading_days)
    print(f"=== {n}거래일 ({trading_days[0]} ~ {trading_days[-1]}) · {elapsed:.0f}s ===\n")
    print(f"{'전략':<13}{'판정':>7}{'억제후':>8}{'일평균':>8}{'신호난 날':>11}{'억제창':>8}")
    for s in strategies.ALL:
        win = ranking.SUPPRESS_DAYS.get(s.name, ranking.DEFAULT_SUPPRESS_DAYS)
        print(f"{s.name:<13}{raw[s.name]:>7}{fresh[s.name]:>8}"
              f"{fresh[s.name] / n:>8.1f}{len(days_seen.get(s.name, ())):>9}일{win:>7}일")
    print(f"{'합계':<13}{sum(raw.values()):>7}{sum(fresh.values()):>8}"
          f"{sum(fresh.values()) / n:>8.1f}")
    print("\n  '억제후'가 실제로 알림에 담기는 건수다 (F10). 카카오는 상위 "
          f"{ranking.KAKAO_LIMIT}건, 메일은 전부.")

    print("\n=== 예시 ===")
    for s in strategies.ALL:
        picked = sorted(samples.get(s.name, []), key=lambda x: -x.score)[: args.show]
        if not picked:
            print(f"\n[{s.name}] 신호 없음")
            continue
        print(f"\n[{s.name}]")
        for sig in picked:
            print(f"  {sig.d} {sig.ticker} {sig.name[:14]:<15} "
                  f"score={sig.score:.3f} 종가 {sig.close:,}")
            for c in sig.conditions:
                print(f"      {'✓' if c.ok else '✗'} {c.label}: {c.actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
