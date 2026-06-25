import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import { clearAllTables, seedInsiders, seedInstitutional, seedPoliticians, seedLockups } from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/stocks/search", () => {
  it("returns empty array for empty DB", async () => {
    const res = await request(app).get("/api/stocks/search?q=AAPL").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns empty array for empty query", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=").expect(200);
    expect(res.body).toEqual([]);
  });

  it("finds ticker by exact match", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=AAPL").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    expect(res.body[0].ticker).toBe("AAPL");
  });

  it("search is case-insensitive", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=aapl").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
  });

  it("finds by partial company name", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=Apple").expect(200);
    expect(res.body.some((r: any) => r.ticker === "AAPL")).toBe(true);
  });

  it("returns results with ticker and companyName fields", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=AAPL").expect(200);
    expect(res.body[0]).toHaveProperty("ticker");
    expect(res.body[0]).toHaveProperty("companyName");
  });

  it("deduplicates tickers appearing in multiple tables", async () => {
    await seedInsiders();
    await seedInstitutional();
    await seedPoliticians();
    const res = await request(app).get("/api/stocks/search?q=AAPL").expect(200);
    const aaplResults = res.body.filter((r: any) => r.ticker === "AAPL");
    expect(aaplResults.length).toBe(1);
  });

  it("returns no results for unknown ticker", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/search?q=ZZZZ").expect(200);
    expect(res.body).toEqual([]);
  });
});

describe("GET /api/stocks/:ticker/signals", () => {
  it("returns 404 for unknown ticker", async () => {
    await request(app).get("/api/stocks/ZZZZ/signals").expect(404);
  });

  it("returns 200 with correct shape for known ticker", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/AAPL/signals").expect(200);
    expect(res.body).toHaveProperty("ticker", "AAPL");
    expect(res.body).toHaveProperty("companyName");
    expect(res.body).toHaveProperty("recentInsiderTrades");
    expect(res.body).toHaveProperty("recentInstitutionalChanges");
    expect(res.body).toHaveProperty("recentPoliticianTrades");
    expect(res.body).toHaveProperty("lockups");
  });

  it("is case-insensitive for ticker param", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/aapl/signals").expect(200);
    expect(res.body.ticker).toBe("AAPL");
  });

  it("populates recentInsiderTrades correctly", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/stocks/AAPL/signals").expect(200);
    expect(res.body.recentInsiderTrades.length).toBeGreaterThan(0);
    const trade = res.body.recentInsiderTrades[0];
    expect(trade).toHaveProperty("insiderName");
    expect(trade).toHaveProperty("transactionType");
    expect(trade).toHaveProperty("totalValue");
    expect(typeof trade.totalValue).toBe("number");
  });

  it("populates recentInstitutionalChanges correctly", async () => {
    await seedInstitutional();
    const res = await request(app).get("/api/stocks/AAPL/signals").expect(200);
    expect(res.body.recentInstitutionalChanges.length).toBeGreaterThan(0);
    const change = res.body.recentInstitutionalChanges[0];
    expect(change).toHaveProperty("institutionName");
    expect(change).toHaveProperty("action");
    expect(typeof change.valueChange).toBe("number");
  });

  it("populates recentPoliticianTrades correctly", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/stocks/AAPL/signals").expect(200);
    expect(res.body.recentPoliticianTrades.length).toBeGreaterThan(0);
    const trade = res.body.recentPoliticianTrades[0];
    expect(trade).toHaveProperty("politician");
    expect(trade).toHaveProperty("party");
    expect(trade).toHaveProperty("chamber");
  });

  it("populates lockups correctly", async () => {
    await seedLockups([{
      ticker: "AAPL", companyName: "Apple Inc.", expirationDate: "2027-01-01",
      sharesUnlocking: "10000000", estimatedValue: "1800000000", ipoDate: "2026-07-01", status: "upcoming",
    }]);
    await seedInsiders();
    const res = await request(app).get("/api/stocks/AAPL/signals").expect(200);
    expect(res.body.lockups.length).toBeGreaterThan(0);
    const lockup = res.body.lockups[0];
    expect(lockup).toHaveProperty("expirationDate");
    expect(lockup).toHaveProperty("status");
    expect(typeof lockup.estimatedValue).toBe("number");
  });

  it("returns empty arrays for categories with no data for that ticker", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "SOLO", companyName: "Solo Corp",
      transactionType: "buy", shares: "100", pricePerShare: "10.00", totalValue: "1000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/stocks/SOLO/signals").expect(200);
    expect(res.body.recentInstitutionalChanges).toEqual([]);
    expect(res.body.recentPoliticianTrades).toEqual([]);
    expect(res.body.lockups).toEqual([]);
  });
});
