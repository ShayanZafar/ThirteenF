import { db } from "@workspace/db";
import {
  institutionalTransactionsTable,
  insiderTransactionsTable,
  politicianTradesTable,
  lockupEventsTable,
} from "@workspace/db";
import { sql } from "drizzle-orm";
import { afterAll, beforeAll } from "vitest";

export async function clearAllTables() {
  await db.execute(sql`TRUNCATE institutional_transactions, insider_transactions, politician_trades, lockup_events RESTART IDENTITY CASCADE`);
}

export async function seedInstitutional(overrides: Partial<typeof institutionalTransactionsTable.$inferInsert>[] = []) {
  const defaults = [
    {
      institutionName: "Test Fund A",
      ticker: "AAPL",
      companyName: "Apple Inc.",
      action: "buy" as const,
      sharesChange: "1000000",
      valueChange: "150000000",
      totalValue: "500000000",
      percentChange: "10.0",
      reportDate: "2026-05-15",
      filingDate: "2026-05-15",
      quarter: "Q1 2026",
    },
    {
      institutionName: "Test Fund B",
      ticker: "TSLA",
      companyName: "Tesla Inc.",
      action: "sell" as const,
      sharesChange: "-500000",
      valueChange: "-90000000",
      totalValue: "200000000",
      percentChange: "-30.0",
      reportDate: "2026-05-15",
      filingDate: "2026-05-15",
      quarter: "Q1 2026",
    },
  ];
  const rows = overrides.length > 0 ? overrides : defaults;
  return db.insert(institutionalTransactionsTable).values(rows as any).returning();
}

export async function seedInsiders(overrides: Partial<typeof insiderTransactionsTable.$inferInsert>[] = []) {
  const defaults = [
    {
      insiderName: "Jane CEO",
      insiderTitle: "CEO",
      ticker: "AAPL",
      companyName: "Apple Inc.",
      transactionType: "buy" as const,
      shares: "10000",
      pricePerShare: "180.00",
      totalValue: "1800000",
      transactionDate: "2026-06-01",
      filingDate: "2026-06-03",
      isDirectOwnership: true,
    },
    {
      insiderName: "John CFO",
      insiderTitle: "CFO",
      ticker: "TSLA",
      companyName: "Tesla Inc.",
      transactionType: "sell" as const,
      shares: "50000",
      pricePerShare: "185.00",
      totalValue: "9250000",
      transactionDate: "2026-06-05",
      filingDate: "2026-06-07",
      isDirectOwnership: true,
    },
  ];
  const rows = overrides.length > 0 ? overrides : defaults;
  return db.insert(insiderTransactionsTable).values(rows as any).returning();
}

export async function seedPoliticians(overrides: Partial<typeof politicianTradesTable.$inferInsert>[] = []) {
  const defaults = [
    {
      politician: "Rep. Smith",
      party: "democrat" as const,
      chamber: "house" as const,
      ticker: "AAPL",
      companyName: "Apple Inc.",
      transactionType: "buy" as const,
      amountRange: "$15,001 - $50,000",
      estimatedAmount: "32000",
      transactionDate: "2026-05-10",
      disclosureDate: "2026-06-10",
      daysToDisclose: 31,
    },
    {
      politician: "Sen. Jones",
      party: "republican" as const,
      chamber: "senate" as const,
      ticker: "TSLA",
      companyName: "Tesla Inc.",
      transactionType: "sell" as const,
      amountRange: "$50,001 - $100,000",
      estimatedAmount: "75000",
      transactionDate: "2026-05-12",
      disclosureDate: "2026-06-12",
      daysToDisclose: 31,
    },
  ];
  const rows = overrides.length > 0 ? overrides : defaults;
  return db.insert(politicianTradesTable).values(rows as any).returning();
}

export async function seedLockups(overrides: Partial<typeof lockupEventsTable.$inferInsert>[] = []) {
  const defaults = [
    {
      ticker: "RDDT",
      companyName: "Reddit Inc.",
      expirationDate: "2026-08-01",
      sharesUnlocking: "50000000",
      estimatedValue: "3000000000",
      ipoDate: "2026-03-21",
      status: "upcoming" as const,
    },
    {
      ticker: "GTLB",
      companyName: "GitLab Inc.",
      expirationDate: "2026-04-01",
      sharesUnlocking: "100000000",
      estimatedValue: "6000000000",
      ipoDate: "2025-12-14",
      status: "expired" as const,
    },
  ];
  const rows = overrides.length > 0 ? overrides : defaults;
  return db.insert(lockupEventsTable).values(rows as any).returning();
}

beforeAll(async () => {
  await clearAllTables();
});

afterAll(async () => {
  await clearAllTables();
});
