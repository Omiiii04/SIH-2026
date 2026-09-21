"use client";

import { useState } from "react";
import { searchMemory } from "@/lib/api";
import type { MemorySearchResult } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Search, Loader2, DatabaseZap, Clock, Server, X } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

export function SemanticSearch({ onClose }: { onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<MemorySearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

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
    <div className="absolute inset-0 z-50 bg-card/95 backdrop-blur-sm border-r border-border flex flex-col">
      <div className="flex items-center justify-between p-4 border-b border-border">
        <div className="flex items-center gap-2 text-primary">
          <DatabaseZap size={16} />
          <h2 className="text-sm font-semibold">Semantic Search</h2>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X size={16} />
        </button>
      </div>

      <div className="p-4 flex flex-col gap-4 flex-1 overflow-hidden">
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search past interactions…"
            className="text-sm bg-background"
          />
          <Button type="submit" disabled={!query.trim() || loading} size="icon" className="shrink-0">
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
          </Button>
        </form>

        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 rounded-md p-2 border border-red-500/20">
            {error}
          </p>
        )}

        {results !== null && (
          <ScrollArea className="flex-1">
            {results.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No matching memories found.</p>
            ) : (
              <div className="flex flex-col gap-2 pb-4">
                {results.map((r) => (
                  <div key={r.request_id} className="border border-border/60 rounded-md p-3 flex flex-col gap-1.5 bg-background/50 text-left">
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <Badge variant="outline" className="text-[10px] bg-primary/10 text-primary border-primary/30 px-1 py-0 h-4">
                        {(r.score * 100).toFixed(1)}% match
                      </Badge>
                      <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Server size={9} />{r.node_id}
                      </span>
                    </div>
                    <p className="text-xs font-medium text-foreground">Q: {r.query}</p>
                    <p className="text-xs text-muted-foreground line-clamp-3">A: {r.response}</p>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        )}
      </div>
    </div>
  );
}
