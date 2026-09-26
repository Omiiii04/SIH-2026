"use client";

import { useRef, useEffect } from "react";
import { ChatMessage, type MessageData } from "./ChatMessage";

const EXAMPLE_PROMPTS = [
  { text: "Explain how transformers work", type: "text" },
  { text: "Analyze code for race conditions", type: "code" },
  { text: "Solve this logic problem step-by-step", type: "reasoning" },
  { text: "Search my stored memory for past context", type: "retrieval" },
];

export function ChatContainer({
  messages,
  loading,
  onExampleClick
}: {
  messages: MessageData[];
  loading: boolean;
  onExampleClick?: (query: string, type: string) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  if (messages.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-4 max-w-2xl mx-auto w-full pb-16">
        <h2 className="text-2xl sm:text-3xl font-semibold text-foreground tracking-tight mb-8 text-center">
          What can I help you with?
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full">
          {EXAMPLE_PROMPTS.map((ex) => (
            <button
              key={ex.text}
              onClick={() => onExampleClick?.(ex.text, ex.type)}
              className="p-3.5 rounded-xl border border-border/80 bg-background hover:bg-muted/60 transition-colors text-left text-xs sm:text-sm text-foreground/80 hover:text-foreground font-medium shadow-2xs"
            >
              {ex.text}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col max-w-3xl mx-auto w-full px-4 sm:px-6 py-6 pb-36">
      {messages.map((m) => (
        <ChatMessage key={m.id} msg={m} />
      ))}
      
      {loading && (
        <div className="flex items-center gap-1.5 py-4">
          <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:-0.3s]" />
          <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:-0.15s]" />
          <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce" />
        </div>
      )}
      
      <div ref={bottomRef} className="h-4" />
    </div>
  );
}

