"use client";

import type { SessionEntry } from "@/lib/types";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageSquare, Trash2 } from "lucide-react";

interface ChatHistoryProps {
  sessions: SessionEntry[];
  selectedSessionId?: string | null;
  onSelectSession: (session: SessionEntry) => void;
  onDeleteSession?: (sessionId: string) => void;
}

function categorizeDate(timestamp: string): "Today" | "Yesterday" | "Previous 7 Days" | "Older" {
  try {
    const d = new Date(timestamp);
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const entryTime = d.getTime();
    
    if (entryTime >= startOfToday) return "Today";
    if (entryTime >= startOfToday - 86400000) return "Yesterday";
    if (entryTime >= startOfToday - 7 * 86400000) return "Previous 7 Days";
    return "Older";
  } catch {
    return "Older";
  }
}

export function ChatHistory({
  sessions = [],
  selectedSessionId,
  onSelectSession,
  onDeleteSession,
}: ChatHistoryProps) {
  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-28 text-muted-foreground/60 text-center px-4 select-none">
        <MessageSquare size={16} className="mb-1.5 opacity-40" />
        <p className="text-xs">No chat history yet</p>
      </div>
    );
  }

  const grouped: Record<string, SessionEntry[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 Days": [],
    Older: [],
  };

  for (const session of sessions) {
    const cat = categorizeDate(session.updated_at || session.created_at);
    grouped[cat].push(session);
  }

  const order: (keyof typeof grouped)[] = ["Today", "Yesterday", "Previous 7 Days", "Older"];

  return (
    <ScrollArea className="h-full">
      <div className="flex flex-col gap-3 py-2 px-1">
        {order.map((cat) => {
          const items = grouped[cat];
          if (!items || items.length === 0) return null;

          return (
            <div key={cat} className="flex flex-col">
              <span className="px-2 py-1 text-[11px] font-medium text-muted-foreground/70">
                {cat}
              </span>
              <div className="flex flex-col gap-0.5">
                {items.map((session) => {
                  const isSelected = selectedSessionId === session.id;
                  return (
                    <div
                      key={session.id}
                      onClick={() => onSelectSession(session)}
                      className={`group flex items-center justify-between w-full px-2.5 py-1.5 rounded-md text-xs transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-muted text-foreground font-medium"
                          : "text-foreground/80 hover:bg-muted/60 hover:text-foreground"
                      }`}
                    >
                      <span className="truncate flex-1" title={session.title}>
                        {session.title}
                      </span>
                      {onDeleteSession && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteSession(session.id);
                          }}
                          title="Delete conversation"
                          aria-label="Delete conversation"
                          className="opacity-0 group-hover:opacity-100 p-1 hover:text-rose-500 rounded transition-all shrink-0 ml-1 text-muted-foreground"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
}


