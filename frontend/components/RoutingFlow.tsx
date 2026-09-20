"use client";

import { cn } from "@/lib/utils";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ArrowDown, User, Cpu, Brain, GitBranch, Server, Sparkles, CheckCircle2, XCircle } from "lucide-react";

type Step = {
  id: string;
  label: string;
  value: string;
  icon: React.ReactNode;
  highlight?: boolean;
  error?: boolean;
};

function FlowStep({ step, index }: { step: Step; index: number }) {
  return (
    <div
      className="animate-flow"
      style={{ animationDelay: `${index * 80}ms`, animationFillMode: "both" }}
    >
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-2.5 rounded-lg border transition-all",
          step.error
            ? "border-red-500/40 bg-red-500/10"
            : step.highlight
            ? "border-primary/50 bg-primary/10 shadow-[0_0_12px_oklch(0.65_0.22_265/25%)]"
            : "border-border/50 bg-white/[0.03]"
        )}
      >
        <span className={cn("shrink-0", step.highlight ? "text-primary" : "text-muted-foreground")}>
          {step.icon}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{step.label}</p>
          <p className={cn("text-sm font-semibold truncate", step.error ? "text-red-400" : step.highlight ? "text-primary" : "")}>
            {step.value}
          </p>
        </div>
      </div>
    </div>
  );
}

interface Props {
  result: QueryResponse | NodeFailureResponse | null;
  ok: boolean;
  loading: boolean;
}

export function RoutingFlow({ result, ok, loading }: Props) {
  if (!result && !loading) {
    return (
      <div className="glass rounded-xl p-5 flex flex-col items-center gap-2 text-center text-muted-foreground">
        <GitBranch size={28} className="opacity-30" />
        <p className="text-sm">Routing decisions appear here after a query</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="glass rounded-xl p-5 flex flex-col gap-2">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-11 rounded-lg bg-white/[0.04] animate-pulse" />
        ))}
      </div>
    );
  }

  const qr = result as QueryResponse;
  const nf = result as NodeFailureResponse;
  const isFailure = !ok;

  const steps: Step[] = [
    {
      id: "user-input",
      label: "USER INPUT",
      value: isFailure ? nf.detail?.slice(0, 60) + "…" : qr.classification?.input_type?.toUpperCase() ?? "TEXT",
      icon: <User size={14} />,
    },
    {
      id: "input-analysis",
      label: "INPUT ANALYSIS",
      value: isFailure ? "—" : `${qr.classification?.task_type?.replace(/_/g, " ")} (${(qr.classification?.confidence * 100).toFixed(0)}% conf)`,
      icon: <Brain size={14} />,
    },
    {
      id: "task-classification",
      label: "TASK CLASSIFICATION",
      value: isFailure ? "—" : qr.classification?.classifier_method?.replace("rule:", "rule → ").replace("llm:", "llm → ") ?? "—",
      icon: <Cpu size={14} />,
    },
    {
      id: "difficulty",
      label: "DIFFICULTY",
      value: isFailure ? "—" : (qr.classification?.difficulty ?? "—").toUpperCase(),
      icon: <Sparkles size={14} />,
    },
    {
      id: "selected-node",
      label: "SELECTED NODE",
      value: isFailure ? nf.selected_node : qr.selected_node,
      icon: <Server size={14} />,
      highlight: !isFailure,
      error: isFailure,
    },
    {
      id: "selected-model",
      label: "MODEL",
      value: isFailure ? "—" : qr.selected_model,
      icon: <Brain size={14} />,
      highlight: !isFailure,
    },
    {
      id: "response-status",
      label: "RESPONSE",
      value: isFailure ? `ERROR: ${nf.error_type}` : `✓ ${qr.latency_ms.toFixed(0)} ms`,
      icon: isFailure ? <XCircle size={14} /> : <CheckCircle2 size={14} />,
      highlight: !isFailure,
      error: isFailure,
    },
  ];

  return (
    <div id="routing-flow" className="glass rounded-xl p-4 flex flex-col gap-1.5">
      {steps.map((step, i) => (
        <div key={step.id}>
          <FlowStep step={step} index={i} />
          {i < steps.length - 1 && (
            <div className="flex justify-center py-0.5">
              <ArrowDown size={12} className="text-muted-foreground/40" />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
