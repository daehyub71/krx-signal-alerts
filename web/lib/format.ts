/** 표시용 포맷 — 순수 함수. */

const DOW = ["일", "월", "화", "수", "목", "금", "토"];

/** `2026-08-14` → `08-14` */
export function md(iso: string): string {
  return iso.slice(5);
}

/**
 * `2026-08-14` → `2026-08-14 (금)`
 *
 * 시간대를 아예 끌어들이지 않는다. `new Date("...T00:00:00+09:00")`으로 만들고
 * `getUTCDay()`로 읽으면 KST 자정이 전날 15:00 UTC라 **요일이 하루 밀린다.**
 */
export function withDow(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${iso} (${DOW[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]})`;
}

/** 원 단위를 억/조로 줄인다. 표에서 자릿수를 맞추기 위해서다. */
export function eok(won: number): string {
  if (won >= 1e12) return `${(won / 1e12).toFixed(1)}조`;
  if (won >= 1e8) return `${Math.round(won / 1e8).toLocaleString()}억`;
  if (won >= 1e4) return `${Math.round(won / 1e4).toLocaleString()}만`;
  return won.toLocaleString();
}

export function pct(v: number): string {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

/** KRX 규약 — 적색 상승 · 청색 하락. 서구 관례와 반대다 (DESIGN §4). */
export function tone(v: number): "up" | "down" | "flat" {
  return v > 0 ? "up" : v < 0 ? "down" : "flat";
}
