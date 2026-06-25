import { pgTable, text, serial, timestamp, numeric, integer, date } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const institutionalTransactionsTable = pgTable("institutional_transactions", {
  id: serial("id").primaryKey(),
  institutionName: text("institution_name").notNull(),
  ticker: text("ticker").notNull(),
  companyName: text("company_name").notNull(),
  action: text("action").notNull(), // buy, sell, increase, decrease
  sharesChange: numeric("shares_change", { precision: 20, scale: 2 }).notNull(),
  valueChange: numeric("value_change", { precision: 20, scale: 2 }).notNull(),
  totalValue: numeric("total_value", { precision: 20, scale: 2 }),
  percentChange: numeric("percent_change", { precision: 10, scale: 4 }),
  reportDate: date("report_date", { mode: "string" }).notNull(),
  filingDate: date("filing_date", { mode: "string" }).notNull(),
  quarter: text("quarter").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertInstitutionalTransactionSchema = createInsertSchema(institutionalTransactionsTable).omit({ id: true, createdAt: true });
export type InsertInstitutionalTransaction = z.infer<typeof insertInstitutionalTransactionSchema>;
export type InstitutionalTransaction = typeof institutionalTransactionsTable.$inferSelect;
