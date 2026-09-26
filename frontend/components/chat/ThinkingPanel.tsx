"use client";

import { useState } from "react";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ChevronDown, ChevronRight, AlertCircle } from "lucide-react";

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
  const node = result.selected_node ?? "—";
  const model = ok ? data.selected_model : undefined;
  const routing = result.routing;
  const classification = ok ? data.classification : undefined;

  const seconds = (total_ms / 1000).toFixed(2);

  return (
    <div className="mt-2 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-1.5 py-1 px-2 text-[11px] font-medium text-muted-foreground hover:text-foreground rounded-md transition-colors hover:bg-muted/60"
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        {isFailure ? (
          <span className="text-rose-500 inline-flex items-center gap-1">
            <AlertCircle size={12} /> Execution error ({seconds}s)
          </span>
        ) : (
          <span>Routing details · {seconds}s</span>
        )}
      </button>

      {expanded && (
        <div className="mt-1.5 p-3 rounded-lg border border-border/80 bg-muted/20 text-xs flex flex-col gap-3 max-w-lg animate-in fade-in duration-150">
          {isFailure && (
            <div className="text-rose-500 text-[11px] bg-rose-500/10 border border-rose-500/20 rounded p-2">
              <span className="font-semibold">{failData.error_type}: </span>
              <span>{typeof failData.detail === "string" ? failData.detail : JSON.stringify(failData.detail)}</span>
            </div>
          )}

          <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
            <div>
              <span className="text-muted-foreground">Detected Task:</span>{" "}
              <span className="font-medium text-foreground">{classification?.task_type || "Standard QA"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Selected Node:</span>{" "}
              <span className="font-mono text-foreground">{node}</span>
            </div>
            {model && (
              <div>
                <span className="text-muted-foreground">Model:</span>{" "}
                <span className="font-mono text-foreground truncate" title={model}>{model}</span>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Fallback:</span>{" "}
              <span className="text-foreground">{routing?.was_fallback ? "Yes" : "None"}</span>
            </div>
            <div>
              <span className="text-muted-foreground">Routing Time:</span>{" "}
              <span className="font-mono text-foreground">{routing_ms.toFixed(0)} ms</span>
            </div>
            <div>
              <span className="text-muted-foreground">Inference Time:</span>{" "}
              <span className="font-mono text-foreground">{inference_ms.toFixed(0)} ms</span>
            </div>
          </div>

          <details className="text-[10px] text-muted-foreground pt-1.5 border-t border-border/60">
            <summary className="cursor-pointer hover:text-foreground select-none">
              Developer Debug JSON
            </summary>
            <pre className="mt-1.5 p-2 rounded bg-background border border-border overflow-x-auto text-[10px] font-mono text-foreground/80">
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

