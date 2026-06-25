export interface SignalEntry {
  ticker: string;
  companyName: string;
  instBuys: number;
  instSells: number;
  insBuys: number;
  insSells: number;
  polBuys: number;
  polSells: number;
  lockupExpiring: boolean;
  lockupDate: string | null;
}

export function computeSignalScore(entry: Pick<SignalEntry, "instBuys" | "instSells" | "insBuys" | "insSells" | "polBuys" | "polSells" | "lockupExpiring">): number {
  const buySignal = entry.instBuys * 2 + entry.insBuys * 3 + entry.polBuys * 1.5;
  const sellSignal = entry.instSells * 2 + entry.insSells * 3 + entry.polSells * 1.5 + (entry.lockupExpiring ? 10 : 0);
  const total = buySignal + sellSignal || 1;
  const score = Math.round(((buySignal - sellSignal) / total) * 100);
  return Math.max(-100, Math.min(100, score));
}

export interface MoneyFlowEntry {
  ticker: string;
  companyName: string;
  institutionalInflow: number;
  institutionalOutflow: number;
  insiderInflow: number;
  insiderOutflow: number;
}

export function computeMoneyFlow(entry: MoneyFlowEntry) {
  const totalInflow = entry.institutionalInflow + entry.insiderInflow;
  const totalOutflow = entry.institutionalOutflow + entry.insiderOutflow;
  return {
    ...entry,
    totalInflow,
    totalOutflow,
    netFlow: totalInflow - totalOutflow,
  };
}
