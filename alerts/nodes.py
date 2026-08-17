"""그래프 노드.

**노드는 얇다** (SPEC N11). 상태에서 값을 꺼내 도메인 함수를 부르고 결과를 상태에 담는 것까지가
노드의 일이다. 함수 하나가 20줄을 넘으면 로직이 새어 들어온 것이니 도메인 모듈로 옮긴다.

M0 단계에서는 전부 통과 함수다. `TODO(M?)` 표시가 붙은 자리를 마일스톤별로 채운다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from alerts import rank as ranking
from alerts import store, strategies, universe
from alerts.freshness import is_stale
from alerts.models import STRATEGY_LABELS, SendResult, StrategyName
from alerts.state import (
    STATUS_FAILED,
    STATUS_OK,
    STATUS_PARTIAL,
    STATUS_STALE,
    AlertState,
)


class AlertRunError(RuntimeError):
    """배치가 실패했음을 알리는 예외. `finalize`에서만 올린다 (SPEC N5)."""


# ── 진입과 게이트 ────────────────────────────────────────────────


def load_meta(state: AlertState) -> dict[str, Any]:
    """적재된 데이터의 실제 최신 거래일을 읽고 신선도를 판정한다 (F3).

    `ksc_meta`가 아니라 `ksc_bars.max(d)`를 본다 — 메타는 마지막 실행이 무엇을
    했는지를 적을 뿐 데이터가 최신인지를 보증하지 않는다 (SPEC F3).
    """
    data_date = store.fetch_data_date(store.conn())
    stale = is_stale(data_date, state["run_date"])
    print(f"[load_meta] 데이터 기준일 {data_date} · {'낡음' if stale else '최신'}")
    return {"data_date": data_date, "stale": stale}


def check_freshness(state: AlertState) -> str:
    """데이터가 낡았는지 판정해 다음 노드를 고른다 (F3).

    Args:
        state: 현재 상태.

    Returns:
        `"stale"` 또는 `"fresh"`.
    """
    return "stale" if state.get("stale", False) else "fresh"


def abort_stale(state: AlertState) -> dict[str, Any]:
    """신호 계산을 건너뛴다. 다만 침묵하지 않고 발송으로 합류한다 (D10).

    TODO(M3): "데이터 지연" 문구를 준비한다.
    """
    return {"status": STATUS_STALE}


# ── 준비 ────────────────────────────────────────────────────────


def build_universe(state: AlertState) -> dict[str, Any]:
    """스팩·우선주·저유동성을 뺀 종목 목록을 만든다 (F1)."""
    c = store.conn()
    result = universe.build(store.fetch_tickers(c), store.fetch_avg_amounts(c))
    print(f"[build_universe] {result.summary()}")
    return {"universe": result.kept}


def load_bars(state: AlertState) -> dict[str, Any]:
    """유니버스 전 종목의 일·주·월봉을 읽는다 (F2)."""
    codes = [m.ticker for m in state["universe"]]
    barsets = store.fetch_barsets(store.conn(), codes)
    rows = sum(len(b.daily) + len(b.weekly) + len(b.monthly) for b in barsets.values())
    print(f"[load_bars] {len(barsets)}종목 · {rows:,}행")
    return {"bars": barsets}


# ── 전략 (병렬 5) ───────────────────────────────────────────────


def make_strategy_node(name: StrategyName) -> Any:
    """전략 노드를 만든다 (F5~F9).

    Args:
        name: 전략 이름.

    Returns:
        상태를 받아 `{"signals": [...]}`를 돌려주는 노드 함수.

    Note:
        노드는 래퍼일 뿐이다. 판정 로직은 `alerts.strategies.{name}`의 순수 함수에 있고,
        노드는 그것을 부르기만 한다 (N11).
    """
    strategy = strategies.BY_NAME[name]

    def node(state: AlertState) -> dict[str, Any]:
        data_date = state.get("data_date")
        if data_date is None or not strategy.runs_on(data_date, state["run_date"]):
            print(f"[{name}] 오늘은 산출 주기가 아니다 — skip")
            return {}
        bars = state["bars"]
        found = [
            sig
            for m in state["universe"]
            if (bs := bars.get(m.ticker)) and (sig := strategy.evaluate(m, bs))
        ]
        print(f"[{name}] 신호 {len(found)}건")
        return {"signals": found}

    node.__name__ = f"strategy_{name}"
    node.__doc__ = f"{STRATEGY_LABELS[name]} 전략 노드."
    return node


# ── 정리와 저장 ─────────────────────────────────────────────────


def suppress(state: AlertState) -> dict[str, Any]:
    """최근 N일 내 같은 신호를 발송 대상에서 뺀다 (F10).

    판정 근거는 메모리가 아니라 DB다 — 배치를 재실행해도 같은 결과가 나와야 한다.
    """
    signals = state["signals"]
    if not signals:
        return {"ranked": []}
    since = state["run_date"] - timedelta(days=ranking.MAX_SUPPRESS_DAYS)
    marked = ranking.suppress(signals, store.fetch_recent_signal_keys(store.conn(), since))
    print(f"[suppress] {sum(1 for s in marked if s.suppressed)}건 억제")
    # `signals`에 쓰면 리듀서가 append해 목록이 두 배가 된다. 작업본은 `ranked`로 넘긴다.
    return {"ranked": marked}


def rank(state: AlertState) -> dict[str, Any]:
    """전략 내 백분위로 정규화해 정렬하고 카카오용 상위 N건을 고른다 (F11)."""
    ranked, top = ranking.rank(state["ranked"], limit=ranking.KAKAO_LIMIT)
    print(f"[rank] 발송 대상 {len(top)}건 / 전체 {len(ranked)}건")
    return {"ranked": ranked, "kakao_top": top}


def persist(state: AlertState) -> dict[str, Any]:
    """판정된 신호를 전부 `ksa_signals`에 저장한다 (F12).

    발송 여부와 무관하게 전부 남긴다 — 웹 이력과 중복 억제가 이걸 읽는다.
    """
    if state.get("dry_run"):
        print(f"[persist] dry-run — {len(state['ranked'])}건 저장 생략")
        return {}
    n = store.upsert_signals(store.rest_client(), state["ranked"])
    print(f"[persist] {n}건 저장")
    return {}


# ── 발송 (병렬 2) ───────────────────────────────────────────────
#
# 이 두 노드는 **예외를 밖으로 내지 않는다** (SPEC F13c).
# raise하면 record_run에 닿지 못해 실패 기록 자체가 사라진다.


def send_kakao(state: AlertState) -> dict[str, Any]:
    """카카오톡 나에게 보내기 — 상위 10건 요약 (F13).

    TODO(M3): notify.kakao.send()
    """
    if "kakao" not in state.get("channels", []):
        return {}
    return {"results": {"kakao": SendResult(channel="kakao", ok=True)}}


def send_email(state: AlertState) -> dict[str, Any]:
    """이메일 — 전 신호와 조건별 근거값 (F13b).

    TODO(M3): notify.email.send()
    """
    if "email" not in state.get("channels", []):
        return {}
    return {"results": {"email": SendResult(channel="email", ok=True)}}


# ── 마감 ────────────────────────────────────────────────────────


def record_run(state: AlertState) -> dict[str, Any]:
    """실행 결과를 `ksa_runs`에 남기고 최종 상태를 정한다 (F13c).

    실패해도 **기록이 먼저**다. 예외를 먼저 던지면 원인이 사라진다.

    TODO(M3): store.insert_run()
    """
    results = state.get("results", {})
    failed = [r.channel for r in results.values() if not r.ok]
    if not results:
        status = state.get("status", STATUS_OK)
    elif not failed:
        status = STATUS_STALE if state.get("stale") else STATUS_OK
    else:
        status = STATUS_FAILED if len(failed) == len(results) else STATUS_PARTIAL
    return {"status": status}


def finalize(state: AlertState) -> dict[str, Any]:
    """채널 중 하나라도 실패했으면 예외를 올린다 (SPEC N5).

    **실패 판정 지점은 여기 하나뿐이다.**

    Raises:
        AlertRunError: 발송 채널 중 실패가 있을 때.
    """
    status = state.get("status", STATUS_OK)
    if status in (STATUS_PARTIAL, STATUS_FAILED):
        failed = [r.channel for r in state.get("results", {}).values() if not r.ok]
        raise AlertRunError(f"발송 실패 ({status}): {', '.join(failed)}")
    return {}
