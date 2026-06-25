import { Router, type IRouter } from "express";
import { db, institutionalTransactionsTable, insiderTransactionsTable, politicianTradesTable, lockupEventsTable } from "@workspace/db";
import { eq, or, ilike, desc } from "drizzle-orm";

const router: IRouter = Router();

router.get("/stocks/search", async (req, res): Promise<void> => {
  const q = String(req.query.q || "").trim().toUpperCase();
  if (!q) {
    res.json([]);
    return;
  }

  const [instRows, insRows, polRows] = await Promise.all([
    db.selectDistinct({ ticker: institutionalTransactionsTable.ticker, companyName: institutionalTransactionsTable.companyName })
      .from(institutionalTransactionsTable)
      .where(or(ilike(institutionalTransactionsTable.ticker, `%${q}%`), ilike(institutionalTransactionsTable.companyName, `%${q}%`)))
      .limit(10),
    db.selectDistinct({ ticker: insiderTransactionsTable.ticker, companyName: insiderTransactionsTable.companyName })
      .from(insiderTransactionsTable)
      .where(or(ilike(insiderTransactionsTable.ticker, `%${q}%`), ilike(insiderTransactionsTable.companyName, `%${q}%`)))
      .limit(10),
    db.selectDistinct({ ticker: politicianTradesTable.ticker, companyName: politicianTradesTable.companyName })
      .from(politicianTradesTable)
      .where(or(ilike(politicianTradesTable.ticker, `%${q}%`), ilike(politicianTradesTable.companyName, `%${q}%`)))
      .limit(10),
  ]);

  const seen = new Set<string>();
  const results: { ticker: string; companyName: string; sector: null }[] = [];

  [...instRows, ...insRows, ...polRows].forEach((r) => {
    if (!seen.has(r.ticker)) {
      seen.add(r.ticker);
      results.push({ ticker: r.ticker, companyName: r.companyName, sector: null });
    }
  });

  res.json(results.slice(0, 15));
});

router.get("/stocks/:ticker/signals", async (req, res): Promise<void> => {
  const raw = Array.isArray(req.params.ticker) ? req.params.ticker[0] : req.params.ticker;
  const ticker = raw.toUpperCase();

  const [insiders, institutional, politicians, lockups] = await Promise.all([
    db.select().from(insiderTransactionsTable).where(eq(insiderTransactionsTable.ticker, ticker)).orderBy(desc(insiderTransactionsTable.transactionDate)).limit(20),
    db.select().from(institutionalTransactionsTable).where(eq(institutionalTransactionsTable.ticker, ticker)).orderBy(desc(institutionalTransactionsTable.filingDate)).limit(20),
    db.select().from(politicianTradesTable).where(eq(politicianTradesTable.ticker, ticker)).orderBy(desc(politicianTradesTable.transactionDate)).limit(20),
    db.select().from(lockupEventsTable).where(eq(lockupEventsTable.ticker, ticker)).orderBy(desc(lockupEventsTable.expirationDate)),
  ]);

  if (!insiders.length && !institutional.length && !politicians.length && !lockups.length) {
    res.status(404).json({ error: "Ticker not found" });
    return;
  }

  const companyName = insiders[0]?.companyName || institutional[0]?.companyName || politicians[0]?.companyName || lockups[0]?.companyName || ticker;

  res.json({
    ticker,
    companyName,
    recentInsiderTrades: insiders.map((t) => ({
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
    recentInstitutionalChanges: institutional.map((t) => ({
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
    recentPoliticianTrades: politicians.map((t) => ({
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
    lockups: lockups.map((t) => {
      const now = new Date();
      const exp = new Date(t.expirationDate);
      const daysUntil = Math.ceil((exp.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
      return {
        id: t.id,
        ticker: t.ticker,
        companyName: t.companyName,
        expirationDate: t.expirationDate,
        sharesUnlocking: Number(t.sharesUnlocking),
        estimatedValue: Number(t.estimatedValue),
        ipoDate: t.ipoDate,
        status: t.status,
        daysUntilExpiry: daysUntil > 0 ? daysUntil : null,
      };
    }),
  });
});

export default router;
