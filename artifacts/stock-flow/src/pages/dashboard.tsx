import { useGetDashboardStats, useGetDashboardSignals, useGetDashboardActivity, getGetDashboardStatsQueryKey, getGetDashboardSignalsQueryKey, getGetDashboardActivityQueryKey } from "@workspace/api-client-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatShares, cn } from "@/lib/utils";
import { Link } from "wouter";
import { ArrowUpRight, ArrowDownRight, Activity, Building2, UserCircle, Users, Lock, ChevronRight } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useGetDashboardStats({ query: { queryKey: getGetDashboardStatsQueryKey() } });
  const { data: signals, isLoading: signalsLoading } = useGetDashboardSignals({}, { query: { queryKey: getGetDashboardSignalsQueryKey({}) } });
  const { data: activity, isLoading: activityLoading } = useGetDashboardActivity({ limit: 15 }, { query: { queryKey: getGetDashboardActivityQueryKey({ limit: 15 }) } });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight font-mono text-primary uppercase">Market Flow Intelligence</h1>
        <p className="text-muted-foreground">Aggregated smart-money signals across institutions, insiders, and politicians.</p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard title="Buy Pressure" value={stats?.netBuyPressure ? `${(stats.netBuyPressure * 100).toFixed(1)}%` : ""} loading={statsLoading} valueClass={stats?.netBuyPressure && stats.netBuyPressure > 0.5 ? "text-buy" : "text-sell"} />
        <StatCard title="Institutional Changes" value={stats?.totalInstitutionalChanges?.toLocaleString()} loading={statsLoading} />
        <StatCard title="Insider Trades" value={stats?.totalInsiderTrades?.toLocaleString()} loading={statsLoading} />
        <StatCard title="Politician Trades" value={stats?.totalPoliticianTrades?.toLocaleString()} loading={statsLoading} />
        <StatCard title="Upcoming Lockups" value={stats?.lockupsThisMonth?.toLocaleString()} loading={statsLoading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Top Signals */}
        <Card className="lg:col-span-2 border-border/50 bg-card/50 backdrop-blur">
          <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-border/50 bg-card">
            <CardTitle className="text-lg font-mono uppercase text-primary">Top Signal Movers</CardTitle>
            <Link href="/institutional" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1">
              View all <ChevronRight className="h-3 w-3" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {signalsLoading ? (
              <div className="p-6 space-y-4">
                {Array(5).fill(0).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
              </div>
            ) : signals && signals.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border/50 bg-muted/20 text-muted-foreground">
                      <th className="text-left font-medium py-3 px-4">Ticker</th>
                      <th className="text-right font-medium py-3 px-4">Score</th>
                      <th className="text-right font-medium py-3 px-4">Inst. Flow</th>
                      <th className="text-right font-medium py-3 px-4">Insider Flow</th>
                      <th className="text-right font-medium py-3 px-4">Pol. Flow</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {signals.map((signal) => (
                      <tr key={signal.ticker} className="hover:bg-muted/30 transition-colors">
                        <td className="py-3 px-4">
                          <Link href={`/stocks/${signal.ticker}`} className="flex flex-col group">
                            <span className="font-mono font-bold text-primary group-hover:underline">{signal.ticker}</span>
                            <span className="text-xs text-muted-foreground truncate max-w-[150px]">{signal.companyName}</span>
                          </Link>
                        </td>
                        <td className="py-3 px-4 text-right">
                          <Badge variant="outline" className={cn("font-mono font-bold text-sm", signal.signalScore > 0 ? "bg-buy" : signal.signalScore < 0 ? "bg-sell" : "")}>
                            {signal.signalScore > 0 ? "+" : ""}{signal.signalScore}
                          </Badge>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          <span className="text-buy">{signal.institutionalBuys}</span> / <span className="text-sell">{signal.institutionalSells}</span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          <span className="text-buy">{signal.insiderBuys}</span> / <span className="text-sell">{signal.insiderSells}</span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-xs">
                          <span className="text-buy">{signal.politicianBuys}</span> / <span className="text-sell">{signal.politicianSells}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-6 text-center text-muted-foreground">No signals found.</div>
            )}
          </CardContent>
        </Card>

        {/* Activity Feed */}
        <Card className="border-border/50 bg-card/50 backdrop-blur flex flex-col">
          <CardHeader className="pb-2 border-b border-border/50 bg-card shrink-0">
            <CardTitle className="text-lg font-mono uppercase text-primary flex items-center gap-2">
              <Activity className="h-4 w-4" /> Live Feed
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-auto max-h-[600px]">
            {activityLoading ? (
              <div className="p-4 space-y-4">
                {Array(6).fill(0).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
              </div>
            ) : activity && activity.length > 0 ? (
              <div className="divide-y divide-border/50">
                {activity.map((item) => (
                  <div key={item.id} className="p-4 hover:bg-muted/30 transition-colors flex gap-3">
                    <div className="mt-1">
                      {item.category === "institutional" && <Building2 className="h-4 w-4 text-blue" />}
                      {item.category === "insider" && <UserCircle className="h-4 w-4 text-primary" />}
                      {item.category === "politician" && <Users className="h-4 w-4 text-purple" />}
                      {item.category === "lockup" && <Lock className="h-4 w-4 text-amber" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-1">
                        <Link href={`/stocks/${item.ticker}`} className="font-mono font-bold text-primary hover:underline text-sm">
                          {item.ticker}
                        </Link>
                        <span className="text-xs text-muted-foreground">{new Date(item.date).toLocaleDateString()}</span>
                      </div>
                      <p className="text-sm font-medium leading-tight truncate">{item.title}</p>
                      <div className="flex items-center justify-between mt-2">
                        <Badge variant="outline" className={cn(
                          "text-[10px] px-1.5 py-0 uppercase",
                          item.direction === "buy" ? "bg-buy" : item.direction === "sell" ? "bg-sell" : ""
                        )}>
                          {item.direction}
                        </Badge>
                        {item.amount && (
                          <span className="font-mono text-xs text-muted-foreground">{formatCurrency(item.amount)}</span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-6 text-center text-muted-foreground">No activity.</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StatCard({ title, value, loading, valueClass }: { title: string, value?: string | number, loading: boolean, valueClass?: string }) {
  return (
    <Card className="border-border/50 bg-card/50 backdrop-blur">
      <CardContent className="p-4 flex flex-col justify-center h-full min-h-[100px]">
        <h3 className="text-xs font-mono uppercase text-muted-foreground mb-2">{title}</h3>
        {loading ? (
          <Skeleton className="h-8 w-20" />
        ) : (
          <div className={cn("text-2xl font-bold font-mono tracking-tighter", valueClass)}>{value || "—"}</div>
        )}
      </CardContent>
    </Card>
  );
}
