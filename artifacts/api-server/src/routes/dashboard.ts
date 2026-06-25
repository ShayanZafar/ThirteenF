import { Router, type IRouter } from "express";
import { db, institutionalTransactionsTable, insiderTransactionsTable, politicianTradesTable, lockupEventsTable } from "@workspace/db";
import { desc, sql, gte, and } from "drizzle-orm";
import { computeSignalScore, computeMoneyFlow, type SignalEntry, type MoneyFlowEntry } from "../lib/signals";

const router: IRouter = Router();

router.get("/dashboard/activity", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 50, 100);

  const [institutional, insiders, politicians, lockups] = await Promise.all([
    db.select().from(institutionalTransactionsTable).orderBy(desc(institutionalTransactionsTable.filingDate)).limit(15),
    db.select().from(insiderTransactionsTable).orderBy(desc(insiderTransactionsTable.filingDate)).limit(15),
    db.select().from(politicianTradesTable).orderBy(desc(politicianTradesTable.disclosureDate)).limit(15),
    db.select().from(lockupEventsTable).orderBy(desc(lockupEventsTable.expirationDate)).limit(10),
  ]);

  const activities: object[] = [
    ...institutional.map((t) => ({
      id: `inst-${t.id}`,
      category: "institutional",
      ticker: t.ticker,
      companyName: t.companyName,
      title: `${t.institutionName} ${t.action === "buy" || t.action === "increase" ? "bought" : "sold"} ${t.ticker}`,
      description: `${t.action} — $${(Math.abs(Number(t.valueChange)) / 1e6).toFixed(1)}M value change in ${t.quarter}`,
      amount: Math.abs(Number(t.valueChange)),
      direction: t.action === "buy" || t.action === "increase" ? "buy" : "sell",
      date: t.filingDate,
      source: "SEC 13F",
    })),
    ...insiders.map((t) => ({
      id: `ins-${t.id}`,
      category: "insider",
      ticker: t.ticker,
      companyName: t.companyName,
      title: `${t.insiderName} (${t.insiderTitle}) ${t.transactionType === "buy" ? "bought" : "sold"} ${t.ticker}`,
      description: `${Number(t.shares).toLocaleString()} shares @ $${Number(t.pricePerShare).toFixed(2)}`,
      amount: Number(t.totalValue),
      direction: t.transactionType === "buy" ? "buy" : t.transactionType === "sell" ? "sell" : "neutral",
      date: t.filingDate,
      source: "SEC Form 4",
    })),
    ...politicians.map((t) => ({
      id: `pol-${t.id}`,
      category: "politician",
      ticker: t.ticker,
      companyName: t.companyName,
      title: `${t.politician} (${t.chamber === "senate" ? "Sen." : "Rep."}) ${t.transactionType === "buy" ? "bought" : "sold"} ${t.ticker}`,
      description: `${t.amountRange} — disclosed ${t.daysToDisclose} days after trade`,
      amount: t.estimatedAmount ? Number(t.estimatedAmount) : null,
      direction: t.transactionType,
      date: t.disclosureDate,
      source: "Congressional Disclosure",
    })),
    ...lockups.map((t) => ({
      id: `lock-${t.id}`,
      category: "lockup",
      ticker: t.ticker,
      companyName: t.companyName,
      title: `${t.ticker} lockup ${t.status === "upcoming" ? "expiring" : "expired"}`,
      description: `${(Number(t.sharesUnlocking) / 1e6).toFixed(1)}M shares unlocking — est. $${(Number(t.estimatedValue) / 1e6).toFixed(0)}M`,
      amount: Number(t.estimatedValue),
      direction: "neutral",
      date: t.expirationDate,
      source: "IPO Lockup",
    })),
  ];

  activities.sort((a: any, b: any) => new Date(b.date).getTime() - new Date(a.date).getTime());

  res.json(activities.slice(0, limit));
});

