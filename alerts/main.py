"""CLI 진입점.

부수효과(시간·네트워크·DB)를 아는 몇 안 되는 곳이다.
**기준일을 여기서 정해 상태에 주입한다** — 전략이 "오늘"을 직접 알면 드라이런이 성립하지 않는다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from alerts import config
from alerts.graph import build_graph
from alerts.nodes import AlertRunError
from alerts.state import initial_state

CHANNEL_CHOICES = ("kakao", "email", "both")


def parse_channels(value: str) -> list[str]:
    """`--channel` 인자를 채널 목록으로 편다."""
    return ["kakao", "email"] if value == "both" else [value]


def parse_date(value: str | None) -> date:
    """`--date YYYYMMDD`를 날짜로 바꾼다. 없으면 오늘."""
    return datetime.strptime(value, "%Y%m%d").date() if value else date.today()


def build_parser() -> argparse.ArgumentParser:
    """인자 파서를 만든다."""
    p = argparse.ArgumentParser(prog="alerts", description="전략 스크리닝 알람 배치")
    p.add_argument("--date", help="기준일 YYYYMMDD (기본: 오늘)")
    p.add_argument("--channel", choices=CHANNEL_CHOICES, default="both", help="발송 채널")
    p.add_argument("--dry-run", action="store_true", help="실제로 발송하지 않는다")
    return p


def main(argv: list[str] | None = None) -> int:
    """배치를 실행한다.

    Args:
        argv: 명령행 인자. None이면 `sys.argv`를 쓴다.

    Returns:
        종료 코드. 0은 성공, 1은 발송 실패.
    """
    args = build_parser().parse_args(argv)
    config.load_env()

    run_date = parse_date(args.date)
    channels = parse_channels(args.channel)
    state = initial_state(run_date, channels, dry_run=args.dry_run)

    print(f"[alerts] 기준일 {run_date} · 채널 {'/'.join(channels)}"
          f"{' · dry-run' if args.dry_run else ''}")

    try:
        final = build_graph().invoke(state)
    except AlertRunError as exc:
        print(f"[alerts] 실패: {exc}", file=sys.stderr)
        return 1

    print(f"[alerts] status={final['status']} "
          f"universe={len(final['universe'])} signals={len(final['signals'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
