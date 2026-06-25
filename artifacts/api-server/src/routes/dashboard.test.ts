import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import {
  clearAllTables,
  seedInstitutional,
  seedInsiders,
  seedPoliticians,
  seedLockups,
} from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/dashboard/stats", () => {
  it("returns zero counts on empty DB", async () => {
    const res = await request(app).get("/api/dashboard/stats").expect(200);
    expect(res.body).toMatchObject({
      totalInsiderTrades: 0,
      totalInstitutionalChanges: 0,
      totalPoliticianTrades: 0,
      lockupsThisMonth: 0,
      netBuyPressure: 0,
    });
  });

  it("counts seeded rows correctly", async () => {
    await seedInstitutional();  // 2 rows
    await seedInsiders();       // 2 rows
    await seedPoliticians();    // 2 rows
    const res = await request(app).get("/api/dashboard/stats").expect(200);
    expect(res.body.totalInsiderTrades).toBe(2);
    expect(res.body.totalInstitutionalChanges).toBe(2);
    expect(res.body.totalPoliticianTrades).toBe(2);
  });

  it("netBuyPressure is 0 when all insider trades are sells", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "XYZ", companyName: "XYZ Corp",
      transactionType: "sell", shares: "100", pricePerShare: "10.00", totalValue: "1000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/dashboard/stats").expect(200);
    expect(res.body.netBuyPressure).toBe(0);
  });

  it("netBuyPressure is 1 when all insider trades are buys", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "XYZ", companyName: "XYZ Corp",
      transactionType: "buy", shares: "100", pricePerShare: "10.00", totalValue: "1000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/dashboard/stats").expect(200);
    expect(res.body.netBuyPressure).toBe(1);
  });

  it("response has all required schema fields", async () => {
    const res = await request(app).get("/api/dashboard/stats").expect(200);
    expect(res.body).toHaveProperty("totalInsiderTrades");
    expect(res.body).toHaveProperty("totalInstitutionalChanges");
    expect(res.body).toHaveProperty("totalPoliticianTrades");
    expect(res.body).toHaveProperty("lockupsThisMonth");
    expect(res.body).toHaveProperty("netBuyPressure");
  });
});