router.get("/dashboard/signals", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 20, 50);

  const [instRows, insRows, polRows] = await Promise.all([
    db.select({
      ticker: institutionalTransactionsTable.ticker,
      companyName: institutionalTransactionsTable.companyName,
      action: institutionalTransactionsTable.action,
    }).from(institutionalTransactionsTable),
    db.select({
      ticker: insiderTransactionsTable.ticker,
      companyName: insiderTransactionsTable.companyName,
      transactionType: insiderTransactionsTable.transactionType,
    }).from(insiderTransactionsTable),
    db.select({
      ticker: politicianTradesTable.ticker,
      companyName: politicianTradesTable.companyName,
      transactionType: politicianTradesTable.transactionType,
    }).from(politicianTradesTable),
  ]);

  const lockupRows = await db.select().from(lockupEventsTable).where(sql`status = 'upcoming'`);

  const tickerMap: Record<string, {
    ticker: string; companyName: string;
    instBuys: number; instSells: number;
    insBuys: number; insSells: number;
    polBuys: number; polSells: number;
    lockupExpiring: boolean; lockupDate: string | null;
  }> = {};

  const getOrCreate = (ticker: string, companyName: string) => {
    if (!tickerMap[ticker]) {
      tickerMap[ticker] = { ticker, companyName, instBuys: 0, instSells: 0, insBuys: 0, insSells: 0, polBuys: 0, polSells: 0, lockupExpiring: false, lockupDate: null };
    }
    return tickerMap[ticker];
  };

  instRows.forEach((r) => {
    const entry = getOrCreate(r.ticker, r.companyName);
    if (r.action === "buy" || r.action === "increase") entry.instBuys++;
    else entry.instSells++;
  });

  insRows.forEach((r) => {
    const entry = getOrCreate(r.ticker, r.companyName);
    if (r.transactionType === "buy") entry.insBuys++;
    else if (r.transactionType === "sell") entry.insSells++;
  });

  polRows.forEach((r) => {
    const entry = getOrCreate(r.ticker, r.companyName);
    if (r.transactionType === "buy") entry.polBuys++;
    else entry.polSells++;
  });

  lockupRows.forEach((r) => {
    const entry = getOrCreate(r.ticker, r.companyName);
    entry.lockupExpiring = true;
    entry.lockupDate = r.expirationDate;
  });

  const signals = Object.values(tickerMap).map((entry) => ({
    ticker: entry.ticker,
    companyName: entry.companyName,
    signalScore: computeSignalScore(entry),
    institutionalBuys: entry.instBuys,
    institutionalSells: entry.instSells,
    insiderBuys: entry.insBuys,
    insiderSells: entry.insSells,
    politicianBuys: entry.polBuys,
    politicianSells: entry.polSells,
    lockupExpiring: entry.lockupExpiring,
    lockupDate: entry.lockupDate,
  }));

  signals.sort((a, b) => Math.abs(b.signalScore) - Math.abs(a.signalScore));
  res.json(signals.slice(0, limit));
});

router.get("/dashboard/stats", async (_req, res): Promise<void> => {
  const [insiderCount, instCount, polCount, lockupCount] = await Promise.all([
    db.select({ count: sql<number>`count(*)::int` }).from(insiderTransactionsTable),
    db.select({ count: sql<number>`count(*)::int` }).from(institutionalTransactionsTable),
    db.select({ count: sql<number>`count(*)::int` }).from(politicianTradesTable),
    db.select({ count: sql<number>`count(*)::int` }).from(lockupEventsTable).where(sql`extract(month from expiration_date::date) = extract(month from current_date) and extract(year from expiration_date::date) = extract(year from current_date)`),
  ]);

  const [buys, sells] = await Promise.all([
    db.select({ count: sql<number>`count(*)::int` }).from(insiderTransactionsTable).where(sql`transaction_type = 'buy'`),
    db.select({ count: sql<number>`count(*)::int` }).from(insiderTransactionsTable).where(sql`transaction_type = 'sell'`),
  ]);

  const buyCount = buys[0]?.count ?? 0;
  const sellCount = sells[0]?.count ?? 0;
  const total = buyCount + sellCount || 1;

  res.json({
    totalInsiderTrades: insiderCount[0]?.count ?? 0,
    totalInstitutionalChanges: instCount[0]?.count ?? 0,
    totalPoliticianTrades: polCount[0]?.count ?? 0,
    lockupsThisMonth: lockupCount[0]?.count ?? 0,
    netBuyPressure: buyCount / total,
  });
});

