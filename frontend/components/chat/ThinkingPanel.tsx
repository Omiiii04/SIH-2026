"use client";

import { useState } from "react";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ChevronDown, ChevronRight, AlertCircle } from "lucide-react";

interface ThinkingPanelProps {
  result: QueryResponse | NodeFailureResponse;
  ok: boolean;
  onRetry?: () => void;
}

export function ThinkingPanel({ result, ok, onRetry }: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const isFailure = !ok || "error_type" in result;

  const data = result as QueryResponse;
  const failData = result as NodeFailureResponse;

  const total_ms = result.total_ms ?? (result as any).latency_ms ?? 0;
  const routing_ms = result.routing_ms ?? 0;
  const inference_ms = result.inference_ms ?? 0;
  const node = result.selected_node ?? "—";
  const model = ok ? data.selected_model : undefined;
  const routing = result.routing;
  const classification = ok ? data.classification : undefined;

  const seconds = (total_ms / 1000).toFixed(1);
  const inferenceSec = inference_ms >= 1000 ? `${(inference_ms / 1000).toFixed(1)} s` : `${inference_ms.toFixed(0)} ms`;

  return (
    <div className="mt-2 text-xs select-none">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1.5 py-1 px-2 text-[11px] font-medium text-muted-foreground hover:text-foreground rounded-md transition-colors hover:bg-muted/50"
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {isFailure ? (
          <span className="text-rose-500 inline-flex items-center gap-1 font-normal">
            <AlertCircle size={12} /> Response failed · {seconds}s
          </span>
        ) : (
          <span>Response details · {seconds}s</span>
        )}
      </button>

      {expanded && (
        <div className="mt-1.5 p-3 rounded-md border border-border/60 bg-muted/20 text-xs flex flex-col gap-2.5 max-w-md animate-in fade-in duration-100">
          {isFailure && (
            <div className="text-[11px] text-rose-500 bg-rose-500/10 border border-rose-500/20 rounded p-2 flex flex-col gap-1.5">
              <span className="font-medium">
                {failData.error_type ? `Unable to reach node (${failData.error_type})` : "Unable to reach the selected model."}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {typeof failData.detail === "string" ? failData.detail : "Request timed out or connection refused."}
              </span>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="self-start mt-1 text-[11px] font-medium text-foreground underline hover:no-underline"
                >
                  Retry
                </button>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
            <div>
              <span className="text-muted-foreground">Detected task</span>
              <div className="font-medium text-foreground">{classification?.task_type || "General Q&A"}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Selected node</span>
              <div className="font-mono text-foreground">{node}</div>
            </div>
            {model && (
              <div>
                <span className="text-muted-foreground">Selected model</span>
                <div className="font-mono text-foreground truncate" title={model}>{model}</div>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Fallback</span>
              <div className="text-foreground">{routing?.was_fallback ? "Yes" : "None"}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Routing time</span>
              <div className="font-mono text-foreground">{routing_ms.toFixed(0)} ms</div>
            </div>
            <div>
              <span className="text-muted-foreground">Inference time</span>
              <div className="font-mono text-foreground">{inferenceSec}</div>
            </div>
          </div>

          <details className="text-[10px] text-muted-foreground pt-1.5 border-t border-border/40">
            <summary className="cursor-pointer hover:text-foreground select-none">
              Developer Debug
            </summary>
            <pre className="mt-1.5 p-2 rounded bg-background border border-border/60 overflow-x-auto text-[10px] font-mono text-foreground/80 max-h-48">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}


