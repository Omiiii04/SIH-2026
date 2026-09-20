"use client";

import useSWR from "swr";
import { fetchMetrics } from "@/lib/api";
import { TrendingUp, CheckCircle2, XCircle, Clock, RotateCcw, GitBranch } from "lucide-react";

export function MetricsBar() {
  const { data } = useSWR("/api/v1/metrics", fetchMetrics, { refreshInterval: 10_000 });

  if (!data) return null;

  const items = [
    { label: "Requests",    value: data.total_requests,                         icon: <TrendingUp size={12} /> },
    { label: "Success",     value: `${(data.success_rate * 100).toFixed(0)}%`,  icon: <CheckCircle2 size={12} className="text-green-400" /> },
    { label: "Failed",      value: data.failed,                                  icon: <XCircle size={12} className="text-red-400" /> },
    { label: "Avg Latency", value: data.avg_latency_ms != null ? `${data.avg_latency_ms.toFixed(0)} ms` : "—", icon: <Clock size={12} /> },
    { label: "Retries",     value: data.total_retries,                           icon: <RotateCcw size={12} /> },
    { label: "Fallbacks",   value: data.fallback_count,                          icon: <GitBranch size={12} className="text-yellow-400" /> },
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => (
        <div
          key={item.label}
          className="glass flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs"
        >
          <span className="text-muted-foreground">{item.icon}</span>
          <span className="text-muted-foreground">{item.label}:</span>
          <span className="font-semibold font-mono">{item.value}</span>
        </div>
      ))}
    </div>
  );
}
