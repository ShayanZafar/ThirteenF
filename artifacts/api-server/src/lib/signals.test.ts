import { describe, it, expect } from "vitest";
import { computeSignalScore, computeMoneyFlow } from "./signals";

describe("computeSignalScore", () => {
  it("returns +100 for pure buy pressure with no sells", () => {
    const score = computeSignalScore({ instBuys: 5, instSells: 0, insBuys: 5, insSells: 0, polBuys: 5, polSells: 0, lockupExpiring: false });
    expect(score).toBe(100);
  });

  it("returns -100 for pure sell pressure with no buys", () => {
    const score = computeSignalScore({ instBuys: 0, instSells: 5, insBuys: 0, insSells: 5, polBuys: 0, polSells: 5, lockupExpiring: false });
    expect(score).toBe(-100);
  });

  it("returns 0 when buy and sell pressure are equal", () => {
    // instBuys=2 → 2*2=4, instSells=2 → 2*2=4, no lockup
    const score = computeSignalScore({ instBuys: 2, instSells: 2, insBuys: 0, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false });
    expect(score).toBe(0);
  });

  it("penalises lockup expiring (adds 10 to sell signal)", () => {
    // pure buy but lockup expiring adds bearish weight
    const noLockup = computeSignalScore({ instBuys: 1, instSells: 0, insBuys: 0, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false });
    const withLockup = computeSignalScore({ instBuys: 1, instSells: 0, insBuys: 0, insBuys: 0, polBuys: 0, polSells: 0, lockupExpiring: true });
    expect(withLockup).toBeLessThan(noLockup);
  });

  it("weights insiders (x3) higher than institutions (x2)", () => {
    const instHeavy = computeSignalScore({ instBuys: 3, instSells: 0, insBuys: 0, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false });
    const insHeavy = computeSignalScore({ instBuys: 0, instSells: 0, insBuys: 3, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false });
    // Both are pure buy so score is 100 — weight shows up in mixed scenarios
    const mixed = computeSignalScore({ instBuys: 1, instSells: 0, insBuys: 0, insSells: 1, polBuys: 0, polSells: 0, lockupExpiring: false });
    // instBuy=2, insSell=3, sell > buy so score < 0
    expect(mixed).toBeLessThan(0);
  });

  it("clamps score to [-100, 100]", () => {
    const score = computeSignalScore({ instBuys: 1000, instSells: 0, insBuys: 1000, insSells: 0, polBuys: 1000, polSells: 0, lockupExpiring: false });
    expect(score).toBeLessThanOrEqual(100);
    expect(score).toBeGreaterThanOrEqual(-100);
  });

  it("returns 100 when all counts are zero and no lockup (treats as no pressure = neutral but avoids div/0)", () => {
    // total = 0 → coerced to 1 → score = (0-0)/1 * 100 = 0
    const score = computeSignalScore({ instBuys: 0, instSells: 0, insBuys: 0, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false });
    expect(score).toBe(0);
  });

  it("politicians weighted at x1.5", () => {
    // polBuys=2 → 3.0, instSells=1 → 2.0, so buy > sell
    const score = computeSignalScore({ instBuys: 0, instSells: 1, insBuys: 0, insSells: 0, polBuys: 2, polSells: 0, lockupExpiring: false });
    expect(score).toBeGreaterThan(0);
  });
});

describe("computeMoneyFlow", () => {
  const base = {
    ticker: "AAPL",
    companyName: "Apple Inc.",
    institutionalInflow: 1_000_000,
    institutionalOutflow: 300_000,
    insiderInflow: 50_000,
    insiderOutflow: 0,
  };

  it("computes totalInflow as sum of institutional + insider inflows", () => {
    const result = computeMoneyFlow(base);
    expect(result.totalInflow).toBe(1_050_000);
  });

  it("computes totalOutflow as sum of institutional + insider outflows", () => {
    const result = computeMoneyFlow(base);
    expect(result.totalOutflow).toBe(300_000);
  });

  it("computes positive netFlow when inflow > outflow", () => {
    const result = computeMoneyFlow(base);
    expect(result.netFlow).toBe(750_000);
  });

  it("computes negative netFlow when outflow > inflow", () => {
    const result = computeMoneyFlow({
      ...base,
      institutionalInflow: 0,
      institutionalOutflow: 5_000_000,
      insiderInflow: 0,
      insiderOutflow: 2_000_000,
    });
    expect(result.netFlow).toBe(-7_000_000);
  });

  it("returns zero netFlow when perfectly balanced", () => {
    const result = computeMoneyFlow({
      ...base,
      institutionalInflow: 500_000,
      institutionalOutflow: 500_000,
      insiderInflow: 0,
      insiderOutflow: 0,
    });
    expect(result.netFlow).toBe(0);
  });

  it("preserves ticker and companyName on the result", () => {
    const result = computeMoneyFlow(base);
    expect(result.ticker).toBe("AAPL");
    expect(result.companyName).toBe("Apple Inc.");
  });

  it("handles all-zero case without NaN", () => {
    const result = computeMoneyFlow({ ...base, institutionalInflow: 0, institutionalOutflow: 0, insiderInflow: 0, insiderOutflow: 0 });
    expect(result.netFlow).toBe(0);
    expect(result.totalInflow).toBe(0);
    expect(result.totalOutflow).toBe(0);
  });
});