describe("GET /api/dashboard/signals", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns a signal entry per ticker with correct shape", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    const item = res.body[0];
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("signalScore");
    expect(item).toHaveProperty("institutionalBuys");
    expect(item).toHaveProperty("institutionalSells");
    expect(item).toHaveProperty("insiderBuys");
    expect(item).toHaveProperty("insiderSells");
    expect(item).toHaveProperty("politicianBuys");
    expect(item).toHaveProperty("politicianSells");
    expect(item).toHaveProperty("lockupExpiring");
  });

  it("signalScore is positive for pure buy activity", async () => {
    await seedInstitutional([{
      institutionName: "Fund A", ticker: "BULL", companyName: "Bull Co",
      action: "buy", sharesChange: "1000000", valueChange: "100000000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    const bull = res.body.find((s: any) => s.ticker === "BULL");
    expect(bull).toBeDefined();
    expect(bull.signalScore).toBeGreaterThan(0);
  });

  it("signalScore is negative for pure sell activity", async () => {
    await seedInstitutional([{
      institutionName: "Fund B", ticker: "BEAR", companyName: "Bear Co",
      action: "sell", sharesChange: "-1000000", valueChange: "-100000000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    const bear = res.body.find((s: any) => s.ticker === "BEAR");
    expect(bear).toBeDefined();
    expect(bear.signalScore).toBeLessThan(0);
  });

  it("respects limit query param", async () => {
    await seedInstitutional();
    await seedInsiders();
    const res = await request(app).get("/api/dashboard/signals?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });

  it("results are sorted by absolute signal score descending", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    const scores = res.body.map((s: any) => Math.abs(s.signalScore));
    for (let i = 1; i < scores.length; i++) {
      expect(scores[i - 1]).toBeGreaterThanOrEqual(scores[i]);
    }
  });

  it("marks lockupExpiring true for tickers with upcoming lockups", async () => {
    await seedLockups([{
      ticker: "RDDT", companyName: "Reddit Inc.", expirationDate: "2026-08-01",
      sharesUnlocking: "50000000", estimatedValue: "3000000000", ipoDate: "2026-03-21", status: "upcoming",
    }]);
    await seedInstitutional([{
      institutionName: "F", ticker: "RDDT", companyName: "Reddit Inc.",
      action: "buy", sharesChange: "100", valueChange: "1000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/dashboard/signals").expect(200);
    const rddt = res.body.find((s: any) => s.ticker === "RDDT");
    expect(rddt?.lockupExpiring).toBe(true);
  });
});

describe("GET /api/dashboard/activity", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/dashboard/activity").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns items with correct shape", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/dashboard/activity").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    const item = res.body[0];
    expect(item).toHaveProperty("id");
    expect(item).toHaveProperty("category");
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("title");
    expect(item).toHaveProperty("direction");
    expect(item).toHaveProperty("date");
    expect(item).toHaveProperty("source");
  });

  it("assigns correct category per source", async () => {
    await seedInsiders();
    await seedInstitutional();
    await seedPoliticians();
    await seedLockups();
    const res = await request(app).get("/api/dashboard/activity?limit=100").expect(200);
    const categories = new Set(res.body.map((i: any) => i.category));
    expect(categories.has("insider")).toBe(true);
    expect(categories.has("institutional")).toBe(true);
    expect(categories.has("politician")).toBe(true);
    expect(categories.has("lockup")).toBe(true);
  });

  it("insider buy has direction=buy", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "AAPL", companyName: "Apple Inc.",
      transactionType: "buy", shares: "100", pricePerShare: "180.00", totalValue: "18000",
      transactionDate: "2026-06-01", filingDate: "2026-06-03", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/dashboard/activity").expect(200);
    const item = res.body.find((i: any) => i.category === "insider");
    expect(item.direction).toBe("buy");
  });

  it("respects limit query param", async () => {
    await seedInsiders();
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/activity?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });

  it("items are sorted by date descending", async () => {
    await seedInsiders();
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/activity?limit=50").expect(200);
    const dates = res.body.map((i: any) => new Date(i.date).getTime());
    for (let i = 1; i < dates.length; i++) {
      expect(dates[i - 1]).toBeGreaterThanOrEqual(dates[i]);
    }
  });
});

describe("GET /api/dashboard/money-flow", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns items with correct shape", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    const item = res.body[0];
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("totalInflow");
    expect(item).toHaveProperty("totalOutflow");
    expect(item).toHaveProperty("netFlow");
    expect(item).toHaveProperty("institutionalInflow");
    expect(item).toHaveProperty("institutionalOutflow");
    expect(item).toHaveProperty("insiderInflow");
    expect(item).toHaveProperty("insiderOutflow");
  });

  it("institutional buy contributes to inflow", async () => {
    await seedInstitutional([{
      institutionName: "F", ticker: "AAPL", companyName: "Apple Inc.",
      action: "buy", sharesChange: "1000", valueChange: "150000000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    const aapl = res.body.find((m: any) => m.ticker === "AAPL");
    expect(aapl.institutionalInflow).toBe(150000000);
    expect(aapl.netFlow).toBeGreaterThan(0);
  });

  it("institutional sell contributes to outflow", async () => {
    await seedInstitutional([{
      institutionName: "F", ticker: "TSLA", companyName: "Tesla Inc.",
      action: "sell", sharesChange: "-1000", valueChange: "-90000000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    const tsla = res.body.find((m: any) => m.ticker === "TSLA");
    expect(tsla.institutionalOutflow).toBe(90000000);
    expect(tsla.netFlow).toBeLessThan(0);
  });

  it("insider buy contributes to insiderInflow", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "NFLX", companyName: "Netflix Inc.",
      transactionType: "buy", shares: "1000", pricePerShare: "600.00", totalValue: "600000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    const nflx = res.body.find((m: any) => m.ticker === "NFLX");
    expect(nflx.insiderInflow).toBe(600000);
  });

  it("sorted by absolute netFlow descending", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/dashboard/money-flow").expect(200);
    const netFlows = res.body.map((m: any) => Math.abs(m.netFlow));
    for (let i = 1; i < netFlows.length; i++) {
      expect(netFlows[i - 1]).toBeGreaterThanOrEqual(netFlows[i]);
    }
  });

  it("respects limit query param", async () => {
    await seedInstitutional();
    await seedInsiders();
    const res = await request(app).get("/api/dashboard/money-flow?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });
});
