import { Router, type IRouter } from "express";
import { db, lockupEventsTable } from "@workspace/db";
import { desc, asc, eq, sql, and, gte, lte } from "drizzle-orm";

const router: IRouter = Router();

router.get("/lockups", async (req, res): Promise<void> => {
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const offset = Number(req.query.offset) || 0;
  const status = req.query.status ? String(req.query.status) : "upcoming";

  const conditions = [];
  if (status !== "all") {
    conditions.push(eq(lockupEventsTable.status, status));
  }

  const whereClause = conditions.length > 0 ? and(...conditions) : undefined;

  const [data, countRows] = await Promise.all([
    db.select().from(lockupEventsTable)
      .where(whereClause)
      .orderBy(asc(lockupEventsTable.expirationDate))
      .limit(limit)
      .offset(offset),
    db.select({ count: sql<number>`count(*)::int` }).from(lockupEventsTable).where(whereClause),
  ]);

  const now = new Date();

  res.json({
    data: data.map((t) => {
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
    total: countRows[0]?.count ?? 0,
  });
});

router.get("/lockups/expiring-soon", async (req, res): Promise<void> => {
  const days = Math.min(Number(req.query.days) || 30, 90);
  const now = new Date();
  const future = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
  const todayStr = now.toISOString().split("T")[0];
  const futureStr = future.toISOString().split("T")[0];

  const rows = await db.select().from(lockupEventsTable)
    .where(and(
      eq(lockupEventsTable.status, "upcoming"),
      sql`expiration_date >= ${todayStr}`,
      sql`expiration_date <= ${futureStr}`,
    ))
    .orderBy(asc(lockupEventsTable.expirationDate));

  res.json(rows.map((t) => {
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
  }));
});

export default router;
