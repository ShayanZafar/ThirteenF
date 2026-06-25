import { pgTable, text, serial, timestamp, numeric, date } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const lockupEventsTable = pgTable("lockup_events", {
  id: serial("id").primaryKey(),
  ticker: text("ticker").notNull(),
  companyName: text("company_name").notNull(),
  expirationDate: date("expiration_date", { mode: "string" }).notNull(),
  sharesUnlocking: numeric("shares_unlocking", { precision: 20, scale: 2 }).notNull(),
  estimatedValue: numeric("estimated_value", { precision: 20, scale: 2 }).notNull(),
  ipoDate: date("ipo_date", { mode: "string" }).notNull(),
  status: text("status").notNull(), // upcoming, expired
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertLockupEventSchema = createInsertSchema(lockupEventsTable).omit({ id: true, createdAt: true });
export type InsertLockupEvent = z.infer<typeof insertLockupEventSchema>;
export type LockupEventRow = typeof lockupEventsTable.$inferSelect;
