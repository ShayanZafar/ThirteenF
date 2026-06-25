import { describe, it, expect, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import { clearAllTables, seedLockups } from "../test/setup";

beforeEach(async () => {
  await clearAllTables();
});

describe("GET /api/lockups", () => {
  it("returns empty page on empty DB", async () => {
    const res = await request(app).get("/api/lockups").expect(200);
    expect(res.body).toMatchObject({ data: [], total: 0 });
  });

  it("returns seeded rows with correct shape", async () => {
    await seedLockups();
    const res = await request(app).get("/api/lockups?status=all").expect(200);
    expect(res.body.total).toBe(2);
    const item = res.body.data[0];
    expect(item).toHaveProperty("id");
    expect(item).toHaveProperty("ticker");
    expect(item).toHaveProperty("companyName");
    expect(item).toHaveProperty("expirationDate");
    expect(item).toHaveProperty("sharesUnlocking");
    expect(item).toHaveProperty("estimatedValue");
    expect(item).toHaveProperty("ipoDate");
    expect(item).toHaveProperty("status");
  });

  it("defaults to upcoming status only", async () => {
    await seedLockups();
    const res = await request(app).get("/api/lockups").expect(200);
    expect(res.body.data.every((r: any) => r.status === "upcoming")).toBe(true);
  });

  it("filters by status=expired", async () => {
    await seedLockups();
    const res = await request(app).get("/api/lockups?status=expired").expect(200);
    expect(res.body.data.every((r: any) => r.status === "expired")).toBe(true);
  });

  it("status=all returns both upcoming and expired", async () => {
    await seedLockups();
    const res = await request(app).get("/api/lockups?status=all").expect(200);
    const statuses = new Set(res.body.data.map((r: any) => r.status));
    expect(statuses.has("upcoming")).toBe(true);
    expect(statuses.has("expired")).toBe(true);
  });

  it("paginates correctly", async () => {
    await seedLockups();
    const page1 = await request(app).get("/api/lockups?status=all&limit=1&offset=0").expect(200);
    const page2 = await request(app).get("/api/lockups?status=all&limit=1&offset=1").expect(200);
    expect(page1.body.data[0].id).not.toBe(page2.body.data[0].id);
    expect(page1.body.total).toBe(2);
  });

  it("numeric fields are numbers not strings", async () => {
    await seedLockups();
    const res = await request(app).get("/api/lockups?status=all").expect(200);
    const item = res.body.data[0];
    expect(typeof item.sharesUnlocking).toBe("number");
    expect(typeof item.estimatedValue).toBe("number");
  });

  it("daysUntilExpiry is a positive number for upcoming lockups", async () => {
    await seedLockups([{
      ticker: "NEAR", companyName: "Near Co", expirationDate: "2027-01-01",
      sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-07-01", status: "upcoming",
    }]);
    const res = await request(app).get("/api/lockups").expect(200);
    const near = res.body.data.find((r: any) => r.ticker === "NEAR");
    expect(near.daysUntilExpiry).toBeGreaterThan(0);
  });

  it("daysUntilExpiry is null for expired lockups", async () => {
    await seedLockups([{
      ticker: "OLD", companyName: "Old Co", expirationDate: "2025-01-01",
      sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2024-07-01", status: "expired",
    }]);
    const res = await request(app).get("/api/lockups?status=expired").expect(200);
    const old = res.body.data.find((r: any) => r.ticker === "OLD");
    expect(old.daysUntilExpiry).toBeNull();
  });
});

describe("GET /api/lockups/expiring-soon", () => {
  it("returns empty array on empty DB", async () => {
    const res = await request(app).get("/api/lockups/expiring-soon").expect(200);
    expect(res.body).toEqual([]);
  });

  it("returns only upcoming lockups within the default 30-day window", async () => {
    const soon = new Date();
    soon.setDate(soon.getDate() + 10);
    const soonStr = soon.toISOString().split("T")[0];

    const far = new Date();
    far.setDate(far.getDate() + 90);
    const farStr = far.toISOString().split("T")[0];

    await seedLockups([
      {
        ticker: "SOON", companyName: "Soon Co", expirationDate: soonStr,
        sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-01-01", status: "upcoming",
      },
      {
        ticker: "FAR", companyName: "Far Co", expirationDate: farStr,
        sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-01-01", status: "upcoming",
      },
    ]);

    const res = await request(app).get("/api/lockups/expiring-soon").expect(200);
    const tickers = res.body.map((r: any) => r.ticker);
    expect(tickers).toContain("SOON");
    expect(tickers).not.toContain("FAR");
  });

  it("respects days param", async () => {
    const soon = new Date();
    soon.setDate(soon.getDate() + 10);
    const soonStr = soon.toISOString().split("T")[0];

    await seedLockups([{
      ticker: "SOON", companyName: "Soon Co", expirationDate: soonStr,
      sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-01-01", status: "upcoming",
    }]);

    const res5 = await request(app).get("/api/lockups/expiring-soon?days=5").expect(200);
    expect(res5.body.find((r: any) => r.ticker === "SOON")).toBeUndefined();

    const res15 = await request(app).get("/api/lockups/expiring-soon?days=15").expect(200);
    expect(res15.body.find((r: any) => r.ticker === "SOON")).toBeDefined();
  });

  it("returns items sorted by expiration date ascending", async () => {
    const d1 = new Date(); d1.setDate(d1.getDate() + 5);
    const d2 = new Date(); d2.setDate(d2.getDate() + 15);

    await seedLockups([
      {
        ticker: "SECOND", companyName: "Second Co", expirationDate: d2.toISOString().split("T")[0],
        sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-01-01", status: "upcoming",
      },
      {
        ticker: "FIRST", companyName: "First Co", expirationDate: d1.toISOString().split("T")[0],
        sharesUnlocking: "1000000", estimatedValue: "50000000", ipoDate: "2026-01-01", status: "upcoming",
      },
    ]);

    const res = await request(app).get("/api/lockups/expiring-soon?days=30").expect(200);
    const tickers = res.body.map((r: any) => r.ticker);
    expect(tickers.indexOf("FIRST")).toBeLessThan(tickers.indexOf("SECOND"));
  });
});
