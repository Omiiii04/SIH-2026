"use client";

import { useState, useCallback, useId } from "react";
import useSWR from "swr";
import { fetchHealth } from "@/lib/api";
import type { QueryResponse, NodeFailureResponse, HistoryEntry } from "@/lib/types";

import { NodeGrid }          from "@/components/NodeGrid";
import { QueryPanel }        from "@/components/QueryPanel";
import { RoutingFlow }       from "@/components/RoutingFlow";
import { ResponsePanel }     from "@/components/ResponsePanel";
import { FaultToleranceViz } from "@/components/FaultToleranceViz";
import { HistoryTable }      from "@/components/HistoryTable";
import { MemorySearch }      from "@/components/MemorySearch";
import { MetricsBar }        from "@/components/MetricsBar";

import { Activity, Cpu, Wifi, WifiOff } from "lucide-react";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
      <span className="w-4 h-px bg-border inline-block" />
      {children}
      <span className="flex-1 h-px bg-border inline-block" />
    </h2>
  );
}

function OrchestratorStatus() {
  const { data, error } = useSWR("/health", fetchHealth, { refreshInterval: 15_000 });
  const ok = !error && data?.status === "ok";
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-400" : "text-red-400"}`}>
      {ok ? <Wifi size={12} /> : <WifiOff size={12} />}
      <span>{ok ? "Orchestrator Online" : "Orchestrator Offline"}</span>
    </div>
  );
}

export default function DashboardPage() {
  // ponytail: session stays constant per page load
  const sessionId = useId().replace(/:/g, "");

  const [lastResult, setLastResult] = useState<QueryResponse | NodeFailureResponse | null>(null);
  const [lastOk,     setLastOk]     = useState(false);
  const [loading,    setLoading]    = useState(false);
  const [history,    setHistory]    = useState<HistoryEntry[]>([]);

  const activeNode = lastOk ? (lastResult as QueryResponse)?.selected_node : undefined;

  const handleResult = useCallback((r: QueryResponse | NodeFailureResponse, ok: boolean) => {
    setLastResult(r);
    setLastOk(ok);
    setLoading(false);
  }, []);

  const handleHistoryEntry = useCallback((e: HistoryEntry) => {
    setHistory((prev) => [e, ...prev].slice(0, 50)); // keep last 50
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-border/40 backdrop-blur-xl bg-background/80">
        <div className="max-w-[1600px] mx-auto px-6 py-3 flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center animate-glow">
              <Cpu size={16} className="text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight">Distributed AI Orchestrator</h1>
              <p className="text-[10px] text-muted-foreground">SIH-2026 · 5-Node Inference Mesh</p>
            </div>
          </div>
          <div className="ml-auto flex items-center gap-4">
            <OrchestratorStatus />
            <Activity size={14} className="text-muted-foreground animate-pulse-online" />
          </div>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <main className="flex-1 max-w-[1600px] mx-auto w-full px-6 py-6 flex flex-col gap-6">

        {/* Metrics bar */}
        <MetricsBar />

        {/* Node status */}
        <section aria-label="Node Status" className="flex flex-col gap-2">
          <SectionTitle>Node Status</SectionTitle>
          <NodeGrid activeNode={activeNode} />
        </section>

        {/* Main 3-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Col 1: Query + Fault Tolerance */}
          <div className="flex flex-col gap-4">
            <SectionTitle>Query Panel</SectionTitle>
            <QueryPanel
              onResult={(r, ok) => { setLoading(false); handleResult(r, ok); }}
              onHistoryEntry={handleHistoryEntry}
              sessionId={sessionId}
            />
            <SectionTitle>Fault Tolerance</SectionTitle>
            <FaultToleranceViz lastResult={lastResult} lastOk={lastOk} />
          </div>

          {/* Col 2: Routing flow */}
          <div className="flex flex-col gap-2">
            <SectionTitle>Routing Visualization</SectionTitle>
            <RoutingFlow result={lastResult} ok={lastOk} loading={loading} />
          </div>

          {/* Col 3: Response */}
          <div className="flex flex-col gap-2">
            <SectionTitle>Response</SectionTitle>
            <ResponsePanel result={lastResult} ok={lastOk} />
          </div>
        </div>

        {/* History */}
        <section aria-label="Request History" className="flex flex-col gap-2">
          <SectionTitle>Request History</SectionTitle>
          <HistoryTable entries={history} />
        </section>

        {/* Memory search */}
        <section aria-label="Semantic Memory" className="flex flex-col gap-2">
          <SectionTitle>Semantic Memory</SectionTitle>
          <MemorySearch />
        </section>
      </main>
    </div>
  );
}
