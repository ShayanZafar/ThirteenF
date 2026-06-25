import { useGetStockSignals, getGetStockSignalsQueryKey } from "@workspace/api-client-react";
import { useParams, Link } from "wouter";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatShares, cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Building2, UserCircle, Users, Lock, AlertTriangle } from "lucide-react";

export default function StockDetail() {
  const params = useParams();
  const ticker = params.ticker?.toUpperCase() || "";
  
  const { data: signals, isLoading, error } = useGetStockSignals(ticker, { 
    query: { 
      enabled: !!ticker,
      queryKey: getGetStockSignalsQueryKey(ticker) 
    } 
  });

  if (!ticker) return <div className="p-8 text-center text-muted-foreground">No ticker specified.</div>;

  if (error) {
    return (
      <div className="p-12 flex flex-col items-center justify-center border border-dashed border-border/50 rounded-lg bg-card/20">
        <AlertTriangle className="h-12 w-12 text-destructive mb-4 opacity-80" />
        <h2 className="text-xl font-mono text-destructive uppercase tracking-tight">Signal Fetch Failed</h2>
        <p className="text-muted-foreground mt-2 max-w-md text-center">
          Could not retrieve data for {ticker}. The ticker may be invalid or no signal data exists.
        </p>
        <Link href="/" className="mt-6 text-primary hover:underline font-mono text-sm">Return to Dashboard</Link>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row gap-6 justify-between items-start md:items-end border-b border-border pb-6">
        <div>
          {isLoading ? (
            <Skeleton className="h-12 w-48 mb-2" />
          ) : (
            <h1 className="text-5xl font-bold tracking-tighter font-mono text-primary flex items-center gap-4">
              {ticker}
            </h1>
          )}
          {isLoading ? (
            <Skeleton className="h-6 w-64" />
          ) : (
            <p className="text-xl text-muted-foreground">{signals?.companyName}</p>
          )}
        </div>
        
        {signals && (
          <Card className="border-border bg-card/80">
            <CardContent className="p-4 flex items-center gap-6">
              <div>
                <div className="text-xs font-mono text-muted-foreground uppercase mb-1">Composite Score</div>
                <Badge className={cn("text-xl font-mono px-3 py-1", signals.signalScore > 0 ? "bg-buy text-white" : signals.signalScore < 0 ? "bg-sell text-white" : "")}>
                  {signals.signalScore > 0 ? "+" : ""}{signals.signalScore}
                </Badge>
              </div>
              {signals.lockupExpiring && (
                <div className="bg-amber/10 border border-amber/30 text-amber px-3 py-2 rounded-md">
                  <div className="flex items-center gap-2 text-sm font-bold uppercase">
                    <Lock className="h-4 w-4" /> Lockup Alert
                  </div>
                  <div className="text-xs font-mono mt-1 opacity-80">Expiring soon</div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : signals ? (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          
          {/* Institutional Block */}
          <Card className="border-border/50 bg-card/50 overflow-hidden flex flex-col">
            <CardHeader className="bg-blue/10 border-b border-blue/20 pb-3 pt-4">
              <CardTitle className="text-lg font-mono uppercase text-blue flex items-center justify-between">
                <div className="flex items-center gap-2"><Building2 className="h-5 w-5" /> Institutional Flow</div>
                <div className="text-sm">
                  <span className="text-buy font-bold">{signals.institutionalBuys}</span> / <span className="text-sell font-bold">{signals.institutionalSells}</span>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex-1">
              {signals.recentInstitutionalChanges?.length > 0 ? (
                <div className="divide-y divide-border/50">
                  {signals.recentInstitutionalChanges.map(tx => (
                    <div key={tx.id} className="p-3 hover:bg-muted/30 flex items-center justify-between text-sm">
                      <div className="truncate pr-4 flex-1">
                        <div className="font-medium truncate">{tx.institutionName}</div>
                        <div className="text-xs text-muted-foreground font-mono">{tx.reportDate}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <Badge variant="outline" className={cn("uppercase text-[10px] px-1 py-0 mb-1 inline-block", tx.action === "buy" || tx.action === "increase" ? "bg-buy" : "bg-sell")}>
                          {tx.action}
                        </Badge>
                        <div className="font-mono text-xs text-muted-foreground">{formatShares(tx.sharesChange)} shs</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-muted-foreground text-sm">No recent institutional activity.</div>
              )}
            </CardContent>
          </Card>

          {/* Insider Block */}
          <Card className="border-border/50 bg-card/50 overflow-hidden flex flex-col">
            <CardHeader className="bg-primary/10 border-b border-primary/20 pb-3 pt-4">
              <CardTitle className="text-lg font-mono uppercase text-primary flex items-center justify-between">
                <div className="flex items-center gap-2"><UserCircle className="h-5 w-5" /> Insider Trades</div>
                <div className="text-sm">
                  <span className="text-buy font-bold">{signals.insiderBuys}</span> / <span className="text-sell font-bold">{signals.insiderSells}</span>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex-1">
              {signals.recentInsiderTrades?.length > 0 ? (
                <div className="divide-y divide-border/50">
                  {signals.recentInsiderTrades.map(tx => (
                    <div key={tx.id} className="p-3 hover:bg-muted/30 flex items-center justify-between text-sm">
                      <div className="truncate pr-4 flex-1">
                        <div className="font-medium truncate">{tx.insiderName}</div>
                        <div className="text-xs text-muted-foreground truncate">{tx.insiderTitle}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <Badge variant="outline" className={cn("uppercase text-[10px] px-1 py-0 mb-1 inline-block", tx.transactionType === "buy" ? "bg-buy" : tx.transactionType === "sell" ? "bg-sell" : "")}>
                          {tx.transactionType.replace("_", " ")}
                        </Badge>
                        <div className={cn("font-mono font-bold text-xs", tx.transactionType === "buy" ? "text-buy" : tx.transactionType === "sell" ? "text-sell" : "")}>
                          {formatCurrency(tx.totalValue)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-muted-foreground text-sm">No recent insider trades.</div>
              )}
            </CardContent>
          </Card>

          {/* Politicians Block */}
          <Card className="border-border/50 bg-card/50 overflow-hidden flex flex-col">
            <CardHeader className="bg-purple/10 border-b border-purple/20 pb-3 pt-4">
              <CardTitle className="text-lg font-mono uppercase text-purple flex items-center justify-between">
                <div className="flex items-center gap-2"><Users className="h-5 w-5" /> Politician Trades</div>
                <div className="text-sm">
                  <span className="text-buy font-bold">{signals.politicianBuys}</span> / <span className="text-sell font-bold">{signals.politicianSells}</span>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex-1">
              {signals.recentPoliticianTrades?.length > 0 ? (
                <div className="divide-y divide-border/50">
                  {signals.recentPoliticianTrades.map(tx => (
                    <div key={tx.id} className="p-3 hover:bg-muted/30 flex items-center justify-between text-sm">
                      <div className="truncate pr-4 flex-1">
                        <div className="font-medium truncate flex items-center gap-2">
                          {tx.politician}
                          <span className={cn("w-2 h-2 rounded-full", tx.party === "democrat" ? "bg-blue" : tx.party === "republican" ? "bg-sell" : "bg-muted-foreground")} />
                        </div>
                        <div className="text-xs text-muted-foreground font-mono">{tx.chamber} • {tx.transactionDate}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <Badge variant="outline" className={cn("uppercase text-[10px] px-1 py-0 mb-1 inline-block", tx.transactionType === "buy" ? "bg-buy" : "bg-sell")}>
                          {tx.transactionType}
                        </Badge>
                        <div className="font-mono text-xs">{tx.amountRange}</div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-muted-foreground text-sm">No recent politician trades.</div>
              )}
            </CardContent>
          </Card>

          {/* Lockups Block */}
          <Card className="border-border/50 bg-card/50 overflow-hidden flex flex-col">
            <CardHeader className="bg-amber/10 border-b border-amber/20 pb-3 pt-4">
              <CardTitle className="text-lg font-mono uppercase text-amber flex items-center gap-2">
                <Lock className="h-5 w-5" /> Lockup Expirations
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 flex-1">
              {signals.lockups?.length > 0 ? (
                <div className="divide-y divide-border/50">
                  {signals.lockups.map(lockup => (
                    <div key={lockup.id} className="p-4 hover:bg-muted/30">
                      <div className="flex justify-between items-center mb-2">
                        <div className="font-mono font-bold text-lg">{lockup.expirationDate}</div>
                        <Badge variant="outline" className={cn("uppercase", lockup.status === "upcoming" ? "bg-amber text-black border-amber/50" : "bg-muted text-muted-foreground")}>
                          {lockup.status}
                        </Badge>
                      </div>
                      {lockup.daysUntilExpiry !== null && lockup.daysUntilExpiry > 0 && (
                        <div className="text-sm font-mono text-amber mb-3">{lockup.daysUntilExpiry} days remaining</div>
                      )}
                      <div className="grid grid-cols-2 gap-4 mt-2 bg-muted/20 p-3 rounded border border-border/50">
                        <div>
                          <div className="text-xs text-muted-foreground uppercase">Unlocking</div>
                          <div className="font-mono font-bold">{formatShares(lockup.sharesUnlocking)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-muted-foreground uppercase">Est. Value</div>
                          <div className="font-mono font-bold text-primary">{formatCurrency(lockup.estimatedValue)}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-8 text-center text-muted-foreground text-sm">No lockups found for this ticker.</div>
              )}
            </CardContent>
          </Card>

        </div>
      ) : null}
    </div>
  );
}
