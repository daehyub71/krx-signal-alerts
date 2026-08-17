/**
 * Supabase 조회 — 서버에서만 부른다.
 *
 * **anon 키만 쓴다.** `service_role`은 웹 번들에 절대 들어가면 안 된다 (SPEC N4).
 * anon은 `ksa_*`에 SELECT만 가능하고, 쓰기는 RLS가 막는다 (실제로 확인함).
 */

import { createClient } from "@supabase/supabase-js";
import { type RunRow, type Signal, type SignalRow, toSignal } from "./types";

// 신호는 하루 한 번만 바뀐다. 수동 실행이 있을 수 있어 10분으로 둔다.
export const revalidate = 600;

function client() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) {
    throw new Error(
      "NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY가 없다. " +
        "Vercel 환경변수를 확인하라.",
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

/** 신호가 있는 날짜들 — 최신순. 날짜 스트립이 쓴다 (F17). */
export async function fetchDates(limit = 30): Promise<string[]> {
  const { data, error } = await client()
    .from("ksa_signals")
    .select("d")
    .order("d", { ascending: false })
    .limit(2000);
  if (error) throw new Error(`날짜 조회 실패: ${error.message}`);
  const seen = new Set<string>();
  for (const row of data ?? []) seen.add((row as { d: string }).d);
  return [...seen].slice(0, limit);
}

/** 하루치 신호 전부 (F15). 억제된 것도 포함해 돌려주고, 숨기는 것은 화면이 정한다. */
export async function fetchSignals(date: string): Promise<Signal[]> {
  const { data, error } = await client()
    .from("ksa_signals")
    .select("d,strategy,ticker,name,score,rank_no,sent_kakao,sent_email,suppressed,evidence")
    .eq("d", date)
    // 하루 수십 건이지만 상한을 명시해 둔다. Supabase는 1000행에서 조용히 자른다.
    .limit(1000);
  if (error) throw new Error(`신호 조회 실패: ${error.message}`);
  return (data as SignalRow[]).map(toSignal);
}

/** 그 날짜의 배치 실행 기록. 없으면 null — 없는 것도 정보다. */
export async function fetchRun(date: string): Promise<RunRow | null> {
  const { data, error } = await client()
    .from("ksa_runs")
    .select("run_at,data_date,universe_n,signal_n,sent_kakao_n,sent_email_n,status")
    .eq("data_date", date)
    .order("run_at", { ascending: false })
    .limit(1);
  if (error) throw new Error(`실행 기록 조회 실패: ${error.message}`);
  return (data as RunRow[])[0] ?? null;
}
