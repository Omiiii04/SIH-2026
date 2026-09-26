"use client";

import { useState } from "react";
import { Search, Settings, Plus } from "lucide-react";
import type { SessionEntry } from "@/lib/types";
import { ChatHistory } from "./ChatHistory";
import { SemanticSearch } from "./SemanticSearch";
import { SettingsPanel } from "./SettingsPanel";

interface SidebarProps {
  sessions: SessionEntry[];
  activeSessionId?: string | null;
  onNewChat: () => void;
  onSelectSession: (session: SessionEntry) => void;
  onDeleteSession?: (sessionId: string) => void;
}

export function Sidebar({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: SidebarProps) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="flex flex-col h-full bg-sidebar select-none">
      {/* Top action: New chat */}
      <div className="p-3 pb-2 flex flex-col gap-2">
        <button
          onClick={onNewChat}
          className="flex items-center justify-between w-full px-3 py-2 text-sm font-medium rounded-lg border border-border/70 bg-background text-foreground hover:bg-muted/70 transition-colors shadow-2xs"
          aria-label="New chat"
        >
          <span className="flex items-center gap-2">
            <Plus size={16} />
            <span>New chat</span>
          </span>
        </button>

        <button
          onClick={() => setSearchOpen(true)}
          className="flex items-center gap-2 w-full px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 rounded-md transition-colors"
          aria-label="Search memory"
        >
          <Search size={14} />
          <span>Search memory...</span>
        </button>
      </div>

      {/* Chat History */}
      <div className="flex-1 overflow-hidden px-1">
        <ChatHistory
          sessions={sessions}
          selectedSessionId={activeSessionId}
          onSelectSession={onSelectSession}
          onDeleteSession={onDeleteSession}
        />
      </div>

      {/* Bottom utilities */}
      <div className="p-2 border-t border-sidebar-border mt-auto flex flex-col gap-0.5">
        <button
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors text-left"
        >
          <Settings size={15} />
          <span>Settings</span>
        </button>
      </div>

      {searchOpen && <SemanticSearch onClose={() => setSearchOpen(false)} />}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}


