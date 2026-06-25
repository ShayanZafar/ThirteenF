# FlowTrack

A stock money-flow intelligence dashboard that aggregates institutional 13F filings, insider SEC Form 4 trades, congressional stock disclosures, and IPO lockup expirations — all in one place.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm --filter @workspace/stock-flow run dev` — run the frontend (port 23833)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Frontend: React + Vite, Tailwind CSS, Wouter routing, TanStack Query
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `lib/api-spec/openapi.yaml` — OpenAPI spec (source of truth for all API contracts)
- `lib/db/src/schema/` — Drizzle table definitions (institutional, insiders, politicians, lockups)
- `artifacts/api-server/src/routes/` — Express route handlers (dashboard, stocks, institutional, insiders, politicians, lockups)
- `artifacts/stock-flow/src/` — React frontend

## Architecture decisions

- Contract-first API: OpenAPI spec drives both Zod server validation and React Query client hooks via Orval codegen
- All four data categories (institutional 13F, insider Form 4, congressional disclosures, lockup expirations) stored in PostgreSQL for fast aggregated queries
- Dashboard signals computed server-side by aggregating buy/sell counts across all categories into a composite score (-100 to +100)
- Data sourced from publicly available SEC filings and congressional disclosures; seed data is representative — a real pipeline would fetch from SEC EDGAR API / Capitol Trades

## Product

- **Dashboard** — stats header, top signal movers by composite score, live cross-category activity feed
- **Institutional 13F** — institutional top movers, most-bought tickers, paginated 13F position changes
- **Insider Trades** — buy/sell ratio summary, notable large trades, paginated Form 4 list
- **Politicians** — most active lawmakers, most traded tickers, paginated disclosure list with party badges
- **Lockups** — upcoming IPO lockup expirations with countdown, full expiration calendar
- **Stock Detail** (`/stocks/:ticker`) — all signals consolidated for one ticker

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- After any OpenAPI spec change, always run `pnpm --filter @workspace/api-spec run codegen` before touching route or frontend code
- Drizzle `numeric` columns come back as strings — always wrap with `Number(...)` before returning JSON
- The `mode() within group (order by ticker)` aggregate is used for "top ticker" grouping — requires PostgreSQL 9.4+

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
