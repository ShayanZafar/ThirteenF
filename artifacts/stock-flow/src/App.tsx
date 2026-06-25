import { Shell } from "@/components/layout/Shell";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/not-found";

import Dashboard from "@/pages/dashboard";
import Institutional from "@/pages/institutional";
import Insiders from "@/pages/insiders";
import Politicians from "@/pages/politicians";
import Lockups from "@/pages/lockups";
import StockDetail from "@/pages/stock-detail";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 60 * 1000,
      retry: 1
    }
  }
});

function Router() {
  return (
    <Shell>
      <Switch>
        <Route path="/" component={Dashboard} />
        <Route path="/institutional" component={Institutional} />
        <Route path="/insiders" component={Insiders} />
        <Route path="/politicians" component={Politicians} />
        <Route path="/lockups" component={Lockups} />
        <Route path="/stocks/:ticker" component={StockDetail} />
        <Route component={NotFound} />
      </Switch>
    </Shell>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <Router />
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
