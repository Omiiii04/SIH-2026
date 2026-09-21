"use client";

import { User, Sparkles } from "lucide-react";
import type { QueryResponse, NodeFailureResponse } from "@/lib/types";
import { ThinkingPanel } from "./ThinkingPanel";

export interface MessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: QueryResponse | NodeFailureResponse;
  ok?: boolean;
}

export function ChatMessage({ msg }: { msg: MessageData }) {
  const isUser = msg.role === "user";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"} mb-6 group`}>
      <div className={`flex max-w-[85%] md:max-w-[75%] gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
        {/* Avatar */}
        <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser ? "bg-primary/20 text-primary border border-primary/30" : "bg-card border border-border text-foreground shadow-sm"}`}>
          {isUser ? <User size={14} /> : <Sparkles size={14} className="text-primary" />}
        </div>

        {/* Content Bubble */}
        <div className="flex flex-col gap-1 min-w-0">
          <div className={`text-sm ${isUser ? "bg-primary text-primary-foreground" : "bg-card border border-border text-foreground shadow-sm"} rounded-2xl px-4 py-2.5 whitespace-pre-wrap break-words leading-relaxed`}>
            {msg.content}
          </div>

          {/* Thinking / Infrastructure Layer (only for assistant) */}
          {!isUser && msg.result && (
            <ThinkingPanel result={msg.result} ok={msg.ok ?? false} />
          )}
        </div>
      </div>
    </div>
  );
}
