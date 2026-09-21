import type { HistoryEntry } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare, Clock } from "lucide-react";

export function ChatHistory({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-muted-foreground opacity-60">
        <MessageSquare size={20} className="mb-2" />
        <p className="text-xs">No chat history</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
        Today
      </div>
      <ScrollArea className="flex-1">
        <div className="flex flex-col px-2 gap-1 pb-4">
          {entries.map((e) => (
            <button
              key={e.request_id}
              className="flex flex-col items-start p-2 text-left rounded-md hover:bg-muted/50 transition-colors"
            >
              <span className="text-sm truncate w-full font-medium text-foreground/90">
                {e.query}
              </span>
              <span className="text-[10px] text-muted-foreground flex items-center gap-1 mt-1">
                <Clock size={10} />
                {new Date(e.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
              </span>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
