import type { HistoryEntry } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare, Clock } from "lucide-react";

function categorizeDate(timestamp: string) {
  const d = new Date(timestamp);
  const now = new Date();
  const diffTime = Math.abs(now.getTime() - d.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
  
  if (diffDays <= 1 && now.getDate() === d.getDate()) return "Today";
  if (diffDays <= 2 && now.getDate() !== d.getDate()) return "Yesterday";
  return "Previous 7 Days";
}

export function ChatHistory({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-muted-foreground opacity-60">
        <MessageSquare size={20} className="mb-2" />
        <p className="text-xs">No chat history</p>
      </div>
    );
  }

  const grouped = entries.reduce((acc, entry) => {
    const cat = categorizeDate(entry.timestamp);
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(entry);
    return acc;
  }, {} as Record<string, HistoryEntry[]>);

  const order = ["Today", "Yesterday", "Previous 7 Days"];

  return (
    <div className="flex flex-col h-full">
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-4 pb-4 px-2 pt-2">
          {order.map((cat) => {
            const items = grouped[cat];
            if (!items?.length) return null;
            return (
              <div key={cat} className="flex flex-col">
                <div className="px-2 py-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
                  {cat}
                </div>
                <div className="flex flex-col gap-0.5">
                  {items.map((e) => (
                    <button
                      key={e.request_id}
                      className="flex flex-col items-start p-2 text-left rounded-md hover:bg-muted/50 transition-colors focus:bg-muted/50 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/20"
                    >
                      <span className="text-[13px] truncate w-full font-medium text-foreground/90 leading-tight">
                        {e.query}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
