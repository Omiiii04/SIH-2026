"use client";

import { useState } from "react";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ChevronDown, ChevronRight, Server, Zap, BrainCircuit, Activity, AlertTriangle, ArrowRight, CornerDownRight } from "lucide-react";

interface ThinkingPanelProps {
  result: QueryResponse | NodeFailureResponse;
  ok: boolean;
}

export function ThinkingPanel({ result, ok }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const isFailure = !ok || "error_type" in result;

  const data = result as QueryResponse;
  const failData = result as NodeFailureResponse;

  const total_ms = result.total_ms ?? (result as any).latency_ms ?? 0;
  const routing_ms = result.routing_ms ?? 0;
  const inference_ms = result.inference_ms ?? 0;
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
          <span className="text-red-400 font-medium">Failed after {total_ms.toFixed(0)}ms</span>
        ) : (
          <span>Thinking <span className="opacity-50">({total_ms.toFixed(0)}ms)</span></span>
        )}
      </button>

      {expanded && (
        <div className="mt-2 text-xs border border-border/60 bg-card rounded-xl p-4 shadow-sm animate-in fade-in slide-in-from-top-2 flex flex-col gap-6">
          
          {/* Status Banner */}
          {isFailure && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg p-3 flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-semibold">
                <AlertTriangle size={14} />
                Node Failure
              </div>
              <div>{String(failData.error_type ?? "")}{failData.detail ? `: ${typeof failData.detail === "string" ? failData.detail : JSON.stringify(failData.detail)}` : ""}</div>
            </div>
          )}

          {/* New Routing Flow Visualization */}
          <div className="flex flex-col gap-3">
            <h4 className="font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <ArrowRight size={12} /> Routing Path
            </h4>
            <div className="flex flex-col text-[11px] font-mono pl-2 border-l border-border/50 ml-2 py-1 gap-1.5">
              <div className="flex items-center gap-2 text-muted-foreground"><CornerDownRight size={12}/> User Query</div>
              <div className="flex items-center gap-2 text-muted-foreground"><CornerDownRight size={12}/> Classifier</div>
              <div className="flex items-center gap-2 text-muted-foreground"><CornerDownRight size={12}/> Router</div>
              
              {routing && routing.was_fallback ? (
                <>
                  <div className="flex items-center gap-2 text-orange-400"><CornerDownRight size={12}/> {routing.selected_node} (Failed)</div>
                  <div className="flex items-center gap-2 text-orange-400"><CornerDownRight size={12}/> Fallback triggered: {routing.reason}</div>
                  <div className="flex items-center gap-2 text-primary"><CornerDownRight size={12}/> {node}</div>
                </>
              ) : (
                <div className="flex items-center gap-2 text-primary"><CornerDownRight size={12}/> {node}</div>
              )}
              
              {model && <div className="flex items-center gap-2 text-primary"><CornerDownRight size={12}/> {model}</div>}
              {isFailure ? (
                <div className="flex items-center gap-2 text-red-400"><CornerDownRight size={12}/> Failure: {failData.error_type}</div>
              ) : (
                <div className="flex items-center gap-2 text-green-500"><CornerDownRight size={12}/> Response Delivered</div>
              )}
            </div>
          </div>

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
                  <span className="opacity-70">Capability</span>
                  <span className="font-medium text-foreground">{classification.required_capability}</span>
                  <span className="opacity-70">Method</span>
                  <span className="font-medium text-foreground">{classification.matched_rule || classification.classifier_method}</span>
                </div>
              </div>
            )}

            {/* Execution */}
            <div className="flex flex-col gap-2">
              <h4 className="font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5"><Activity size={12} /> Execution</h4>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                <span className="opacity-70">Final Node</span>
                <span className="font-mono text-primary flex items-center gap-1"><Server size={10} />{node}</span>
                {model && (
                  <>
                    <span className="opacity-70">Model</span>
                    <span className="font-mono text-foreground truncate">{model}</span>
                  </>
                )}
                <span className="opacity-70">Routing Time</span>
                <span className="font-mono text-foreground flex items-center gap-1"><Zap size={10} />{routing_ms.toFixed(0)} ms</span>
                <span className="opacity-70">Inference Time</span>
                <span className="font-mono text-foreground flex items-center gap-1"><Zap size={10} />{inference_ms.toFixed(0)} ms</span>
                <span className="opacity-70">Total Time</span>
                <span className="font-mono text-foreground flex items-center gap-1"><Zap size={10} />{total_ms.toFixed(0)} ms</span>
                <span className="opacity-70">Status</span>
                <span className="font-medium text-foreground">{isFailure ? "Failed" : "Completed"}</span>
                  <>
                  </>
              </div>
            </div>
          </div>

          {/* Raw Telemetry Debugging */}
          <details className="text-[10px] text-muted-foreground border-t border-border/40 pt-2 mt-2">
            <summary className="cursor-pointer hover:text-foreground">Developer Debug</summary>
            <pre className="mt-2 p-2 bg-muted/30 rounded overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>

        </div>
      )}
    </div>
  );
}
