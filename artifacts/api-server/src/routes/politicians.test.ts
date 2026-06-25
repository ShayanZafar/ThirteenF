import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import { clearAllTables, seedPoliticians } from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/politicians", () => {
  it("returns empty page on empty DB", async () => {
    const res = await request(app).get("/api/politicians").expect(200);
    expect(res.body).toMatchObject({ data: [], total: 0 });
  });

  it("returns seeded rows with correct shape", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians").expect(200);
    expect(res.body.total).toBe(2);
    const item = res.body.data[0];
    expect(item).toHaveProperty("id");
    expect(item).toHaveProperty("politician");
    expect(item).toHaveProperty("party");
    expect(item).toHaveProperty("chamber");
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("transactionType");
    expect(item).toHaveProperty("amountRange");
    expect(item).toHaveProperty("transactionDate");
    expect(item).toHaveProperty("disclosureDate");
    expect(item).toHaveProperty("daysToDisclose");
  });

  it("filters by ticker", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians?ticker=AAPL").expect(200);
    expect(res.body.total).toBe(1);
    expect(res.body.data[0].ticker).toBe("AAPL");
  });

  it("filters by party=democrat", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians?party=democrat").expect(200);
    expect(res.body.data.every((r: any) => r.party === "democrat")).toBe(true);
  });

  it("filters by party=republican", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians?party=republican").expect(200);
    expect(res.body.data.every((r: any) => r.party === "republican")).toBe(true);
  });

  it("filters by transactionType=buy", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians?transactionType=buy").expect(200);
    expect(res.body.data.every((r: any) => r.transactionType === "buy")).toBe(true);
  });

  it("filters by transactionType=sell", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians?transactionType=sell").expect(200);
    expect(res.body.data.every((r: any) => r.transactionType === "sell")).toBe(true);
  });

  it("paginates correctly", async () => {
    await seedPoliticians();
    const page1 = await request(app).get("/api/politicians?limit=1&offset=0").expect(200);
    const page2 = await request(app).get("/api/politicians?limit=1&offset=1").expect(200);
    expect(page1.body.data[0].id).not.toBe(page2.body.data[0].id);
    expect(page1.body.total).toBe(2);
  });
});

describe("GET /api/politicians/leaders", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/politicians/leaders").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns correct shape", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians/leaders").expect(200);
    expect(res.body.length).toBeGreaterThan(0);
    const item = res.body[0];
    expect(item).toHaveProperty("politician");
    expect(item).toHaveProperty("party");
    expect(item).toHaveProperty("chamber");
    expect(item).toHaveProperty("tradeCount");
    expect(item).toHaveProperty("estimatedVolume");
    expect(item).toHaveProperty("topTicker");
  });

  it("trade count is correct per politician", async () => {
    await seedPoliticians([
      {
        politician: "Rep. Multi", party: "democrat", chamber: "house",
        ticker: "AAPL", companyName: "Apple Inc.", transactionType: "buy",
        amountRange: "$1,001 - $15,000", estimatedAmount: "8000",
        transactionDate: "2026-05-01", disclosureDate: "2026-06-01", daysToDisclose: 31,
      },
      {
        politician: "Rep. Multi", party: "democrat", chamber: "house",
        ticker: "MSFT", companyName: "Microsoft", transactionType: "sell",
        amountRange: "$1,001 - $15,000", estimatedAmount: "5000",
        transactionDate: "2026-05-02", disclosureDate: "2026-06-02", daysToDisclose: 31,
      },
    ]);
    const res = await request(app).get("/api/politicians/leaders").expect(200);
    const multi = res.body.find((p: any) => p.politician === "Rep. Multi");
    expect(multi.tradeCount).toBe(2);
  });

  it("respects limit param", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians/leaders?limit=1").expect(200);
    expect(res.body.length).toBeLessThanOrEqual(1);
  });
});

describe("GET /api/politicians/most-traded", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/politicians/most-traded").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns correct shape", async () => {
    await seedPoliticians();
    const res = await request(app).get("/api/politicians/most-traded").expect(200);
    const item = res.body[0];
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("count");
    expect(item).toHaveProperty("totalValue");
  });

  it("ticker with more trades appears first", async () => {
    await seedPoliticians([
      {
        politician: "A", party: "democrat", chamber: "house", ticker: "HOT", companyName: "Hot Co",
        transactionType: "buy", amountRange: "$1,001 - $15,000", estimatedAmount: "5000",
        transactionDate: "2026-05-01", disclosureDate: "2026-06-01", daysToDisclose: 31,
      },
      {
        politician: "B", party: "republican", chamber: "senate", ticker: "HOT", companyName: "Hot Co",
        transactionType: "buy", amountRange: "$1,001 - $15,000", estimatedAmount: "5000",
        transactionDate: "2026-05-02", disclosureDate: "2026-06-02", daysToDisclose: 31,
      },
      {
        politician: "C", party: "democrat", chamber: "house", ticker: "COLD", companyName: "Cold Co",
        transactionType: "buy", amountRange: "$1,001 - $15,000", estimatedAmount: "5000",
        transactionDate: "2026-05-03", disclosureDate: "2026-06-03", daysToDisclose: 31,
      },
    ]);
    const res = await request(app).get("/api/politicians/most-traded").expect(200);
    expect(res.body[0].ticker).toBe("HOT");
    expect(res.body[0].count).toBe(2);
  });
});
