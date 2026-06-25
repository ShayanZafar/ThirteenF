import { Router, type IRouter } from "express";
import { db, politicianTradesTable } from "@workspace/db";
import { desc, eq, sql, and } from "drizzle-orm";

const router: IRouter = Router();

router.get("/politicians", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const offset = Number(req.query.offset) || 0;
  const ticker = req.query.ticker ? String(req.query.ticker).toUpperCase() : null;
  const party = req.query.party ? String(req.query.party) : null;
  const transactionType = req.query.transactionType ? String(req.query.transactionType) : null;

  const conditions = [];
  if (ticker) conditions.push(eq(politicianTradesTable.ticker, ticker));
  if (party) conditions.push(eq(politicianTradesTable.party, party));
  if (transactionType) conditions.push(eq(politicianTradesTable.transactionType, transactionType));

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  const [data, countRows] = await Promise.all([
    db.select().from(politicianTradesTable)
      .where(whereClause)
      .orderBy(desc(politicianTradesTable.disclosureDate))
      .limit(limit)
      .offset(offset),
    db.select({ count: sql<number>`count(*)::int` }).from(politicianTradesTable).where(whereClause),
  ]);

  res.json({
    data: data.map((t) => ({
      id: t.id,
      politician: t.politician,
      party: t.party,
      chamber: t.chamber,
      ticker: t.ticker,
      companyName: t.companyName,
      transactionType: t.transactionType,
      amountRange: t.amountRange,
      estimatedAmount: t.estimatedAmount ? Number(t.estimatedAmount) : null,
      transactionDate: t.transactionDate,
      disclosureDate: t.disclosureDate,
      daysToDisclose: t.daysToDisclose,
    })),
    total: countRows[0]?.count ?? 0,
  });
});

router.get("/politicians/leaders", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const rows = await db.select({
    politician: politicianTradesTable.politician,
    party: politicianTradesTable.party,
    chamber: politicianTradesTable.chamber,
    tradeCount: sql<number>`count(*)::int`,
    estimatedVolume: sql<number>`sum(coalesce(estimated_amount, 0))`,
    topTicker: sql<string | null>`mode() within group (order by ticker)`,
  })
    .from(politicianTradesTable)
    .groupBy(politicianTradesTable.politician, politicianTradesTable.party, politicianTradesTable.chamber)
    .orderBy(sql`count(*) desc`)
    .limit(limit);

  res.json(rows.map((r) => ({
    politician: r.politician,
    party: r.party,
    chamber: r.chamber,
    tradeCount: r.tradeCount,
    estimatedVolume: Number(r.estimatedVolume),
    topTicker: r.topTicker,
  })));
});

router.get("/politicians/most-traded", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const rows = await db.select({
    ticker: politicianTradesTable.ticker,
    companyName: politicianTradesTable.companyName,
    count: sql<number>`count(*)::int`,
    totalValue: sql<number>`sum(coalesce(estimated_amount, 0))`,
  })
    .from(politicianTradesTable)
    .groupBy(politicianTradesTable.ticker, politicianTradesTable.companyName)
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