router.get("/dashboard/money-flow", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 10, 50);

  const [instBuys, instSells, insBuys, insSells] = await Promise.all([
    db.select({
      ticker: institutionalTransactionsTable.ticker,
      companyName: institutionalTransactionsTable.companyName,
      total: sql<number>`sum(value_change)`,
    }).from(institutionalTransactionsTable)
      .where(sql`action in ('buy','increase')`)
      .groupBy(institutionalTransactionsTable.ticker, institutionalTransactionsTable.companyName),
    db.select({
      ticker: institutionalTransactionsTable.ticker,
      companyName: institutionalTransactionsTable.companyName,
      total: sql<number>`sum(abs(value_change))`,
    }).from(institutionalTransactionsTable)
      .where(sql`action in ('sell','decrease')`)
      .groupBy(institutionalTransactionsTable.ticker, institutionalTransactionsTable.companyName),
    db.select({
      ticker: insiderTransactionsTable.ticker,
      companyName: insiderTransactionsTable.companyName,
      total: sql<number>`sum(total_value)`,
    }).from(insiderTransactionsTable)
      .where(sql`transaction_type = 'buy'`)
      .groupBy(insiderTransactionsTable.ticker, insiderTransactionsTable.companyName),
    db.select({
      ticker: insiderTransactionsTable.ticker,
      companyName: insiderTransactionsTable.companyName,
      total: sql<number>`sum(total_value)`,
    }).from(insiderTransactionsTable)
      .where(sql`transaction_type = 'sell'`)
      .groupBy(insiderTransactionsTable.ticker, insiderTransactionsTable.companyName),
  ]);

  const tickerMap: Record<string, {
    ticker: string; companyName: string;
    institutionalInflow: number; institutionalOutflow: number;
    insiderInflow: number; insiderOutflow: number;
  }> = {};

  const getOrCreate = (ticker: string, companyName: string) => {
    if (!tickerMap[ticker]) {
      tickerMap[ticker] = { ticker, companyName, institutionalInflow: 0, institutionalOutflow: 0, insiderInflow: 0, insiderOutflow: 0 };
    }
    return tickerMap[ticker];
  };

  instBuys.forEach((r) => { getOrCreate(r.ticker, r.companyName).institutionalInflow = Number(r.total); });
  instSells.forEach((r) => { getOrCreate(r.ticker, r.companyName).institutionalOutflow = Number(r.total); });
  insBuys.forEach((r) => { getOrCreate(r.ticker, r.companyName).insiderInflow = Number(r.total); });
  insSells.forEach((r) => { getOrCreate(r.ticker, r.companyName).insiderOutflow = Number(r.total); });

  const result = Object.values(tickerMap).map((entry) => ({
    ticker: entry.ticker,
    companyName: entry.companyName,
    institutionalInflow: entry.institutionalInflow,
    institutionalOutflow: entry.institutionalOutflow,
    insiderInflow: entry.insiderInflow,
    insiderOutflow: entry.insiderOutflow,
    totalInflow: entry.institutionalInflow + entry.insiderInflow,
    totalOutflow: entry.institutionalOutflow + entry.insiderOutflow,
    netFlow: (entry.institutionalInflow + entry.insiderInflow) - (entry.institutionalOutflow + entry.insiderOutflow),
  }));

  result.sort((a, b) => Math.abs(b.netFlow) - Math.abs(a.netFlow));
  res.json(result.slice(0, limit));
});

export default router;
