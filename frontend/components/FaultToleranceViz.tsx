"use client";

import useSWR from "swr";
import { fetchNodes } from "@/lib/api";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ArrowDown, WifiOff, ArrowRight } from "lucide-react";

interface Props {
  lastResult: QueryResponse | NodeFailureResponse | null;
  lastOk: boolean;
}

export function FaultToleranceViz({ lastResult, lastOk }: Props) {
  const { data } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 10_000 });
  const nodes = data?.nodes ?? [];
  const offlineNodes = nodes.filter((n) => n.status === "OFFLINE");
  const qr = lastResult as QueryResponse;
  const wasFallback = qr?.routing?.was_fallback;

  // Determine primary vs fallback in last response
  const fallbackNode = wasFallback ? qr?.selected_node : null;

  if (offlineNodes.length === 0 && !wasFallback) {
    return (
      <div className="glass rounded-xl p-5 flex flex-col items-center gap-2 text-muted-foreground text-center">
        <div className="w-8 h-8 rounded-full bg-green-500/20 flex items-center justify-center">
          <span className="text-green-400 text-lg">✓</span>
        </div>
        <p className="text-sm font-medium text-green-400">All nodes operational</p>
        <p className="text-xs">Fault tolerance visualization activates when a node goes offline or a fallback occurs.</p>
      </div>
    );
  }

  return (
    <div id="fault-tolerance-viz" className="glass rounded-xl p-4 flex flex-col gap-3">
      {/* Offline nodes */}
      {offlineNodes.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Offline Nodes</p>
          {offlineNodes.map((node) => (
            <div
              key={node.node_id}
              className="flex items-center gap-3 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10"
            >
              <WifiOff size={14} className="text-red-400 animate-blink-offline shrink-0" />
              <div>
                <p className="text-sm font-mono font-semibold">{node.node_id}</p>
                <p className="text-xs text-red-400 font-bold">OFFLINE</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Fallback visualization */}
      {wasFallback && fallbackNode && (
        <div className="flex flex-col gap-1.5 border-t border-border/40 pt-3">
          <p className="text-xs text-muted-foreground uppercase tracking-wider">Fallback Routing</p>

          {/* Primary (offline) — best guess: whatever node was NOT selected */}
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 opacity-70">
            <WifiOff size={12} className="text-red-400" />
            <div>
              <p className="text-[10px] text-muted-foreground">PRIMARY NODE</p>
              <p className="text-sm font-mono text-red-400">OFFLINE</p>
            </div>
          </div>

          <div className="flex justify-center">
            <ArrowDown size={14} className="text-yellow-400" />
          </div>

          {/* Fallback node */}
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg border border-yellow-500/40 bg-yellow-500/10">
            <ArrowRight size={14} className="text-yellow-400 shrink-0" />
            <div>
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">FALLBACK</p>
              <p className="text-sm font-mono font-semibold text-yellow-300">{fallbackNode}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
