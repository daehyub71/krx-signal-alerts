/**
 * 배치와 웹이 만나는 계약 (PLAN §4).
 *
 * `evidence`의 키 이름은 파이썬 `Signal.evidence()`가 만든다.
 * 여기 이름을 바꾸면 과거 이력이 통째로 안 읽힌다 — 바꾸려면 SPEC부터 고친다.
 */

export const STRATEGIES = ["mtf", "pullback", "vcp", "squeeze", "turnaround"] as const;
export type Strategy = (typeof STRATEGIES)[number];

/** 알림·화면에 쓰는 전략 이름. 짧은 쪽은 표에서, 긴 쪽은 상세에서 쓴다. */
export const STRATEGY_LABEL: Record<Strategy, string> = {
  mtf: "MTF 정배열",
  pullback: "주봉 눌림목",
  vcp: "VCP 수축",
  squeeze: "밴드 스퀴즈",
  turnaround: "장기 턴어라운드",
};

export const STRATEGY_SHORT: Record<Strategy, string> = {
  mtf: "MTF",
  pullback: "눌림목",
  vcp: "VCP",
  squeeze: "스퀴즈",
  turnaround: "턴어라운드",
};

/** 전략이 판정한 조건 하나. `actual`은 배치가 이미 포맷한 문자열이다. */
export type Condition = {
  label: string;
  ok: boolean;
  actual: string;
};

/** `ksa_signals.evidence` (jsonb). */
export type Evidence = {
  conditions: Condition[];
  price: { close: number; change_pct: number };
  volume: { value: number; amount: number };
  meta: { in_progress: boolean };
};

/** `ksa_signals` 한 행. */
export type SignalRow = {
  d: string;
  strategy: Strategy;
  ticker: string;
  name: string;
  score: number;
  rank_no: number | null;
  sent_kakao: boolean;
  sent_email: boolean;
  suppressed: boolean;
  evidence: Evidence;
};

/** `ksa_runs` 한 행 — "안 온 게 정상인지 고장인지"를 가리는 기록. */
export type RunRow = {
  run_at: string;
  data_date: string | null;
  universe_n: number;
  signal_n: number;
  sent_kakao_n: number;
  sent_email_n: number;
  status: "ok" | "stale_data" | "partial_send_failed" | "send_failed";
};

/** 화면이 실제로 다루는 형태 — evidence를 펴서 정렬·필터를 쉽게 만든다. */
export type Signal = {
  key: string;
  d: string;
  strategy: Strategy;
  ticker: string;
  name: string;
  score: number;
  rank: number | null;
  sent: boolean;
  suppressed: boolean;
  close: number;
  change: number;
  amount: number;
  inProgress: boolean;
  conditions: Condition[];
};

export function toSignal(row: SignalRow): Signal {
  const ev = row.evidence;
  return {
    key: `${row.strategy}:${row.ticker}`,
    d: row.d,
    strategy: row.strategy,
    ticker: row.ticker,
    name: row.name || row.ticker,
    score: row.score,
    rank: row.rank_no,
    sent: row.sent_kakao,
    suppressed: row.suppressed,
    close: ev?.price?.close ?? 0,
    change: ev?.price?.change_pct ?? 0,
    amount: ev?.volume?.amount ?? 0,
    inProgress: ev?.meta?.in_progress ?? false,
    conditions: ev?.conditions ?? [],
  };
}
