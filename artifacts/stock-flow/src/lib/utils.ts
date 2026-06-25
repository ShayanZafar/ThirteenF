import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatCurrency(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  if (val === 0) return "$0";
  
  const absVal = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  
  if (absVal >= 1e9) {
    return `${sign}${(absVal / 1e9).toFixed(2)}B`;
  }
  if (absVal >= 1e6) {
    return `${sign}${(absVal / 1e6).toFixed(2)}M`;
  }
  if (absVal >= 1e3) {
    return `${sign}${(absVal / 1e3).toFixed(2)}K`;
  }
  return `${sign}$${absVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatShares(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  if (val === 0) return "0";
  
  const absVal = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  
  if (absVal >= 1e9) {
    return `${sign}${(absVal / 1e9).toFixed(2)}B`;
  }
  if (absVal >= 1e6) {
    return `${sign}${(absVal / 1e6).toFixed(2)}M`;
  }
  if (absVal >= 1e3) {
    return `${sign}${(absVal / 1e3).toFixed(2)}K`;
  }
  return `${sign}${absVal.toLocaleString()}`;
}

export function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return "—";
  try {
    const d = new Date(dateString);
    return d.toISOString().split("T")[0]; // YYYY-MM-DD
  } catch (e) {
    return dateString;
  }
}

export function formatPercentage(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  const sign = val > 0 ? "+" : "";
  return `${sign}${(val).toFixed(2)}%`;
}
