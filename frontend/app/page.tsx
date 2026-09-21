"use client";

import { useState, useCallback, useId, useEffect } from "react";
import { submitQuery } from "@/lib/api";
import type { QueryResponse, NodeFailureResponse, HistoryEntry } from "@/lib/types";

import { AppShell } from "@/components/layout/AppShell";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatContainer } from "@/components/chat/ChatContainer";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { NodeStatusBar } from "@/components/nodes/NodeStatusBar";
import { type MessageData } from "@/components/chat/ChatMessage";

export default function DashboardPage() {
  const sessionId = useId().replace(/:/g, "");
  
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [isClient, setIsClient] = useState(false);

  // Load history from localStorage on mount
  useEffect(() => {
    setIsClient(true);
    const savedMsg = localStorage.getItem("chat_messages");
    const savedHist = localStorage.getItem("chat_history");
    if (savedMsg) {
      try { setMessages(JSON.parse(savedMsg)); } catch {}
    }
    if (savedHist) {
      try { setHistory(JSON.parse(savedHist)); } catch {}
    }
  }, []);

  // Save to localStorage when state changes
  useEffect(() => {
    if (isClient) {
      localStorage.setItem("chat_messages", JSON.stringify(messages));
      localStorage.setItem("chat_history", JSON.stringify(history));
    }
  }, [messages, history, isClient]);

  const handleSend = useCallback(async (query: string, inputType: string, imageFile: File | null) => {
    const userMsgId = crypto.randomUUID();
    setMessages(prev => [...prev, { id: userMsgId, role: "user", content: query }]);
    setLoading(true);

    try {
      const { ok, data } = await submitQuery({
        user_id: "dashboard-user",
        query: query,
        input_type: inputType,
        session_id: sessionId,
      });

      const qr = data as QueryResponse;
      const fail = data as NodeFailureResponse;
      
      const assistantMsgId = crypto.randomUUID();
      const content = ok ? qr.response : "I encountered an error processing your request.";

      setMessages(prev => [...prev, {
        id: assistantMsgId,
        role: "assistant",
        content: content,
        result: data,
        ok: ok
      }]);

      setHistory(prev => [{
        request_id: qr.request_id ?? crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        query: query,
        selected_node: qr.selected_node ?? fail.selected_node ?? "—",
        latency_ms: qr.latency_ms ?? fail.latency_ms ?? 0,
        status: (ok ? "success" : "error") as "success" | "error",
      }, ...prev].slice(0, 50));

    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Network error communicating with the Orchestrator."
      }]);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  const handleNewChat = useCallback(() => {
    setMessages([]);
  }, []);

  // Avoid hydration mismatch by rendering a simple fallback before client load
  if (!isClient) return <div className="min-h-screen bg-background" />;

  return (
    <AppShell
      sidebar={<Sidebar history={history} onNewChat={handleNewChat} />}
      footer={<NodeStatusBar />}
    >
      <div className="flex flex-col h-full relative">
        <ChatContainer 
          messages={messages} 
          loading={loading} 
          onExampleClick={(query, type) => handleSend(query, type, null)} 
        />
        
        {/* Composer fixed at bottom of chat area */}
        <div className="sticky bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-background via-background to-transparent pt-10 mt-auto">
          <div className="max-w-3xl mx-auto w-full">
            <ChatComposer onSend={handleSend} loading={loading} />
            <p className="text-center text-[10px] text-muted-foreground mt-2">
              Distributed AI Orchestrator can make mistakes. Verify routing details in the Thinking panel.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
