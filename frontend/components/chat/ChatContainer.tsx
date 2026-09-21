"use client";

import { useRef, useEffect } from "react";
import { ChatMessage, type MessageData } from "./ChatMessage";
import { Bot } from "lucide-react";

export function ChatContainer({ messages, loading }: { messages: MessageData[]; loading: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  if (messages.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-70 gap-4">
        <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary mb-2">
          <Bot size={24} />
        </div>
        <h2 className="text-lg font-semibold text-foreground">Distributed AI Orchestrator</h2>
        <p className="text-sm max-w-sm text-center">
          Ask a question to see how it routes across the 5-node inference mesh.
        </p>
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
