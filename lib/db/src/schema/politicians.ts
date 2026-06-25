import { pgTable, text, serial, timestamp, numeric, integer, date } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const politicianTradesTable = pgTable("politician_trades", {
  id: serial("id").primaryKey(),
  politician: text("politician").notNull(),
  party: text("party").notNull(), // democrat, republican, independent
  chamber: text("chamber").notNull(), // senate, house
  ticker: text("ticker").notNull(),
  companyName: text("company_name").notNull(),
  transactionType: text("transaction_type").notNull(), // buy, sell
  amountRange: text("amount_range").notNull(), // e.g. "$15,001 - $50,000"
  estimatedAmount: numeric("estimated_amount", { precision: 20, scale: 2 }),
  transactionDate: date("transaction_date", { mode: "string" }).notNull(),
  disclosureDate: date("disclosure_date", { mode: "string" }).notNull(),
  daysToDisclose: integer("days_to_disclose").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertPoliticianTradeSchema = createInsertSchema(politicianTradesTable).omit({ id: true, createdAt: true });
export type InsertPoliticianTrade = z.infer<typeof insertPoliticianTradeSchema>;
export type PoliticianTradeRow = typeof politicianTradesTable.$inferSelect;
