"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetchNodes } from "@/lib/api";
import { Server, Zap, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { NodeStatusEntry } from "@/lib/types";

function NodeDetails({ node, onClose }: { node: NodeStatusEntry; onClose: () => void }) {
  const isOnline = node.status === "ONLINE";
  return (
    <div className="absolute bottom-full mb-2 right-4 bg-card border border-border shadow-xl rounded-xl p-4 w-72 animate-in fade-in slide-in-from-bottom-2 z-50 text-left">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Server size={14} className={isOnline ? "text-green-500" : "text-red-500"} />
          <h3 className="text-sm font-semibold">{node.node_id}</h3>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
          <X size={14} />
        </button>
      </div>
      <div className="flex flex-col gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Status</span>
          <Badge variant="outline" className={`text-[10px] ${isOnline ? "bg-green-500/10 text-green-500 border-green-500/30" : "bg-red-500/10 text-red-500 border-red-500/30"}`}>
            {node.status}
          </Badge>
        </div>
        {isOnline && (
          <>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Model</span>
              <span className="font-mono text-foreground truncate ml-4" title={node.model_loaded || ""}>{node.model_loaded || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Latency</span>
              <span className="font-mono">{node.latency_ms} ms</span>
            </div>
          </>
        )}
        <div className="flex justify-between mt-2 pt-2 border-t border-border/50">
          <span className="text-muted-foreground">Last Success</span>
          <span className="font-mono text-muted-foreground">
            {node.last_success ? new Date(node.last_success).toLocaleTimeString("en-IN") : "Never"}
          </span>
        </div>
      </div>
    </div>
  );
}

export function NodeStatusBar() {
  const { data } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 5_000 });
  const [selectedNode, setSelectedNode] = useState<NodeStatusEntry | null>(null);

  if (!data?.nodes) return null;

  return (
    <div className="relative flex items-center h-10 px-4 gap-4 overflow-x-auto text-xs whitespace-nowrap hide-scrollbar">
      <span className="font-semibold text-muted-foreground tracking-wider uppercase mr-2 flex items-center gap-1.5">
        <Zap size={12} /> Nodes
      </span>
      {data.nodes.map(n => {
        const isOnline = n.status === "ONLINE";
        return (
          <button
            key={n.node_id}
            onClick={() => setSelectedNode(n)}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-md transition-colors hover:bg-muted ${selectedNode?.node_id === n.node_id ? "bg-muted" : ""}`}
          >
            <span className={`w-2 h-2 rounded-full ${isOnline ? "bg-green-500" : "bg-red-500"}`} />
            <span className="font-mono text-muted-foreground">{n.node_id}</span>
          </button>
        );
      })}
      
      {selectedNode && (
        <NodeDetails node={selectedNode} onClose={() => setSelectedNode(null)} />
      )}
    </div>
  );
}
