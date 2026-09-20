"use client";

import useSWR from "swr";
import { fetchNodes } from "@/lib/api";
import { NodeCard } from "./NodeCard";
import { RefreshCw } from "lucide-react";

const NODE_ORDER = ["NODE-TEXT", "NODE-VISION", "NODE-REASONING", "NODE-CODE", "NODE-RAG"];

export function NodeGrid({ activeNode }: { activeNode?: string }) {
  const { data, error, isLoading } = useSWR("/api/v1/nodes", fetchNodes, {
    refreshInterval: 10_000,
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {NODE_ORDER.map((id) => (
          <div key={id} className="glass rounded-xl p-4 h-32 animate-pulse" id={`node-skeleton-${id}`} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass rounded-xl p-4 text-red-400 text-sm flex items-center gap-2">
        <RefreshCw size={14} className="animate-spin" />
        Cannot reach orchestrator — is FastAPI running on port 8000?
      </div>
    );
  }

  // Sort by fixed order
  const nodeMap = Object.fromEntries((data?.nodes ?? []).map((n) => [n.node_id, n]));

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
      {NODE_ORDER.map((id) => {
        const node = nodeMap[id];
        if (!node) return null;
        return <NodeCard key={id} node={node} active={activeNode === id} />;
      })}
    </div>
  );
}
