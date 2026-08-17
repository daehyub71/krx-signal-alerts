import { describe, expect, it } from "vitest";
import { eok, md, pct, tone, withDow } from "../format";

describe("withDow", () => {
  it("요일을 맞게 붙인다", () => {
    // 2026-08-14는 금요일. KST 자정을 UTC로 읽으면 하루 밀려 목요일이 된다.
    expect(withDow("2026-08-14")).toBe("2026-08-14 (금)");
    expect(withDow("2026-08-17")).toBe("2026-08-17 (월)");
  });

  it("월 경계에서도 밀리지 않는다", () => {
    expect(withDow("2026-08-01")).toBe("2026-08-01 (토)");
    expect(withDow("2026-09-01")).toBe("2026-09-01 (화)");
  });

  it("연 경계에서도 밀리지 않는다", () => {
    expect(withDow("2027-01-01")).toBe("2027-01-01 (금)");
  });
});

describe("eok", () => {
  it("자릿수를 줄여 표 폭을 맞춘다", () => {
    expect(eok(4_100_000_000)).toBe("41억");
    expect(eok(879_000_000_000)).toBe("8,790억");
    expect(eok(1_500_000_000_000)).toBe("1.5조");
    expect(eok(50_000)).toBe("5만");
  });

  it("0을 삼키지 않는다", () => {
    expect(eok(0)).toBe("0");
  });
});

describe("pct", () => {
  it("상승에만 부호를 붙인다", () => {
    expect(pct(2.14)).toBe("+2.14%");
    expect(pct(-0.39)).toBe("-0.39%");
    expect(pct(0)).toBe("0.00%");
  });
});

describe("tone", () => {
  it("KRX 규약 — 상승이 up(적색), 하락이 down(청색)", () => {
    expect(tone(1)).toBe("up");
    expect(tone(-1)).toBe("down");
    expect(tone(0)).toBe("flat");
  });
});

describe("md", () => {
  it("월-일만 남긴다", () => {
    expect(md("2026-08-14")).toBe("08-14");
  });
});
