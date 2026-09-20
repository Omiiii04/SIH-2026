"use client";

import { useState } from "react";
import { searchMemory } from "@/lib/api";
import type { MemorySearchResult } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Search, Loader2, DatabaseZap, Clock, Server } from "lucide-react";

export function MemorySearch() {
  const [query, setQuery]     = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<MemorySearchResult[] | null>(null);
  const [error, setError]     = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await searchMemory("dashboard-user", query.trim(), 8);
      setResults(res.results);
    } catch (err) {
      setError("ChromaDB unavailable or no memories stored yet.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div id="memory-search" className="glass rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <DatabaseZap size={14} className="text-primary" />
        <span className="text-sm font-semibold">Semantic Memory Search</span>
      </div>

      <form onSubmit={handleSearch} className="flex gap-2">
        <Input
          id="memory-search-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search past interactions…"
          className="bg-transparent text-sm"
        />
        <Button id="memory-search-submit" type="submit" disabled={!query.trim() || loading} size="sm" className="shrink-0 gap-1.5">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
          Search
        </Button>
      </form>

      {error && (
        <p className="text-xs text-red-400 border border-red-500/30 bg-red-500/10 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {results !== null && (
        <ScrollArea className="max-h-64">
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No matching memories found.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {results.map((r) => (
                <div
                  key={r.request_id}
                  className="border border-border/40 rounded-lg p-3 flex flex-col gap-1.5 bg-white/[0.02] hover:bg-white/[0.04] transition-colors"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/30">
                      {(r.score * 100).toFixed(1)}% match
                    </Badge>
                    <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                      <Server size={9} />{r.node_id}
                    </span>
                    <span className="flex items-center gap-1 text-[10px] text-muted-foreground ml-auto">
                      <Clock size={9} />{new Date(r.timestamp).toLocaleString("en-IN")}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-foreground/80 truncate">Q: {r.query}</p>
                  <p className="text-xs text-muted-foreground line-clamp-2">A: {r.response}</p>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      )}
    </div>
  );
}
