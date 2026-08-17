"use client";

import { useMemo, useState } from "react";
import { SignalRow } from "./SignalRow";
import { STRATEGIES, STRATEGY_SHORT, type Signal, type Strategy } from "@/lib/types";

type Scope = "all" | "sent" | "suppressed";
type Sort = "rank" | "score" | "amount" | "change";

const SCOPES: { id: Scope; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "sent", label: "카카오 발송분" },
  { id: "suppressed", label: "억제분 포함" },
];

const SORTS: { id: Sort; label: string }[] = [
  { id: "rank", label: "순위순" },
  { id: "score", label: "점수순" },
  { id: "amount", label: "거래대금순" },
  { id: "change", label: "등락률순" },
];

const COMPARE: Record<Sort, (a: Signal, b: Signal) => number> = {
  // 순위가 없는 신호(발송 상한에 밀린 것)는 뒤로 보내되 점수순은 유지한다.
  rank: (a, b) => (a.rank ?? 999) - (b.rank ?? 999) || b.score - a.score,
  score: (a, b) => b.score - a.score,
  amount: (a, b) => b.amount - a.amount,
  change: (a, b) => b.change - a.change,
};

/**
 * 신호판 (F15).
 *
 * 하루 수십 건이라 전부 받아 두고 필터·정렬을 메모리에서 한다.
 * 서버 왕복을 만들 이유가 없다 (DESIGN §6).
 */
export function SignalBoard({ signals }: { signals: Signal[] }) {
  const [scope, setScope] = useState<Scope>("all");
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [sort, setSort] = useState<Sort>("rank");
  const [open, setOpen] = useState<string | null>(null);

  // 억제된 신호는 저장은 되지만 알림에 안 나간 것이다. 기본은 숨긴다 (W6).
  const live = useMemo(() => signals.filter((s) => !s.suppressed), [signals]);

  const counts = useMemo(() => {
    const c = {} as Record<Strategy, number>;
    for (const k of STRATEGIES) c[k] = live.filter((s) => s.strategy === k).length;
    return c;
  }, [live]);

  const max = Math.max(1, ...Object.values(counts));

  const rows = useMemo(() => {
    let out = scope === "suppressed" ? signals : live;
    if (scope === "sent") out = out.filter((s) => s.sent);
    if (strategy) out = out.filter((s) => s.strategy === strategy);
    return [...out].sort(COMPARE[sort]);
  }, [signals, live, scope, strategy, sort]);

  return (
    <>
      {/* 전략 타일 — 요약이자 필터다 */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
        {STRATEGIES.map((k) => {
          const on = strategy === k;
          return (
            <button
              key={k}
              type="button"
              aria-pressed={on}
              onClick={() => {
                setStrategy(on ? null : k);
                setOpen(null);
              }}
              className={`flex flex-col gap-0.5 rounded-lg border px-3.5 py-3 text-left transition-colors
                ${on ? "border-up bg-up-w" : "border-line bg-surface hover:border-line-2"}`}
            >
              <span className={`text-[12.5px] ${on ? "text-up" : "text-muted"}`}>
                {STRATEGY_SHORT[k]}
              </span>
              <span
                className={`font-mono text-2xl font-semibold leading-tight tnum
                  ${counts[k] ? "" : "text-faint"}`}
              >
                {counts[k]}
              </span>
              <span className="mt-1 h-[3px] overflow-hidden rounded-sm bg-line">
                <i
                  className="block h-full bg-up"
                  style={{ width: `${(counts[k] / max) * 100}%` }}
                />
              </span>
            </button>
          );
        })}
      </div>

      {/* 도구 막대 */}
      <div className="flex flex-wrap items-center gap-2 py-3.5">
        <div className="flex overflow-hidden rounded-md border border-line bg-surface">
          {SCOPES.map((s, i) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={scope === s.id}
              onClick={() => {
                setScope(s.id);
                setOpen(null);
              }}
              className={`px-3 py-1.5 text-[13px] whitespace-nowrap
                ${i > 0 ? "border-l border-line" : ""}
                ${scope === s.id ? "bg-ink font-semibold text-surface" : "text-muted"}`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-[13px] text-muted tnum">{rows.length}건</span>
          <label className="sr-only" htmlFor="sort">
            정렬
          </label>
          <select
            id="sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as Sort)}
            className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-[13px] text-ink"
          >
            {SORTS.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* 표 (모바일에서는 카드로 접힌다 — SignalRow의 grid가 바뀐다) */}
      <div className="overflow-hidden rounded-lg border border-line bg-surface">
        <div
          className="hidden h-[38px] grid-cols-[44px_84px_1fr_96px_78px_88px_24px] items-center
            gap-3 border-b border-line bg-sunk px-4 font-mono text-[11px] uppercase
            tracking-[0.08em] text-muted sm:grid"
        >
          <div>#</div>
          <div>전략</div>
          <div>종목</div>
          <div className="text-right">종가</div>
          <div className="text-right">등락</div>
          <div className="text-right">거래대금</div>
          <div />
        </div>

        {rows.length === 0 ? (
          <p className="px-5 py-12 text-center text-sm text-muted">
            조건에 맞는 신호가 없습니다.
          </p>
        ) : (
          rows.map((s) => (
            <SignalRow
              key={s.key}
              signal={s}
              open={open === s.key}
              onToggle={(k) => setOpen(open === k ? null : k)}
            />
          ))
        )}
      </div>
    </>
  );
}
