"use client";

import { useState } from "react";
import { searchMemory } from "@/lib/api";
import type { MemorySearchResult } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Loader2, X, Server } from "lucide-react";
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
    } catch {
      setError("Memory search unavailable or no memories stored yet.");
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
      <div 
        className="fixed inset-0" 
        onClick={onClose} 
      />
      <div className="relative w-full max-w-lg bg-card border border-border rounded-xl shadow-xl flex flex-col max-h-[80vh] overflow-hidden z-10 animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Search size={16} className="text-muted-foreground" />
            <h2 className="text-sm font-semibold">Search Memory</h2>
          </div>
          <button 
            onClick={onClose} 
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-4 flex flex-col gap-3 flex-1 overflow-hidden">
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search past conversations…"
              className="text-sm bg-background border-border"
            />
            <Button 
              type="submit" 
              disabled={!query.trim() || loading} 
              size="sm" 
              className="shrink-0 h-9 px-3"
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : "Search"}
            </Button>
          </form>

          {error && (
            <p className="text-xs text-muted-foreground bg-muted/60 rounded-md p-2.5 border border-border">
              {error}
            </p>
          )}

          {results !== null && (
            <ScrollArea className="flex-1 pr-2">
              {results.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-8">
                  No matching memories found.
                </p>
              ) : (
                <div className="flex flex-col gap-2 pb-2">
                  {results.map((r) => (
                    <div 
                      key={r.request_id} 
                      className="border border-border/70 rounded-lg p-3 flex flex-col gap-1.5 bg-background text-left"
                    >
                      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                        <span className="font-medium text-foreground">
                          {(r.score * 100).toFixed(0)}% relevance
                        </span>
                        <span className="flex items-center gap-1 font-mono text-[10px]">
                          <Server size={10} /> {r.node_id}
                        </span>
                      </div>
                      <p className="text-xs font-medium text-foreground line-clamp-1">Q: {r.query}</p>
                      <p className="text-xs text-muted-foreground line-clamp-3">A: {r.response}</p>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          )}
        </div>
      </div>
    </div>
  );
}

