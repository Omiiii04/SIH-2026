"use client";

import { useState } from "react";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ChevronDown, ChevronRight, Server, Zap, BrainCircuit, Activity, AlertTriangle, ArrowRight } from "lucide-react";

interface ThinkingPanelProps {
  result: QueryResponse | NodeFailureResponse;
  ok: boolean;
}

export function ThinkingPanel({ result, ok }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const isFailure = !ok || "error_type" in result;

  const data = result as QueryResponse;
  const failData = result as NodeFailureResponse;

  const latency = result.latency_ms;
  const node = result.selected_node;
  const model = ok ? data.selected_model : undefined;
  const routing = result.routing;
  const classification = ok ? data.classification : undefined;

  return (
    <div className="mt-2 mb-4 w-fit max-w-full">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors bg-muted/30 hover:bg-muted/50 px-2.5 py-1.5 rounded-full border border-border/50"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {isFailure ? (
          <span className="text-red-400 font-medium">Failed after {latency.toFixed(0)}ms</span>
        ) : (
          <span>Thinking <span className="opacity-50">({latency.toFixed(0)}ms)</span></span>
        )}
      </button>

      {expanded && (
        <div className="mt-2 text-xs border border-border/60 bg-card rounded-xl p-4 shadow-sm animate-in fade-in slide-in-from-top-2 flex flex-col gap-4">
          
          {/* Status Banner */}
          {isFailure && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg p-3 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle size={14} />
                Node Failure
              </div>
              <div>{failData.error_type}: {failData.detail}</div>
            </div>
          )}

          {/* Fallback / Routing */}
          {routing && routing.was_fallback && (
            <div className="bg-orange-500/10 border border-orange-500/20 text-orange-400 rounded-lg p-3 flex flex-col gap-1.5">
              <div className="font-semibold flex items-center gap-1.5"><ArrowRight size={14} /> Fallback Triggered</div>
              <div><span className="opacity-70">Reason:</span> {routing.reason}</div>
              <div><span className="opacity-70">Selected Node:</span> {routing.selected_node}</div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Classification */}
            {classification && (
              <div className="flex flex-col gap-2">
                <h4 className="font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5"><BrainCircuit size={12} /> Classification</h4>
                <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                  <span className="opacity-70">Intent</span>
                  <span className="font-medium text-foreground">{classification.task_type}</span>
                  <span className="opacity-70">Input Type</span>
                  <span className="font-medium text-foreground">{classification.input_type}</span>
                  <span className="opacity-70">Difficulty</span>
                  <span className="font-medium text-foreground">{classification.difficulty}</span>
                  <span className="opacity-70">Confidence</span>
                  <span className="font-medium text-foreground">{(classification.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            )}

            {/* Execution */}
            <div className="flex flex-col gap-2">
              <h4 className="font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5"><Activity size={12} /> Execution</h4>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                <span className="opacity-70">Node</span>
                <span className="font-mono text-primary flex items-center gap-1"><Server size={10} />{node}</span>
                {model && (
                  <>
                    <span className="opacity-70">Model</span>
                    <span className="font-mono text-foreground truncate">{model}</span>
                  </>
                )}
                <span className="opacity-70">Latency</span>
                <span className="font-mono text-foreground flex items-center gap-1"><Zap size={10} />{latency.toFixed(0)} ms</span>
                {!isFailure && routing && !routing.was_fallback && (
                  <>
                    <span className="opacity-70">Reason</span>
                    <span className="text-foreground truncate" title={routing.reason}>{routing.reason}</span>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
