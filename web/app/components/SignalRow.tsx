"use client";

import { eok, pct, tone } from "@/lib/format";
import { STRATEGY_LABEL, STRATEGY_SHORT, type Signal } from "@/lib/types";

const CHART_URL = "https://krx-stock-charts.vercel.app";

const TONE_CLASS = {
  up: "text-up",
  down: "text-down",
  flat: "text-faint",
} as const;

type Props = {
  signal: Signal;
  open: boolean;
  onToggle: (key: string) => void;
};

/**
 * 신호 한 행. 누르면 조건별 근거값이 같은 자리에서 펼쳐진다 (F16).
 *
 * 페이지를 옮기지 않는 것이 핵심이다 — 목록과 상세를 오가며 뒤로가기를 반복하게 하면
 * 훑어보는 흐름이 끊긴다 (DESIGN §2).
 */
export function SignalRow({ signal: s, open, onToggle }: Props) {
  return (
    <>
      <button
        type="button"
        onClick={() => onToggle(s.key)}
        aria-expanded={open}
        className={`grid w-full grid-cols-[32px_1fr_auto] items-baseline gap-x-3 gap-y-1
          border-b border-line px-4 py-3 text-left hover:bg-raise
          sm:grid-cols-[44px_84px_1fr_96px_78px_88px_24px] sm:items-center sm:py-0 sm:min-h-[52px]
          ${s.suppressed ? "opacity-45" : ""}`}
      >
        {/* 순위 배지 — 채워져 있으면 아침에 카카오로 받은 그 10건이다 */}
        <span
          className={`row-span-2 grid h-6 w-6 place-items-center rounded-[5px] font-mono
            text-xs tnum sm:row-span-1
            ${s.sent ? "bg-up font-semibold text-white" : "text-faint"}`}
        >
          {s.rank ?? "·"}
        </span>

        <span className="order-3 text-[11.5px] text-muted sm:order-none sm:text-[12.5px] sm:text-ink-2">
          {STRATEGY_SHORT[s.strategy]}
        </span>

        <span className="flex min-w-0 items-baseline gap-2">
          <b className="truncate font-semibold tracking-[-0.01em]">{s.name}</b>
          <span className="font-mono text-[11.5px] text-faint">{s.ticker}</span>
          {s.inProgress && (
            <span className="shrink-0 rounded border border-line-2 px-1.5 py-px text-[10.5px] text-muted">
              진행중
            </span>
          )}
          {s.suppressed && (
            <span className="shrink-0 rounded bg-sunk px-1.5 py-px text-[10.5px] text-muted">
              억제
            </span>
          )}
        </span>

        <span className="text-right font-mono text-[13.5px] tnum">
          {s.close.toLocaleString()}
        </span>

        <span
          className={`order-4 text-right font-mono text-[13px] tnum sm:order-none ${TONE_CLASS[tone(s.change)]}`}
        >
          {pct(s.change)}
        </span>

        <span className="hidden text-right font-mono text-[12.5px] tnum text-muted sm:block">
          {eok(s.amount)}
        </span>

        <span
          aria-hidden
          className={`hidden text-[11px] text-faint transition-transform sm:block ${open ? "rotate-90" : ""}`}
        >
          ▶
        </span>
      </button>

      {open && (
        <div className="border-b border-line bg-sunk px-4 py-4 sm:pl-[60px]">
          <ul className="flex flex-col gap-[7px]">
            {s.conditions.map((c) => (
              <li
                key={c.label}
                className="grid grid-cols-[18px_1fr] items-baseline gap-2.5 text-[13.5px]
                  sm:grid-cols-[18px_1fr_auto]"
              >
                <span className={`text-xs ${c.ok ? "text-up" : "text-faint"}`}>
                  {c.ok ? "✓" : "✗"}
                </span>
                <span className="text-ink-2">{c.label}</span>
                <span
                  className="col-start-2 font-mono text-[12.5px] tnum text-muted
                    sm:col-start-3 sm:text-right sm:text-ink"
                >
                  {c.actual}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-3.5 flex flex-wrap items-center gap-3.5 border-t border-line pt-3 text-[12.5px]">
            <span className="font-mono text-muted">
              {STRATEGY_LABEL[s.strategy]} · 점수 {s.score.toFixed(3)}
            </span>
            <a
              href={`${CHART_URL}/?ticker=${s.ticker}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-up hover:underline"
            >
              차트에서 보기 ↗
            </a>
          </div>
        </div>
      )}
    </>
  );
}
