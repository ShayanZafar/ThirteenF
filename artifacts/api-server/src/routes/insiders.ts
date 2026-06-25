import { Router, type IRouter } from "express";
import { db, insiderTransactionsTable } from "@workspace/db";
import { desc, eq, sql, and } from "drizzle-orm";

const router: IRouter = Router();

router.get("/insiders", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const offset = Number(req.query.offset) || 0;
  const ticker = req.query.ticker ? String(req.query.ticker).toUpperCase() : null;
  const transactionType = req.query.transactionType ? String(req.query.transactionType) : null;

  const conditions = [];
  if (ticker) conditions.push(eq(insiderTransactionsTable.ticker, ticker));
  if (transactionType) conditions.push(eq(insiderTransactionsTable.transactionType, transactionType));

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  const [data, countRows] = await Promise.all([
    db.select().from(insiderTransactionsTable)
      .where(whereClause)
      .orderBy(desc(insiderTransactionsTable.filingDate))
      .limit(limit)
      .offset(offset),
    db.select({ count: sql<number>`count(*)::int` }).from(insiderTransactionsTable).where(whereClause),
  ]);

  res.json({
    data: data.map((t) => ({
      id: t.id,
      insiderName: t.insiderName,
      insiderTitle: t.insiderTitle,
      ticker: t.ticker,
      companyName: t.companyName,
      transactionType: t.transactionType,
      shares: Number(t.shares),
      pricePerShare: Number(t.pricePerShare),
      totalValue: Number(t.totalValue),
      transactionDate: t.transactionDate,
      filingDate: t.filingDate,
      isDirectOwnership: t.isDirectOwnership,
    })),
    total: countRows[0]?.count ?? 0,
  });
});

router.get("/insiders/summary", async (_req, res): Promise<void> => {
  const [summary, last30] = await Promise.all([
    db.select({
      transactionType: insiderTransactionsTable.transactionType,
      count: sql<number>`count(*)::int`,
      volume: sql<number>`sum(total_value)`,
    })
      .from(insiderTransactionsTable)
      .groupBy(insiderTransactionsTable.transactionType),
    db.select({
      transactionType: insiderTransactionsTable.transactionType,
      count: sql<number>`count(*)::int`,
    })
      .from(insiderTransactionsTable)
      .where(sql`filing_date >= current_date - interval '30 days'`)
      .groupBy(insiderTransactionsTable.transactionType),
  ]);

  const getBuysSells = (rows: { transactionType: string; count: number; volume?: number }[]) => {
    const buys = rows.find((r) => r.transactionType === "buy");
    const sells = rows.find((r) => r.transactionType === "sell");
    return { buys, sells };
  };

  const { buys, sells } = getBuysSells(summary as any);
  const { buys: l30Buys, sells: l30Sells } = getBuysSells(last30 as any);

  const totalBuys = buys?.count ?? 0;
  const totalSells = sells?.count ?? 0;
  const buyVolume = Number(buys?.volume ?? 0);
  const sellVolume = Number(sells?.volume ?? 0);
  const total = totalBuys + totalSells || 1;

  res.json({
    totalBuys,
    totalSells,
    buyVolume,
    sellVolume,
    buyRatio: totalBuys / total,
    last30Days: {
      buys: l30Buys?.count ?? 0,
      sells: l30Sells?.count ?? 0,
    },
  });
});

router.get("/insiders/notable", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const rows = await db.select().from(insiderTransactionsTable)
    .orderBy(desc(sql`total_value`))
    .limit(limit);

  res.json(rows.map((t) => ({
    id: t.id,
    insiderName: t.insiderName,
    insiderTitle: t.insiderTitle,
    ticker: t.ticker,
    companyName: t.companyName,
    transactionType: t.transactionType,
    shares: Number(t.shares),
    pricePerShare: Number(t.pricePerShare),
    totalValue: Number(t.totalValue),
    transactionDate: t.transactionDate,
    filingDate: t.filingDate,
    isDirectOwnership: t.isDirectOwnership,
  })));
});

export default router;
