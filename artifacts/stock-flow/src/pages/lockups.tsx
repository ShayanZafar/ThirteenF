import { useGetLockupsExpiringSoon, useListLockups, getGetLockupsExpiringSoonQueryKey, getListLockupsQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatShares, cn } from "@/lib/utils";
import { Link } from "wouter";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { ChevronLeft, ChevronRight, Lock, AlertTriangle } from "lucide-react";

export default function Lockups() {
  const [page, setPage] = useState(0);
  const limit = 20;
  
  const { data: upcoming, isLoading: upcomingLoading } = useGetLockupsExpiringSoon({ days: 14 }, { query: { queryKey: getGetLockupsExpiringSoonQueryKey({ days: 14 }) } });
  const { data: listData, isLoading: listLoading } = useListLockups(
    { limit, offset: page * limit }, 
    { query: { queryKey: getListLockupsQueryKey({ limit, offset: page * limit }) } }
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-2 border-l-4 border-amber pl-4">
        <h1 className="text-3xl font-bold tracking-tight font-mono uppercase text-amber flex items-center gap-3">
          <Lock className="h-8 w-8" />
          IPO Lockup Expirations
        </h1>
        <p className="text-muted-foreground">Tracking when insider shares unlock and become available to sell on the open market.</p>
      </div>

      <Card className="border-amber/30 bg-amber/5">
        <CardHeader className="pb-2 border-b border-amber/20">
          <CardTitle className="text-lg font-mono uppercase text-amber flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" /> Expiring in next 14 days
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {upcomingLoading ? (
            <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              {Array(3).fill(0).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}
            </div>
          ) : upcoming && upcoming.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-amber/20">
              {upcoming.map((lockup) => (
                <div key={lockup.id} className="p-6 flex flex-col justify-between hover:bg-amber/10 transition-colors">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <Link href={`/stocks/${lockup.ticker}`} className="font-mono font-bold text-2xl text-primary hover:underline">
                        {lockup.ticker}
                      </Link>
                      <div className="text-sm text-muted-foreground truncate max-w-[200px]">{lockup.companyName}</div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono font-bold text-lg text-amber">{lockup.daysUntilExpiry}</div>
                      <div className="text-[10px] uppercase text-muted-foreground font-mono">Days Left</div>
                    </div>
                  </div>
                  <div className="bg-background/50 rounded p-3 border border-amber/10 mt-auto">
                    <div className="flex justify-between mb-1 text-xs">
                      <span className="text-muted-foreground uppercase font-mono">Unlocking</span>
                      <span className="font-mono">{formatShares(lockup.sharesUnlocking)}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground uppercase font-mono">Est Value</span>
                      <span className="font-mono font-bold text-primary">{formatCurrency(lockup.estimatedValue)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="p-8 text-center text-muted-foreground">No lockups expiring in the next 14 days.</div>
          )}
        </CardContent>
      </Card>

      <Card className="border-border/50 bg-card/50">
        <CardHeader className="pb-2 border-b border-border/50 flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-mono uppercase">Full Expiration Calendar</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {listLoading ? (
            <div className="p-6 space-y-4">{Array(10).fill(0).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}</div>
          ) : listData?.data && listData.data.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border/50 bg-muted/20 text-muted-foreground">
                    <th className="text-left font-medium py-3 px-4">Expiry Date</th>
                    <th className="text-left font-medium py-3 px-4">Ticker</th>
                    <th className="text-left font-medium py-3 px-4">Company</th>
                    <th className="text-right font-medium py-3 px-4">Unlocking Shares</th>
                    <th className="text-right font-medium py-3 px-4">Est Value</th>
                    <th className="text-right font-medium py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {listData.data.map((lockup) => (
                    <tr key={lockup.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-mono font-medium">{lockup.expirationDate}</div>
                        {lockup.status === 'upcoming' && lockup.daysUntilExpiry !== null && (
                          <div className="text-[10px] text-amber uppercase font-mono">{lockup.daysUntilExpiry} days</div>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <Link href={`/stocks/${lockup.ticker}`} className="font-mono font-bold text-primary hover:underline">
                          {lockup.ticker}
                        </Link>
                      </td>
                      <td className="py-3 px-4 truncate max-w-[200px]">{lockup.companyName}</td>
                      <td className="py-3 px-4 text-right font-mono">{formatShares(lockup.sharesUnlocking)}</td>
                      <td className="py-3 px-4 text-right font-mono font-bold">{formatCurrency(lockup.estimatedValue)}</td>
                      <td className="py-3 px-4 text-right">
                        <Badge variant="outline" className={cn(
                          "uppercase text-[10px] px-1.5 py-0",
                          lockup.status === "upcoming" ? "bg-amber text-black border-amber" : "bg-muted text-muted-foreground"
                        )}>
                          {lockup.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-6 text-center text-muted-foreground">No lockup events found.</div>
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
