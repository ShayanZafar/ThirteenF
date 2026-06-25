import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import { clearAllTables, seedInsiders } from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/insiders", () => {
  it("returns empty page on empty DB", async () => {
    const res = await request(app).get("/api/insiders").expect(200);
    expect(res.body).toMatchObject({ data: [], total: 0 });
  });

  it("returns seeded rows with correct shape", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders").expect(200);
    expect(res.body.total).toBe(2);
    const item = res.body.data[0];
    expect(item).toHaveProperty("id");
    expect(item).toHaveProperty("insiderName");
    expect(item).toHaveProperty("insiderTitle");
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("transactionType");
    expect(item).toHaveProperty("shares");
    expect(item).toHaveProperty("pricePerShare");
    expect(item).toHaveProperty("totalValue");
    expect(item).toHaveProperty("transactionDate");
    expect(item).toHaveProperty("filingDate");
    expect(item).toHaveProperty("isDirectOwnership");
  });

  it("filters by ticker", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders?ticker=AAPL").expect(200);
    expect(res.body.total).toBe(1);
    expect(res.body.data[0].ticker).toBe("AAPL");
  });

  it("filters by transactionType=buy", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders?transactionType=buy").expect(200);
    expect(res.body.data.every((r: any) => r.transactionType === "buy")).toBe(true);
  });

  it("filters by transactionType=sell", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders?transactionType=sell").expect(200);
    expect(res.body.data.every((r: any) => r.transactionType === "sell")).toBe(true);
  });

  it("paginates correctly", async () => {
    await seedInsiders();
    const page1 = await request(app).get("/api/insiders?limit=1&offset=0").expect(200);
    const page2 = await request(app).get("/api/insiders?limit=1&offset=1").expect(200);
    expect(page1.body.data[0].id).not.toBe(page2.body.data[0].id);
    expect(page1.body.total).toBe(2);
  });

  it("numeric fields are numbers not strings", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders").expect(200);
    const item = res.body.data[0];
    expect(typeof item.shares).toBe("number");
    expect(typeof item.pricePerShare).toBe("number");
    expect(typeof item.totalValue).toBe("number");
  });
});

describe("GET /api/insiders/summary", () => {
  it("returns zero values on empty DB", async () => {
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body).toMatchObject({
      totalBuys: 0,
      totalSells: 0,
      buyVolume: 0,
      sellVolume: 0,
      buyRatio: 0,
      last30Days: { buys: 0, sells: 0 },
    });
  });

  it("counts buys and sells separately", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body.totalBuys).toBe(1);
    expect(res.body.totalSells).toBe(1);
  });

  it("buyRatio is 1 when all trades are buys", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "X", companyName: "X Corp",
      transactionType: "buy", shares: "100", pricePerShare: "10.00", totalValue: "1000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body.buyRatio).toBe(1);
  });

  it("buyRatio is 0 when all trades are sells", async () => {
    await seedInsiders([{
      insiderName: "B", insiderTitle: "CFO", ticker: "Y", companyName: "Y Corp",
      transactionType: "sell", shares: "100", pricePerShare: "10.00", totalValue: "1000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body.buyRatio).toBe(0);
  });

  it("buyVolume reflects sum of buy totalValues", async () => {
    await seedInsiders([{
      insiderName: "A", insiderTitle: "CEO", ticker: "X", companyName: "X Corp",
      transactionType: "buy", shares: "100", pricePerShare: "50.00", totalValue: "5000",
      transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
    }]);
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body.buyVolume).toBe(5000);
  });

  it("has last30Days property with buys and sells keys", async () => {
    const res = await request(app).get("/api/insiders/summary").expect(200);
    expect(res.body.last30Days).toHaveProperty("buys");
    expect(res.body.last30Days).toHaveProperty("sells");
  });
});

describe("GET /api/insiders/notable", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/insiders/notable").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns rows sorted by total value descending", async () => {
    await seedInsiders([
      {
        insiderName: "A", insiderTitle: "CEO", ticker: "LOW", companyName: "Low Co",
        transactionType: "sell", shares: "100", pricePerShare: "10.00", totalValue: "1000",
        transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
      },
      {
        insiderName: "B", insiderTitle: "CFO", ticker: "HIGH", companyName: "High Co",
        transactionType: "sell", shares: "10000", pricePerShare: "500.00", totalValue: "5000000",
        transactionDate: "2026-06-01", filingDate: "2026-06-02", isDirectOwnership: true,
      },
    ]);
    const res = await request(app).get("/api/insiders/notable").expect(200);
    expect(res.body[0].ticker).toBe("HIGH");
  });

  it("respects limit param", async () => {
    await seedInsiders();
    const res = await request(app).get("/api/insiders/notable?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });
});
