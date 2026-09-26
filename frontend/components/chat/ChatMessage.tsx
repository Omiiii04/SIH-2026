"use client";

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

  if (isUser) {
    return (
      <div className="flex w-full justify-end mb-6">
        <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 bg-muted/80 text-foreground text-[14.5px] leading-relaxed whitespace-pre-wrap break-words shadow-2xs">
          {msg.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full mb-8 text-left">
      <div className="text-[15px] leading-relaxed text-foreground whitespace-pre-wrap break-words">
        {msg.content}
      </div>

      {msg.result && (
        <ThinkingPanel result={msg.result} ok={msg.ok ?? false} />
      )}
    </div>
  );
}

