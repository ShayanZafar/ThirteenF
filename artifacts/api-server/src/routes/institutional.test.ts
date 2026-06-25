import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import { clearAllTables, seedInstitutional } from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/institutional", () => {
  it("returns empty page on empty DB", async () => {
    const res = await request(app).get("/api/institutional").expect(200);
    expect(res.body).toMatchObject({ data: [], total: 0 });
  });

  it("returns seeded rows with correct shape", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional").expect(200);
    expect(res.body.total).toBe(2);
    expect(res.body.data.length).toBe(2);
    const item = res.body.data[0];
    expect(item).toHaveProperty("id");
    expect(item).toHaveProperty("institutionName");
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("action");
    expect(item).toHaveProperty("sharesChange");
    expect(item).toHaveProperty("valueChange");
    expect(item).toHaveProperty("reportDate");
    expect(item).toHaveProperty("filingDate");
    expect(item).toHaveProperty("quarter");
  });

  it("filters by ticker", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional?ticker=AAPL").expect(200);
    expect(res.body.total).toBe(1);
    expect(res.body.data[0].ticker).toBe("AAPL");
  });

  it("ticker filter is case-insensitive (upcases automatically)", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional?ticker=aapl").expect(200);
    expect(res.body.total).toBe(1);
  });

  it("filters by action=buy", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional?action=buy").expect(200);
    expect(res.body.data.every((r: any) => r.action === "buy")).toBe(true);
  });

  it("filters by action=sell", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional?action=sell").expect(200);
    expect(res.body.data.every((r: any) => r.action === "sell")).toBe(true);
  });

  it("paginates with limit and offset", async () => {
    await seedInstitutional();
    const page1 = await request(app).get("/api/institutional?limit=1&offset=0").expect(200);
    const page2 = await request(app).get("/api/institutional?limit=1&offset=1").expect(200);
    expect(page1.body.data.length).toBe(1);
    expect(page2.body.data.length).toBe(1);
    expect(page1.body.data[0].id).not.toBe(page2.body.data[0].id);
    expect(page1.body.total).toBe(2);
  });

  it("numeric fields are numbers not strings", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional").expect(200);
    const item = res.body.data[0];
    expect(typeof item.sharesChange).toBe("number");
    expect(typeof item.valueChange).toBe("number");
  });
});

describe("GET /api/institutional/top-movers", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/institutional/top-movers").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns movers with correct shape", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional/top-movers").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    const item = res.body[0];
    expect(item).toHaveProperty("institutionName");
    expect(item).toHaveProperty("netValueChange");
    expect(item).toHaveProperty("buysCount");
    expect(item).toHaveProperty("sellsCount");
  });

  it("respects limit param", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional/top-movers?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });

  it("buy institution has positive netValueChange", async () => {
    await seedInstitutional([{
      institutionName: "Bull Fund", ticker: "AAPL", companyName: "Apple Inc.",
      action: "buy", sharesChange: "1000", valueChange: "100000000",
      reportDate: "2026-05-15", filingDate: "2026-05-15", quarter: "Q1 2026",
    }]);
    const res = await request(app).get("/api/institutional/top-movers").expect(200);
    const bull = res.body.find((m: any) => m.institutionName === "Bull Fund");
    expect(bull.netValueChange).toBeGreaterThan(0);
    expect(bull.buysCount).toBe(1);
    expect(bull.sellsCount).toBe(0);
  });
});

describe("GET /api/institutional/most-bought", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/institutional/most-bought").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns correct shape", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional/most-bought").expect(200);
    const item = res.body[0];
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("count");
    expect(item).toHaveProperty("totalValue");
  });

  it("only includes buy/increase actions", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional/most-bought").expect(200);
    // TSLA is only a sell in seed data — should not appear
    const tsla = res.body.find((m: any) => m.ticker === "TSLA");
    expect(tsla).toBeUndefined();
  });

  it("respects limit param", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/institutional/most-bought?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });
});
