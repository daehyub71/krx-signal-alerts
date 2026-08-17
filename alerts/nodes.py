"""그래프 노드.

**노드는 얇다** (SPEC N11). 상태에서 값을 꺼내 도메인 함수를 부르고 결과를 상태에 담는 것까지가
노드의 일이다. 함수 하나가 20줄을 넘으면 로직이 새어 들어온 것이니 도메인 모듈로 옮긴다.

부수효과(DB·네트워크)를 아는 노드는 `store`·`notify`를 부르고, 나머지는 순수 함수만 부른다.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from alerts import config, render, store, strategies, universe
from alerts import rank as ranking
from alerts.freshness import is_stale
from alerts.models import STRATEGY_LABELS, SendResult, StrategyName
from alerts.notify import email, kakao
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


# ── 발송 (순차 2: 메일 → 카카오) ────────────────────────────────
#
# 이 두 노드는 **예외를 밖으로 내지 않는다** (SPEC F13c).
# raise하면 record_run에 닿지 못해 실패 기록 자체가 사라진다.
#
# 병렬이 아닌 이유: 병렬이면 서로의 실패를 모른다. 순차로 두면 뒤에 오는
# 카카오가 메일의 실패를 실어 나를 수 있다. 발송은 전체 70초 중 2~3초다.


def _skip(channel: str, state: AlertState) -> bool:
    """이 채널을 건너뛰는가 (미선택이거나 드라이런)."""
    if channel not in state.get("channels", []):
        return True
    if state.get("dry_run"):
        print(f"[{channel}] dry-run — 발송 생략")
        return True
    return False


def _report_date(state: AlertState) -> date:
    """알림에 표기할 날짜 — 데이터 기준일. 없으면 실행일."""
    return state.get("data_date") or state["run_date"]


def send_email(state: AlertState) -> dict[str, Any]:
    """이메일 — 전 신호와 조건별 근거값 (F13b).

    **먼저 보낸다.** 길이 제한이 없어 내용을 다 담는 쪽이고, 토큰 만료 같은
    조용한 실패 모드가 없어 더 믿을 만하다.

    **예외를 밖으로 내지 않는다** (F13c).
    """
    if _skip("email", state):
        return {}
    live = [s for s in state.get("ranked", []) if not s.suppressed]
    d, stale = _report_date(state), state.get("stale", False)
    url = config.optional("SIGNALS_WEB_URL")
    try:
        n = email.send(
            render.email_subject(live, d, stale=stale),
            render.email_text(live, d, web_url=url, stale=stale),
            render.email_html(live, d, web_url=url, stale=stale),
        )
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 결과로 바꿔 담는다
        print(f"[email] 실패: {exc}")
        return {"results": {"email": SendResult("email", ok=False, error=str(exc)[:200])}}
    print(f"[email] {len(live)}건 발송 → 수신자 {n}명")
    return {"results": {"email": SendResult("email", ok=True, sent_n=len(live))}}


def send_kakao(state: AlertState) -> dict[str, Any]:
    """카카오톡 나에게 보내기 — 상위 10건 요약 (F13).

    **메일 다음에 보낸다.** 그래야 메일이 죽었을 때 이 메시지가 알려 줄 수 있다 (F13c).

    **예외를 밖으로 내지 않는다.**
    """
    if _skip("kakao", state):
        return {}
    top = state.get("kakao_top", [])
    mail = state.get("results", {}).get("email")
    warning = "메일 발송 실패" if mail is not None and not mail.ok else ""

    body = render.kakao_body(
        top, _report_date(state), stale=state.get("stale", False), warning=warning
    )
    try:
        tokens = kakao.refresh_access_token(kakao.load_refresh_token())
        kakao.send_text(tokens.access, body, config.optional("SIGNALS_WEB_URL"))
    except Exception as exc:  # noqa: BLE001
        print(f"[kakao] 실패: {exc}")
        return {"results": {"kakao": SendResult("kakao", ok=False, error=str(exc)[:200])}}

    print(f"[kakao] {len(top)}건 발송 ({len(body)}자)")
    out: dict[str, Any] = {"results": {"kakao": SendResult("kakao", ok=True, sent_n=len(top))}}
    if tokens.refresh:
        # 카카오가 새 리프레시 토큰을 줬다. 저장하지 않으면 옛 토큰으로 계속
        # 시도하다 2개월 뒤 조용히 죽는다 (R2).
        kakao.save_refresh_token(tokens.refresh)
        out["kakao_refresh"] = tokens.refresh
        print("[kakao] 새 리프레시 토큰 저장 — GitHub Secret도 갱신해야 한다 (M4)")
    return out


# ── 마감 ────────────────────────────────────────────────────────


def _status_of(state: AlertState) -> str:
    """채널 결과로 최종 상태를 정한다."""
    results = state.get("results", {})
    failed = [r for r in results.values() if not r.ok]
    if not results:
        return state.get("status", STATUS_OK)
    if not failed:
        return STATUS_STALE if state.get("stale") else STATUS_OK
    return STATUS_FAILED if len(failed) == len(results) else STATUS_PARTIAL


def record_run(state: AlertState) -> dict[str, Any]:
    """실행 결과를 `ksa_runs`에 남기고 최종 상태를 정한다 (F13c).

    실패해도 **기록이 먼저**다. 예외를 먼저 던지면 원인이 사라진다.
    """
    results = state.get("results", {})
    status = _status_of(state)
    record = {
        "data_date": (d.isoformat() if (d := state.get("data_date")) else None),
        "universe_n": len(state.get("universe", [])),
        "signal_n": len(state.get("signals", [])),
        "sent_kakao_n": results["kakao"].sent_n if "kakao" in results else 0,
        "sent_email_n": results["email"].sent_n if "email" in results else 0,
        "status": status,
        "detail": {
            c: {"ok": r.ok, "sent_n": r.sent_n, "error": r.error} for c, r in results.items()
        },
    }
    if not state.get("dry_run"):
        try:
            store.insert_run(store.rest_client(), record)
        except Exception as exc:  # noqa: BLE001 — 기록 실패가 알림을 삼키면 안 된다
            print(f"[record_run] 기록 실패(무시): {exc}")
    print(f"[record_run] status={status}")
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
