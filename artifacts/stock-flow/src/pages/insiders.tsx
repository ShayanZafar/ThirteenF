import { useGetInsiderSummary, useGetNotableInsiders, useListInsiders, getGetInsiderSummaryQueryKey, getGetNotableInsidersQueryKey, getListInsidersQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatShares, cn } from "@/lib/utils";
import { Link } from "wouter";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { ChevronLeft, ChevronRight, UserCircle } from "lucide-react";

export default function Insiders() {
  const [page, setPage] = useState(0);
  const limit = 20;
  
  const { data: summary, isLoading: summaryLoading } = useGetInsiderSummary({ query: { queryKey: getGetInsiderSummaryQueryKey() } });
  const { data: notable, isLoading: notableLoading } = useGetNotableInsiders({ limit: 6 }, { query: { queryKey: getGetNotableInsidersQueryKey({ limit: 6 }) } });
  const { data: listData, isLoading: listLoading } = useListInsiders(
    { limit, offset: page * limit }, 
    { query: { queryKey: getListInsidersQueryKey({ limit, offset: page * limit }) } }
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 border-l-4 border-primary pl-4">
        <h1 className="text-3xl font-bold tracking-tight font-mono uppercase text-primary flex items-center gap-3">
          <UserCircle className="h-8 w-8" />
          Corporate Insider Trades
        </h1>
        <p className="text-muted-foreground">Form 4 filings from C-suite executives, directors, and 10% owners.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="border-border/50 bg-card/50">
          <CardContent className="p-4 flex flex-col justify-center min-h-[100px]">
            <h3 className="text-xs font-mono uppercase text-muted-foreground mb-2">Buy/Sell Ratio</h3>
            {summaryLoading ? <Skeleton className="h-8 w-20" /> : (
              <div className="text-2xl font-bold font-mono tracking-tighter text-primary">
                {summary?.buyRatio ? summary.buyRatio.toFixed(2) : "—"}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="border-border/50 bg-card/50">
          <CardContent className="p-4 flex flex-col justify-center min-h-[100px]">
            <h3 className="text-xs font-mono uppercase text-muted-foreground mb-2">Total Buy Volume</h3>
            {summaryLoading ? <Skeleton className="h-8 w-20" /> : (
              <div className="text-2xl font-bold font-mono tracking-tighter text-buy">
                {formatCurrency(summary?.buyVolume)}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="border-border/50 bg-card/50">
          <CardContent className="p-4 flex flex-col justify-center min-h-[100px]">
            <h3 className="text-xs font-mono uppercase text-muted-foreground mb-2">Total Sell Volume</h3>
            {summaryLoading ? <Skeleton className="h-8 w-20" /> : (
              <div className="text-2xl font-bold font-mono tracking-tighter text-sell">
                {formatCurrency(summary?.sellVolume)}
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="border-border/50 bg-card/50">
          <CardContent className="p-4 flex flex-col justify-center min-h-[100px]">
            <h3 className="text-xs font-mono uppercase text-muted-foreground mb-2">Last 30 Days</h3>
            {summaryLoading ? <Skeleton className="h-8 w-20" /> : (
              <div className="text-lg font-bold font-mono tracking-tighter">
                <span className="text-buy">{summary?.last30Days?.buys} Buys</span> / <span className="text-sell">{summary?.last30Days?.sells} Sells</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/50 bg-card/50">
        <CardHeader className="pb-2 border-b border-border/50">
          <CardTitle className="text-lg font-mono uppercase text-primary">Notable Large Trades</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {notableLoading ? (
            <div className="p-6 space-y-4 grid grid-cols-2 gap-4">
              {Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
            </div>
          ) : notable && notable.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 divide-y md:divide-y-0 md:divide-x divide-border/50 border-b border-border/50">
              {notable.map((trade) => (
                <div key={trade.id} className="p-4 hover:bg-muted/30 flex flex-col justify-between">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <Link href={`/stocks/${trade.ticker}`} className="font-mono font-bold text-xl text-primary hover:underline">
                        {trade.ticker}
                      </Link>
                      <div className="text-xs text-muted-foreground font-mono">{trade.transactionDate}</div>
                    </div>
                    <Badge variant="outline" className={cn("uppercase", trade.transactionType === "buy" ? "bg-buy" : "bg-sell")}>
                      {trade.transactionType}
                    </Badge>
                  </div>
                  <div className="my-2">
                    <div className="font-bold truncate">{trade.insiderName}</div>
                    <div className="text-xs text-muted-foreground truncate">{trade.insiderTitle}</div>
                  </div>
                  <div className={cn("text-lg font-mono font-bold mt-auto", trade.transactionType === "buy" ? "text-buy" : "text-sell")}>
                    {formatCurrency(trade.totalValue)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-6 text-center text-muted-foreground">No notable trades found.</div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/50">
        <CardHeader className="pb-2 border-b border-border/50 flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-mono uppercase">Recent Form 4 Filings</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {listLoading ? (
            <div className="p-6 space-y-4">{Array(10).fill(0).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : listData?.data && listData.data.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-muted/20 text-muted-foreground">
                    <th className="text-left font-medium py-3 px-4">Date</th>
                    <th className="text-left font-medium py-3 px-4">Ticker</th>
                    <th className="text-left font-medium py-3 px-4">Insider</th>
                    <th className="text-left font-medium py-3 px-4">Type</th>
                    <th className="text-right font-medium py-3 px-4">Shares</th>
                    <th className="text-right font-medium py-3 px-4">Price</th>
                    <th className="text-right font-medium py-3 px-4">Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {listData.data.map((tx) => (
                    <tr key={tx.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-mono text-xs text-muted-foreground">{tx.transactionDate}</td>
                      <td className="py-3 px-4">
                        <Link href={`/stocks/${tx.ticker}`} className="font-mono font-bold text-primary hover:underline">
                          {tx.ticker}
                        </Link>
                      </td>
                      <td className="py-3 px-4">
                        <div className="font-medium">{tx.insiderName}</div>
                        <div className="text-xs text-muted-foreground truncate max-w-[200px]" title={tx.insiderTitle}>{tx.insiderTitle}</div>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className={cn(
                          "uppercase text-[10px] px-1.5 py-0",
                          tx.transactionType === "buy" ? "bg-buy" : tx.transactionType === "sell" ? "bg-sell" : ""
                        )}>
                          {tx.transactionType.replace("_", " ")}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-right font-mono">{formatShares(tx.shares)}</td>
                      <td className="py-3 px-4 text-right font-mono text-muted-foreground">${tx.pricePerShare.toFixed(2)}</td>
                      <td className={cn("py-3 px-4 text-right font-mono font-bold", tx.transactionType === "buy" ? "text-buy" : tx.transactionType === "sell" ? "text-sell" : "")}>
                        {formatCurrency(tx.totalValue)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6 text-center text-muted-foreground">No filings found.</div>
          )}
          
          {listData?.total && listData.total > 0 && (
            <div className="p-4 border-t border-border/50 flex items-center justify-between bg-muted/10">
              <div className="text-xs text-muted-foreground font-mono">
                Showing {page * limit + 1}-{Math.min((page + 1) * limit, listData.total)} of {listData.total}
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>
                  <ChevronLeft className="h-4 w-4" /> Prev
                </Button>
                <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={(page + 1) * limit >= listData.total}>
                  Next <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
