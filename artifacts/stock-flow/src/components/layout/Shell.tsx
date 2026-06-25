import { Link, useLocation } from "wouter";
import { Activity, Building2, UserCircle, Users, Lock, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { SearchBar } from "@/components/search-bar";

const NAVIGATION = [
  { name: "Dashboard", href: "/", icon: Activity },
  { name: "Institutional 13F", href: "/institutional", icon: Building2 },
  { name: "Insider Trades", href: "/insiders", icon: UserCircle },
  { name: "Politicians", href: "/politicians", icon: Users },
  { name: "Lockups", href: "/lockups", icon: Lock },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const [location] = useLocation();

  return (
    <div className="flex h-screen w-full bg-background text-foreground overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 border-r border-border bg-sidebar flex flex-col hidden md:flex">
        <div className="h-14 flex items-center px-4 border-b border-border">
          <div className="flex items-center gap-2 text-primary font-bold text-lg tracking-tight uppercase font-mono">
            <Activity className="h-5 w-5" />
            <span>FlowTrack</span>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {NAVIGATION.map((item) => {
            const isActive = location === item.href || (item.href !== "/" && location.startsWith(item.href));
            const Icon = item.icon;
            
            return (
              <Link key={item.name} href={item.href}>
                <div
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors cursor-pointer group",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-accent-foreground"
                      : "text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
                  )}
                  data-testid={`link-nav-${item.name.toLowerCase().replace(/\\s+/g, "-")}`}
                >
                  <Icon className={cn("h-4 w-4", isActive ? "text-primary" : "text-muted-foreground group-hover:text-primary/70")} />
                  {item.name}
                  {isActive && <ChevronRight className="h-4 w-4 ml-auto opacity-50" />}
                </div>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border mt-auto">
          <div className="text-xs text-muted-foreground/60 space-y-1">
            <p>SYSTEM STATUS: <span className="text-green-500 font-mono">ONLINE</span></p>
            <p>DATA DELAY: <span className="text-primary font-mono">REALTIME</span></p>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <header className="h-14 border-b border-border bg-background/95 backdrop-blur z-10 flex items-center justify-between px-4 sm:px-6">
          <div className="flex items-center gap-4 flex-1">
            {/* Mobile menu toggle could go here */}
            <div className="md:hidden font-mono font-bold text-primary mr-2">FLOWTRACK</div>
            <SearchBar />
          </div>
          <div className="flex items-center gap-4">
            <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" title="System Online"></div>
            <div className="text-xs font-mono text-muted-foreground hidden sm:block">
              {new Date().toISOString().split("T")[0]}
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8 scroll-smooth">
          <div className="mx-auto max-w-7xl">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
