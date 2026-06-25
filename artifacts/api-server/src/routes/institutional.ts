import { Router, type IRouter } from "express";
import { db, institutionalTransactionsTable } from "@workspace/db";
import { desc, eq, sql, and } from "drizzle-orm";

const router: IRouter = Router();

router.get("/institutional", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const offset = Number(req.query.offset) || 0;
  const ticker = req.query.ticker ? String(req.query.ticker).toUpperCase() : null;
  const action = req.query.action ? String(req.query.action) : null;

  const conditions = [];
  if (ticker) conditions.push(eq(institutionalTransactionsTable.ticker, ticker));
  if (action) conditions.push(eq(institutionalTransactionsTable.action, action));

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  const [data, countRows] = await Promise.all([
    db.select().from(institutionalTransactionsTable)
      .where(whereClause)
      .orderBy(desc(institutionalTransactionsTable.filingDate))
      .limit(limit)
      .offset(offset),
    db.select({ count: sql<number>`count(*)::int` }).from(institutionalTransactionsTable).where(whereClause),
  ]);

  res.json({
    data: data.map((t) => ({
      id: t.id,
      institutionName: t.institutionName,
      ticker: t.ticker,
      companyName: t.companyName,
      action: t.action,
      sharesChange: Number(t.sharesChange),
      valueChange: Number(t.valueChange),
      totalValue: t.totalValue ? Number(t.totalValue) : null,
      percentChange: t.percentChange ? Number(t.percentChange) : null,
      reportDate: t.reportDate,
      filingDate: t.filingDate,
      quarter: t.quarter,
    })),
    total: countRows[0]?.count ?? 0,
  });
});

router.get("/institutional/top-movers", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const rows = await db.select({
    institutionName: institutionalTransactionsTable.institutionName,
    netValueChange: sql<number>`sum(case when action in ('buy','increase') then value_change else -value_change end)`,
    buysCount: sql<number>`count(case when action in ('buy','increase') then 1 end)::int`,
    sellsCount: sql<number>`count(case when action in ('sell','decrease') then 1 end)::int`,
    topBuy: sql<string | null>`max(case when action in ('buy','increase') then ticker end)`,
    topSell: sql<string | null>`max(case when action in ('sell','decrease') then ticker end)`,
  })
    .from(institutionalTransactionsTable)
    .groupBy(institutionalTransactionsTable.institutionName)
    .orderBy(sql`abs(sum(case when action in ('buy','increase') then value_change else -value_change end)) desc`)
    .limit(limit);

  res.json(rows.map((r) => ({
    institutionName: r.institutionName,
    netValueChange: Number(r.netValueChange),
    buysCount: r.buysCount,
    sellsCount: r.sellsCount,
    topBuy: r.topBuy,
    topSell: r.topSell,
  })));
});

router.get("/institutional/most-bought", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const rows = await db.select({
    ticker: institutionalTransactionsTable.ticker,
    companyName: institutionalTransactionsTable.companyName,
    count: sql<number>`count(*)::int`,
    totalValue: sql<number>`sum(value_change)`,
  })
    .from(institutionalTransactionsTable)
    .where(sql`action in ('buy','increase')`)
    .groupBy(institutionalTransactionsTable.ticker, institutionalTransactionsTable.companyName)
    .orderBy(sql`count(*) desc`)
    .limit(limit);

  res.json(rows.map((r) => ({
    ticker: r.ticker,
    companyName: r.companyName,
    count: r.count,
    totalValue: Number(r.totalValue),
  })));
});

export default router;
