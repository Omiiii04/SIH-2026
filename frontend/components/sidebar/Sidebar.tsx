"use client";

import { useState } from "react";
import { Search, Settings, Plus, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { HistoryEntry } from "@/lib/types";
import { ChatHistory } from "./ChatHistory";
import { SemanticSearch } from "./SemanticSearch";
import { SettingsPanel } from "./SettingsPanel";

export function Sidebar({ history, onNewChat }: { history: HistoryEntry[]; onNewChat: () => void }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="flex flex-col h-full relative">
      <div className="p-4 flex flex-col gap-2">
        <Button onClick={onNewChat} variant="default" className="w-full justify-start gap-2 h-10 shadow-sm" aria-label="New chat">
          <Plus size={16} /> New chat
        </Button>
        <div className="flex gap-2">
          <Button onClick={() => setSearchOpen(true)} variant="outline" className="flex-1 justify-start gap-2 h-9 text-muted-foreground" aria-label="Semantic Search">
            <Search size={14} /> Search memory...
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <ChatHistory entries={history} />
      </div>

      <div className="p-3 border-t border-border mt-auto flex flex-col gap-1">
        <a href="/admin">
          <Button variant="ghost" className="w-full justify-start gap-2 text-muted-foreground">
            <Server size={16} /> Nodes Admin
          </Button>
        </a>
        <Button onClick={() => setSettingsOpen(true)} variant="ghost" className="w-full justify-start gap-2 text-muted-foreground">
          <Settings size={16} /> Settings
        </Button>
      </div>

      {searchOpen && <SemanticSearch onClose={() => setSearchOpen(false)} />}
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
