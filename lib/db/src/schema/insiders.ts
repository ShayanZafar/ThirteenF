import { pgTable, text, serial, timestamp, numeric, boolean, date } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const insiderTransactionsTable = pgTable("insider_transactions", {
  id: serial("id").primaryKey(),
  insiderName: text("insider_name").notNull(),
  insiderTitle: text("insider_title").notNull(),
  ticker: text("ticker").notNull(),
  companyName: text("company_name").notNull(),
  transactionType: text("transaction_type").notNull(), // buy, sell, option_exercise, gift
  shares: numeric("shares", { precision: 20, scale: 2 }).notNull(),
  pricePerShare: numeric("price_per_share", { precision: 10, scale: 4 }).notNull(),
  totalValue: numeric("total_value", { precision: 20, scale: 2 }).notNull(),
  transactionDate: date("transaction_date", { mode: "string" }).notNull(),
  filingDate: date("filing_date", { mode: "string" }).notNull(),
  isDirectOwnership: boolean("is_direct_ownership").notNull().default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertInsiderTransactionSchema = createInsertSchema(insiderTransactionsTable).omit({ id: true, createdAt: true });
export type InsertInsiderTransaction = z.infer<typeof insertInsiderTransactionSchema>;
export type InsiderTransactionRow = typeof insiderTransactionsTable.$inferSelect;
