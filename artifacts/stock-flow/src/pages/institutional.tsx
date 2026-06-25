import { useGetInstitutionalTopMovers, useGetInstitutionalMostBought, useListInstitutional, getGetInstitutionalTopMoversQueryKey, getGetInstitutionalMostBoughtQueryKey, getListInstitutionalQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatShares, cn } from "@/lib/utils";
import { Link } from "wouter";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { ChevronLeft, ChevronRight, Building2 } from "lucide-react";

export default function Institutional() {
  const [page, setPage] = useState(0);
  const limit = 20;
  
  const { data: movers, isLoading: moversLoading } = useGetInstitutionalTopMovers({ limit: 4 }, { query: { queryKey: getGetInstitutionalTopMoversQueryKey({ limit: 4 }) } });
  const { data: mostBought, isLoading: mostBoughtLoading } = useGetInstitutionalMostBought({ limit: 5 }, { query: { queryKey: getGetInstitutionalMostBoughtQueryKey({ limit: 5 }) } });
  const { data: listData, isLoading: listLoading } = useListInstitutional(
    { limit, offset: page * limit }, 
    { query: { queryKey: getListInstitutionalQueryKey({ limit, offset: page * limit }) } }
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 border-l-4 border-blue pl-4">
        <h1 className="text-3xl font-bold tracking-tight font-mono uppercase text-blue flex items-center gap-3">
          <Building2 className="h-8 w-8" />
          Institutional 13F Flow
        </h1>
        <p className="text-muted-foreground">Quarterly position changes from major funds and institutional investors.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-border/50 bg-card/50">
          <CardHeader className="pb-2 border-b border-border/50">
            <CardTitle className="text-lg font-mono uppercase">Top Movers This Quarter</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {moversLoading ? (
              <div className="p-6 space-y-4">{Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
            ) : movers && movers.length > 0 ? (
              <div className="divide-y divide-border/50">
                {movers.map((mover) => (
                  <div key={mover.institutionName} className="p-4 flex items-center justify-between hover:bg-muted/30">
                    <div>
                      <h4 className="font-bold text-primary">{mover.institutionName}</h4>
                      <div className="flex items-center gap-4 mt-1 text-xs font-mono text-muted-foreground">
                        <span><span className="text-buy">{mover.buysCount}</span> Buys</span>
                        <span><span className="text-sell">{mover.sellsCount}</span> Sells</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={cn("font-mono font-bold", mover.netValueChange > 0 ? "text-buy" : mover.netValueChange < 0 ? "text-sell" : "")}>
                        {mover.netValueChange > 0 ? "+" : ""}{formatCurrency(mover.netValueChange)}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 flex gap-2 justify-end">
                        {mover.topBuy && <span>Top Buy: <Link href={`/stocks/${mover.topBuy}`} className="text-primary hover:underline">{mover.topBuy}</Link></span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center text-muted-foreground">No data available.</div>
            )}
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-card/50">
          <CardHeader className="pb-2 border-b border-border/50">
            <CardTitle className="text-lg font-mono uppercase">Most Bought Tickers</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {mostBoughtLoading ? (
              <div className="p-6 space-y-4">{Array(5).fill(0).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : mostBought && mostBought.length > 0 ? (
              <div className="divide-y divide-border/50">
                {mostBought.map((ticker) => (
                  <div key={ticker.ticker} className="p-3 flex items-center justify-between hover:bg-muted/30">
                    <Link href={`/stocks/${ticker.ticker}`} className="font-mono font-bold text-primary hover:underline">
                      {ticker.ticker}
                    </Link>
                    <div className="text-right">
                      <div className="font-mono text-sm">{ticker.count} Funds</div>
                      <div className="text-xs text-buy font-mono">+{formatCurrency(ticker.totalValue)}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center text-muted-foreground">No data available.</div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="border-border/50 bg-card/50">
        <CardHeader className="pb-2 border-b border-border/50 flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-mono uppercase">Recent 13F Filings</CardTitle>
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
                    <th className="text-left font-medium py-3 px-4">Institution</th>
                    <th className="text-left font-medium py-3 px-4">Ticker</th>
                    <th className="text-left font-medium py-3 px-4">Action</th>
                    <th className="text-right font-medium py-3 px-4">Shares Changed</th>
                    <th className="text-right font-medium py-3 px-4">Value Changed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {listData.data.map((tx) => (
                    <tr key={tx.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-mono text-xs text-muted-foreground">{tx.reportDate}</td>
                      <td className="py-3 px-4 font-medium truncate max-w-[200px]" title={tx.institutionName}>{tx.institutionName}</td>
                      <td className="py-3 px-4">
                        <Link href={`/stocks/${tx.ticker}`} className="font-mono font-bold text-primary hover:underline">
                          {tx.ticker}
                        </Link>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className={cn(
                          "uppercase text-[10px] px-1.5 py-0",
                          tx.action === "buy" || tx.action === "increase" ? "bg-buy" : "bg-sell"
                        )}>
                          {tx.action}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-right font-mono">
                        {tx.sharesChange > 0 ? "+" : ""}{formatShares(tx.sharesChange)}
                      </td>
                      <td className={cn("py-3 px-4 text-right font-mono", tx.valueChange > 0 ? "text-buy" : "text-sell")}>
                        {tx.valueChange > 0 ? "+" : ""}{formatCurrency(tx.valueChange)}
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
