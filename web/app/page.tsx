import Link from "next/link";
import { SignalBoard } from "./components/SignalBoard";
import { fetchDates, fetchRun, fetchSignals } from "@/lib/data";
import { md, withDow } from "@/lib/format";

export const revalidate = 600;

const REPO = "https://github.com/daehyub71/krx-signal-alerts";

type Props = { searchParams: Promise<{ d?: string }> };

export default async function Page({ searchParams }: Props) {
  const { d } = await searchParams;
  const dates = await fetchDates();

  if (dates.length === 0) {
    return (
      <main className="mx-auto max-w-[1080px] px-5 py-16">
        <p className="text-center text-muted">
          아직 신호가 없습니다. 배치가 한 번도 돌지 않았거나 저장에 실패했습니다.
        </p>
      </main>
    );
  }

  // 잘못된 날짜가 들어와도 빈 화면을 보여주지 않는다 — 최신으로 되돌린다.
  const date = d && dates.includes(d) ? d : dates[0];
  const [signals, run] = await Promise.all([fetchSignals(date), fetchRun(date)]);
  const stale = run?.status === "stale_data";

  return (
    <main className="mx-auto max-w-[1080px] px-5 pb-16">
      <header className="flex flex-wrap items-baseline justify-between gap-4 pt-7 pb-4">
        <div>
          <div className="font-mono text-[13px] tracking-[0.06em] text-muted">
            krx-signal-alerts
          </div>
          <h1 className="text-2xl font-extrabold tracking-[-0.025em]">
            {withDow(date)}
            <span className="ml-2 text-sm font-medium text-muted">기준</span>
          </h1>
        </div>
        <a
          href={REPO}
          target="_blank"
          rel="noopener noreferrer"
          className="font-mono text-[12px] text-muted hover:text-ink"
        >
          GitHub ↗
        </a>
      </header>

      {stale && (
        <p className="mb-3 rounded-lg border border-down bg-down-w px-4 py-3 text-[13.5px] text-down">
          ⚠ 이 날은 시세가 갱신되지 않아 신호를 만들지 않았습니다. 0건인 것이 정상입니다.
        </p>
      )}

      {/* 날짜 스트립 (F17) — 페이지를 옮기지 않고 날짜만 갈아 끼운다 */}
      <nav
        aria-label="날짜"
        className="flex items-center gap-1 overflow-x-auto rounded-lg border border-line
          bg-surface px-3 py-2.5"
      >
        {[...dates].slice(0, 12).reverse().map((x) => {
          const cur = x === date;
          return (
            <Link
              key={x}
              href={cur ? "/" : `/?d=${x}`}
              aria-current={cur}
              className={`whitespace-nowrap rounded-[5px] px-3 py-1.5 font-mono text-[13px]
                ${cur ? "bg-ink font-semibold text-surface" : "text-muted hover:bg-sunk hover:text-ink"}`}
            >
              {md(x)}
            </Link>
          );
        })}
        {run && (
          <span className="ml-auto whitespace-nowrap pl-3 text-[12.5px] text-muted">
            유니버스 <span className="tnum">{run.universe_n.toLocaleString()}</span> · 신호{" "}
            <span className="tnum">{run.signal_n}</span>건
          </span>
        )}
      </nav>

      <SignalBoard signals={signals} />

      {run && (
        <div
          className="mt-3 flex flex-wrap items-center gap-3.5 rounded-lg border border-line
            bg-surface px-4 py-3 text-[12.5px] text-muted"
        >
          <span
            className={`h-[7px] w-[7px] rounded-full ${run.status === "ok" ? "bg-up" : "bg-down"}`}
          />
          <span>
            배치 <span className="font-mono text-ink-2">{run.run_at.slice(11, 16)}</span>
          </span>
          <span>
            카카오 <span className="font-mono text-ink-2 tnum">{run.sent_kakao_n}</span> · 메일{" "}
            <span className="font-mono text-ink-2 tnum">{run.sent_email_n}</span>
          </span>
          <span>
            상태 <span className="font-mono text-ink-2">{run.status}</span>
          </span>
        </div>
      )}

      <p className="mt-3.5 text-[12.5px] leading-7 text-muted">
        카카오톡은 상위 10건만 보냅니다(본문 200자 상한). 나머지는 메일과 이 화면에 있습니다 —
        순위 배지가 채워진 것이 아침에 폰으로 받은 그 10건입니다.
        <br />
        신호는 <b className="text-ink-2">관찰 후보 목록</b>이지 매매 지시가 아닙니다.
      </p>
    </main>
  );
}
