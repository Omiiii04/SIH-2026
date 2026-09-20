"use client";

import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Clock, Server, Cpu, MessageSquare, AlertCircle, GitBranch } from "lucide-react";

interface Props {
  result: QueryResponse | NodeFailureResponse | null;
  ok: boolean;
}

export function ResponsePanel({ result, ok }: Props) {
  if (!result) {
    return (
      <div className="glass rounded-xl p-5 flex flex-col items-center gap-2 text-muted-foreground text-center h-full min-h-[200px] justify-center">
        <MessageSquare size={28} className="opacity-30" />
        <p className="text-sm">Response appears here</p>
      </div>
    );
  }

  const qr = result as QueryResponse;
  const nf = result as NodeFailureResponse;

  return (
    <div id="response-panel" className="glass rounded-xl p-4 flex flex-col gap-3 animate-slide-in">
      {/* Status badge */}
      <div className="flex items-center gap-2">
        {ok ? (
          <Badge className="bg-green-500/20 text-green-300 border-green-500/30">SUCCESS</Badge>
        ) : (
          <Badge className="bg-red-500/20 text-red-300 border-red-500/30 flex gap-1">
            <AlertCircle size={11} /> ERROR
          </Badge>
        )}
        <span className="text-xs text-muted-foreground font-mono ml-auto">
          {result.request_id?.slice(0, 8)}…
        </span>
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <Server size={11} />
          {(qr.selected_node ?? nf.selected_node) || "—"}
        </span>
        <span className="flex items-center gap-1">
          <Cpu size={11} />
          {qr.selected_model ?? "—"}
        </span>
        <span className="flex items-center gap-1">
          <Clock size={11} />
          {((qr.latency_ms ?? nf.latency_ms) || 0).toFixed(0)} ms
        </span>
      </div>

      {/* Routing reason */}
      {(qr.routing ?? nf.routing) && (
        <div className="flex items-start gap-2 text-xs bg-white/[0.04] rounded-lg px-3 py-2 border border-white/[0.06]">
          <GitBranch size={11} className="text-primary mt-0.5 shrink-0" />
          <div>
            <span className="text-muted-foreground">Reason: </span>
            <span>{(qr.routing ?? nf.routing)?.reason}</span>
            {(qr.routing ?? nf.routing)?.was_fallback && (
              <Badge className="ml-2 text-[10px] bg-yellow-500/20 text-yellow-300 border-yellow-500/30">FALLBACK</Badge>
            )}
          </div>
        </div>
      )}

      {/* Response text */}
      <ScrollArea className="max-h-56">
        <div className="text-sm leading-relaxed whitespace-pre-wrap border border-border/40 rounded-lg p-3 bg-white/[0.02]">
          {ok ? (qr.response || "(empty response)") : (
            <span className="text-red-400">{nf.detail}</span>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
