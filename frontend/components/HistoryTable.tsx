"use client";

import type { HistoryEntry } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { History } from "lucide-react";

function fmt(iso: string) {
  return new Date(iso).toLocaleTimeString("en-IN", { hour12: false });
}

export function HistoryTable({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <div id="history-table" className="glass rounded-xl p-5 flex flex-col items-center gap-2 text-muted-foreground text-center">
        <History size={28} className="opacity-30" />
        <p className="text-sm">Request history appears here</p>
      </div>
    );
  }

  return (
    <div id="history-table" className="glass rounded-xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-border/40 flex items-center gap-2">
        <History size={13} className="text-muted-foreground" />
        <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">History</span>
        <Badge variant="outline" className="ml-auto text-xs">{entries.length}</Badge>
      </div>
      <ScrollArea className="max-h-64">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/30">
              <th className="px-3 py-2 text-left text-muted-foreground font-medium">Time</th>
              <th className="px-3 py-2 text-left text-muted-foreground font-medium">Query</th>
              <th className="px-3 py-2 text-left text-muted-foreground font-medium">Node</th>
              <th className="px-3 py-2 text-right text-muted-foreground font-medium">Latency</th>
              <th className="px-3 py-2 text-center text-muted-foreground font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr
                key={e.request_id}
                className="border-b border-border/20 hover:bg-white/[0.03] transition-colors"
              >
                <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">{fmt(e.timestamp)}</td>
                <td className="px-3 py-2 max-w-[180px] truncate">{e.query}</td>
                <td className="px-3 py-2 font-mono text-primary whitespace-nowrap">{e.selected_node}</td>
                <td className="px-3 py-2 text-right font-mono whitespace-nowrap">
                  {e.latency_ms > 0 ? `${e.latency_ms.toFixed(0)} ms` : "—"}
                </td>
                <td className="px-3 py-2 text-center">
                  {e.status === "success" ? (
                    <Badge className="text-[10px] bg-green-500/20 text-green-300 border-green-500/30">OK</Badge>
                  ) : (
                    <Badge className="text-[10px] bg-red-500/20 text-red-300 border-red-500/30">ERR</Badge>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollArea>
    </div>
  );
}
