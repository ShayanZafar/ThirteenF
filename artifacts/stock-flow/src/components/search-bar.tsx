import { useState, useRef, useEffect } from "react";
import { Search } from "lucide-react";
import { useLocation } from "wouter";
import { useSearchStocks, getSearchStocksQueryKey } from "@workspace/api-client-react";
import { Input } from "@/components/ui/input";

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [, setLocation] = useLocation();
  const wrapperRef = useRef<HTMLDivElement>(null);

  const { data: results, isLoading } = useSearchStocks(
    { q: query },
    { query: { enabled: query.length >= 2, queryKey: getSearchStocksQueryKey({ q: query }) } }
  );

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={wrapperRef} className="relative w-full max-w-sm">
      <div className="relative">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search ticker (e.g. AAPL)..."
          className="w-full bg-background border-border pl-9 text-sm focus-visible:ring-primary/50"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          data-testid="input-global-search"
        />
      </div>

      {isOpen && query.length >= 2 && (
        <div className="absolute top-full mt-1 w-full bg-popover border border-border rounded-md shadow-lg overflow-hidden z-50">
          {isLoading ? (
            <div className="p-3 text-sm text-muted-foreground">Searching...</div>
          ) : results && results.length > 0 ? (
            <ul className="max-h-[300px] overflow-auto py-1">
              {results.map((result) => (
                <li key={result.ticker}>
                  <button
                    className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground flex justify-between items-center"
                    onClick={() => {
                      setQuery("");
                      setIsOpen(false);
                      setLocation(`/stocks/${result.ticker}`);
                    }}
                    data-testid={`btn-search-result-${result.ticker}`}
                  >
                    <span className="font-mono font-medium">{result.ticker}</span>
                    <span className="text-muted-foreground truncate ml-2 text-xs">{result.companyName}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="p-3 text-sm text-muted-foreground">No tickers found.</div>
          )}
        </div>
      )}
    </div>
  );
}
