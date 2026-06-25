import { useGetPoliticianLeaders, useGetPoliticiansMostTraded, useListPoliticians, getGetPoliticianLeadersQueryKey, getGetPoliticiansMostTradedQueryKey, getListPoliticiansQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, cn } from "@/lib/utils";
import { Link } from "wouter";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { ChevronLeft, ChevronRight, Users } from "lucide-react";

export default function Politicians() {
  const [page, setPage] = useState(0);
  const limit = 20;
  
  const { data: leaders, isLoading: leadersLoading } = useGetPoliticianLeaders({ limit: 4 }, { query: { queryKey: getGetPoliticianLeadersQueryKey({ limit: 4 }) } });
  const { data: mostTraded, isLoading: mostTradedLoading } = useGetPoliticiansMostTraded({ limit: 5 }, { query: { queryKey: getGetPoliticiansMostTradedQueryKey({ limit: 5 }) } });
  const { data: listData, isLoading: listLoading } = useListPoliticians(
    { limit, offset: page * limit }, 
    { query: { queryKey: getListPoliticiansQueryKey({ limit, offset: page * limit }) } }
  );

  const getPartyColor = (party: string) => {
    if (party === "democrat") return "bg-blue text-blue-foreground border-blue/30";
    if (party === "republican") return "bg-sell text-sell-foreground border-sell/30";
    return "bg-muted text-muted-foreground";
  };

  const getPartyDot = (party: string) => {
    if (party === "democrat") return "bg-blue";
    if (party === "republican") return "bg-sell";
    return "bg-muted-foreground";
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 border-l-4 border-purple pl-4">
        <h1 className="text-3xl font-bold tracking-tight font-mono uppercase text-purple flex items-center gap-3">
          <Users className="h-8 w-8" />
          Congressional Trades
        </h1>
        <p className="text-muted-foreground">STOCK Act disclosures from US Senators and House Representatives.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2 border-border/50 bg-card/50">
          <CardHeader className="pb-2 border-b border-border/50">
            <CardTitle className="text-lg font-mono uppercase">Most Active Politicians</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {leadersLoading ? (
              <div className="p-6 space-y-4">{Array(4).fill(0).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}</div>
            ) : leaders && leaders.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border/50">
                {leaders.map((leader) => (
                  <div key={leader.politician} className="p-4 hover:bg-muted/30">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={cn("w-3 h-3 rounded-full", getPartyDot(leader.party))} />
                      <h4 className="font-bold text-primary truncate" title={leader.politician}>{leader.politician}</h4>
                      <Badge variant="outline" className="text-[10px] uppercase ml-auto">{leader.chamber}</Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-2 mt-3">
                      <div>
                        <div className="text-xs text-muted-foreground font-mono uppercase">Volume</div>
                        <div className="font-bold font-mono">{formatCurrency(leader.estimatedVolume)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground font-mono uppercase">Trades</div>
                        <div className="font-bold font-mono">{leader.tradeCount}</div>
                      </div>
                    </div>
                    {leader.topTicker && (
                      <div className="text-xs text-muted-foreground mt-3 pt-3 border-t border-border/30">
                        Top Ticker: <Link href={`/stocks/${leader.topTicker}`} className="text-primary font-mono hover:underline">{leader.topTicker}</Link>
                      </div>
                    )}
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
            <CardTitle className="text-lg font-mono uppercase">Most Traded Tickers</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {mostTradedLoading ? (
              <div className="p-6 space-y-4">{Array(5).fill(0).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}</div>
            ) : mostTraded && mostTraded.length > 0 ? (
              <div className="divide-y divide-border/50">
                {mostTraded.map((ticker) => (
                  <div key={ticker.ticker} className="p-3 flex items-center justify-between hover:bg-muted/30">
                    <Link href={`/stocks/${ticker.ticker}`} className="font-mono font-bold text-primary hover:underline">
                      {ticker.ticker}
                    </Link>
                    <div className="text-right">
                      <div className="font-mono text-sm">{ticker.count} Trades</div>
                      <div className="text-xs text-muted-foreground font-mono">Vol: {formatCurrency(ticker.totalValue)}</div>
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
          <CardTitle className="text-lg font-mono uppercase">Recent Disclosures</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {listLoading ? (
            <div className="p-6 space-y-4">{Array(10).fill(0).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : listData?.data && listData.data.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-muted/20 text-muted-foreground">
                    <th className="text-left font-medium py-3 px-4">Tx Date</th>
                    <th className="text-left font-medium py-3 px-4">Filed</th>
                    <th className="text-left font-medium py-3 px-4">Politician</th>
                    <th className="text-left font-medium py-3 px-4">Ticker</th>
                    <th className="text-left font-medium py-3 px-4">Action</th>
                    <th className="text-right font-medium py-3 px-4">Amount Range</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {listData.data.map((tx) => (
                    <tr key={tx.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4 font-mono text-xs text-muted-foreground">{tx.transactionDate}</td>
                      <td className="py-3 px-4 font-mono text-xs text-muted-foreground">
                        {tx.disclosureDate}
                        {tx.daysToDisclose && tx.daysToDisclose > 45 && (
                          <span className="text-sell ml-1" title="Late filing">*</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <div className={cn("w-2 h-2 rounded-full shrink-0", getPartyDot(tx.party))} />
                          <span className="font-medium">{tx.politician}</span>
                          <span className="text-xs text-muted-foreground uppercase hidden md:inline-block">({tx.chamber[0]})</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <Link href={`/stocks/${tx.ticker}`} className="font-mono font-bold text-primary hover:underline">
                          {tx.ticker}
                        </Link>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className={cn(
                          "uppercase text-[10px] px-1.5 py-0",
                          tx.transactionType === "buy" ? "bg-buy" : "bg-sell"
                        )}>
                          {tx.transactionType}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-xs whitespace-nowrap">
                        {tx.amountRange}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6 text-center text-muted-foreground">No disclosures found.</div>
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
