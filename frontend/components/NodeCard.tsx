"use client";

import { cn } from "@/lib/utils";
import type { NodeStatusEntry } from "@/lib/types";
import { Cpu, Zap, Clock, Wifi, WifiOff, AlertTriangle } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const NODE_META: Record<string, { icon: string; color: string; capability: string; model: string }> = {
  "NODE-1": { icon: "1",  color: "oklch(0.65 0.22 265)",  capability: "text",               model: "Unknown" },
  "NODE-2": { icon: "2",  color: "oklch(0.65 0.22 320)",  capability: "vision",             model: "Unknown" },
  "NODE-3": { icon: "3",  color: "oklch(0.65 0.22 165)",  capability: "reasoning",          model: "Unknown" },
  "NODE-4": { icon: "4",  color: "oklch(0.78 0.18 65)",   capability: "coding",             model: "Unknown" },
  "NODE-5": { icon: "5",  color: "oklch(0.65 0.22 200)",  capability: "embedding/retrieval",model: "Unknown" },
};

function StatusIcon({ status }: { status: string }) {
  if (status === "ONLINE")  return <Wifi   size={14} className="text-green-400" />;
  if (status === "DEGRADED") return <AlertTriangle size={14} className="text-yellow-400" />;
  return <WifiOff size={14} className="text-red-400" />;
}

function statusBadge(status: string) {
  if (status === "ONLINE")   return "bg-green-500/20 text-green-300 border-green-500/30";
  if (status === "DEGRADED") return "bg-yellow-500/20 text-yellow-300 border-yellow-500/30";
  return "bg-red-500/20 text-red-300 border-red-500/30";
}

export function NodeCard({ node, active }: { node: NodeStatusEntry; active?: boolean }) {
  const meta = NODE_META[node.node_id] ?? { icon: "?", color: "#888", capability: "unknown", model: "unknown" };
  const isOffline = node.status === "OFFLINE";

  return (
    <div
      id={`node-card-${node.node_id}`}
      className={cn(
        "glass rounded-xl p-4 flex flex-col gap-3 transition-all duration-500",
        isOffline && "opacity-60 border-red-500/30",
        active && "ring-2 ring-primary animate-glow",
        !isOffline && "hover:border-white/20"
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold font-mono shrink-0",
            isOffline && "animate-blink-offline"
          )}
          style={{ background: `${meta.color}22`, border: `1px solid ${meta.color}55`, color: meta.color }}
        >
          {meta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-mono text-sm font-semibold truncate">
            {node.node_id === "NODE-1" ? "Node 1 (Orchestrator)" : `Node ${node.node_id.split("-")[1]}`}
          </p>
          <p className="text-xs text-muted-foreground capitalize">{meta.capability}</p>
        </div>
        <StatusIcon status={node.status} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* Status badge */}
        <Badge variant="outline" className={cn("w-fit text-xs", statusBadge(node.status))}>
          {node.status}
        </Badge>
        {/* Orchestrator Badge */}
        {node.node_id === "NODE-1" && (
          <Badge variant="outline" className="w-fit text-xs bg-purple-500/20 text-purple-300 border-purple-500/30">
            ORCHESTRATOR
          </Badge>
        )}
        {/* Capacity badge */}
        {node.capacity && (
          <Badge variant="outline" className="w-fit text-xs bg-blue-500/20 text-blue-300 border-blue-500/30 font-mono">
            {node.capacity}
          </Badge>
        )}
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Cpu size={11} />
          <span className="truncate font-mono">{node.model_loaded ?? meta.model}</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Clock size={11} />
          <span>{node.latency_ms != null ? `${node.latency_ms.toFixed(0)} ms` : "—"}</span>
        </div>
      </div>

      {/* Offline banner */}
      {isOffline && (
        <div className="flex items-center gap-1.5 bg-red-500/10 border border-red-500/30 rounded-lg px-2 py-1">
          <WifiOff size={11} className="text-red-400 animate-blink-offline" />
          <span className="text-xs text-red-400 font-semibold">OFFLINE</span>
        </div>
      )}

      {/* Active indicator */}
      {active && (
        <div className="flex items-center gap-1.5 bg-primary/10 border border-primary/30 rounded-lg px-2 py-1">
          <Zap size={11} className="text-primary" />
          <span className="text-xs text-primary font-semibold">ACTIVE</span>
        </div>
      )}
    </div>
  );
}
