"use client";

import { useRef, useEffect } from "react";
import { ChatMessage, type MessageData } from "./ChatMessage";
import { Bot } from "lucide-react";

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
      <div className="h-full flex flex-col items-center justify-center text-muted-foreground gap-8 px-4">
        <div className="flex flex-col items-center gap-3">
          {/* <div className="w-14 h-14 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-2 shadow-sm animate-in fade-in zoom-in duration-500">
            <Bot size={28} />
          </div> */}
          <h2 className="text-2xl font-semibold text-foreground tracking-tight">What can I help you with?</h2>
          <p className="text-sm max-w-md text-center opacity-70">
            Route your queries automatically across the 5-node inference mesh.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl mt-4">
          {[
            { q: "Explain transformers", label: "General QA", type: "text" },
            { q: "Analyze this code for race conditions", label: "Code", type: "code" },
            { q: "Think step-by-step to solve this logic puzzle", label: "Reasoning", type: "reasoning" },
            { q: "Search my memory for previous context", label: "Retrieval", type: "retrieval" },
          ].map(ex => (
            <button
              key={ex.q}
              onClick={() => onExampleClick?.(ex.q, ex.type)}
              className="flex flex-col gap-1 items-start text-left p-4 rounded-xl border border-border/50 bg-card hover:bg-muted/50 hover:border-border transition-all"
            >
              <span className="text-[10px] font-semibold tracking-wider uppercase text-primary/80">{ex.label}</span>
              <span className="text-sm text-foreground">"{ex.q}"</span>
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-4 md:p-6 lg:p-8 max-w-4xl mx-auto w-full pb-32">
      {messages.map((m) => (
        <ChatMessage key={m.id} msg={m} />
      ))}
      {loading && (
        <div className="flex justify-start mb-6">
          <div className="flex max-w-[85%] md:max-w-[75%] gap-3 flex-row">
            <div className="shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-card border border-border text-foreground shadow-sm">
              <Bot size={14} className="animate-pulse" />
            </div>
            <div className="flex flex-col justify-center">
              <div className="flex gap-1.5 items-center bg-card border border-border rounded-2xl px-4 py-3 h-[40px]">
                <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.3s]" />
                <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]" />
                <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce" />
              </div>
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} className="h-1" />
    </div>
  );
}
