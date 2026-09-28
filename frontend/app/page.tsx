"use client";

import { useState, useCallback, useEffect } from "react";
import { submitQuery, fetchSessions, fetchSessionMessages, deleteSession } from "@/lib/api";
import type { QueryResponse, NodeFailureResponse, SessionEntry, AttachmentMeta } from "@/lib/types";

import { AppShell } from "@/components/layout/AppShell";
import { Sidebar } from "@/components/sidebar/Sidebar";
import { ChatContainer } from "@/components/chat/ChatContainer";
import { ChatComposer } from "@/components/chat/ChatComposer";
import { type MessageData } from "@/components/chat/ChatMessage";

export default function DashboardPage() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [messages, setMessages] = useState<MessageData[]>([]);
  const [loading, setLoading] = useState(false);
  const [isClient, setIsClient] = useState(false);

  // Load sessions from backend
  const loadSessions = useCallback(async (selectSessionId?: string | null) => {
    try {
      const list = await fetchSessions("dashboard-user");
      setSessions(list);

      // Determine which session to activate
      const toSelect = selectSessionId !== undefined 
        ? selectSessionId 
        : (typeof window !== "undefined" ? sessionStorage.getItem("active_session_id") : null);

      if (toSelect && list.some(s => s.id === toSelect)) {
        setActiveSessionId(toSelect);
        const msgs = await fetchSessionMessages(toSelect, "dashboard-user");
        setMessages(msgs);
      } else if (!toSelect && selectSessionId === undefined && list.length > 0) {
        // Default to most recent session on fresh initial visit only
        setActiveSessionId(list[0].id);
        if (typeof window !== "undefined") sessionStorage.setItem("active_session_id", list[0].id);
        const msgs = await fetchSessionMessages(list[0].id, "dashboard-user");
        setMessages(msgs);
      } else {
        // Stay in new chat state (e.g. after deletion or explicit new chat)
        setActiveSessionId(null);
        setMessages([]);
        if (typeof window !== "undefined") sessionStorage.removeItem("active_session_id");
      }
    } catch (err) {
      console.error("Failed to load sessions:", err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    setIsClient(true);
    let targetSid: string | null = null;
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      targetSid = params.get("session_id");
    }
    loadSessions(targetSid);
  }, [loadSessions]);

  // Load messages when selecting a history item
  const handleSelectSession = useCallback(async (session: SessionEntry) => {
    setActiveSessionId(session.id);
    if (typeof window !== "undefined") {
      sessionStorage.setItem("active_session_id", session.id);
    }
    setLoading(true);
    try {
      const msgs = await fetchSessionMessages(session.id, "dashboard-user");
      setMessages(msgs);
    } catch (err) {
      console.error("Failed to load messages for session:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle + New chat
  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    if (typeof window !== "undefined") {
      sessionStorage.removeItem("active_session_id");
    }
  }, []);

  // Delete single session
  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId, "dashboard-user");
      const wasActive = activeSessionId === sessionId;
      if (wasActive) {
        handleNewChat();
      }
      await loadSessions(wasActive ? null : activeSessionId);
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  }, [activeSessionId, handleNewChat, loadSessions]);

  // Clear all sessions for user
  const handleClearAllHistory = useCallback(async () => {
    handleNewChat();
    await loadSessions(null);
  }, [handleNewChat, loadSessions]);

  const handleSend = useCallback(async (query: string, inputType: string, attachedFile: File | null) => {
    const effectiveQuery = query.trim() ||
      (attachedFile ? `📎 ${attachedFile.name}` : "[File attached]");
    const effectiveInputType = inputType || "auto";

    // Determine current or new session ID
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      currentSessionId = `sess-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
      setActiveSessionId(currentSessionId);
      if (typeof window !== "undefined") {
        sessionStorage.setItem("active_session_id", currentSessionId);
      }
    }

    // Build attachment metadata for user message UI
    let attachmentMeta: AttachmentMeta | undefined = undefined;
    if (attachedFile) {
      const isImg = attachedFile.type.startsWith("image/");
      const isPdf = attachedFile.name.toLowerCase().endsWith(".pdf") || attachedFile.type === "application/pdf";
      const isCode = [".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".css", ".sql", ".sh", ".rs", ".go"].some(
        ext => attachedFile.name.toLowerCase().endsWith(ext)
      );
      const kind = isImg ? "image" : isPdf ? "pdf" : isCode ? "code" : "text";

      attachmentMeta = {
        filename: attachedFile.name,
        mime_type: attachedFile.type || "application/octet-stream",
        size: attachedFile.size,
        kind: kind,
        preview_url: isImg ? URL.createObjectURL(attachedFile) : undefined,
      };
    }

    const userMsgId = crypto.randomUUID();
    setMessages(prev => [...prev, {
      id: userMsgId,
      role: "user",
      content: query.trim() || "[File attached]",
      attachments: attachmentMeta ? [attachmentMeta] : [],
    }]);
    setLoading(true);

    try {
      const result = await submitQuery({
        user_id: "dashboard-user",
        query: effectiveQuery,
        input_type: effectiveInputType,
        session_id: currentSessionId,
        file: attachedFile,
      });

      const assistantMsgId = crypto.randomUUID();
      const content = result.ok
        ? (result.data as QueryResponse).response
        : (result.errorMessage || (result.data as NodeFailureResponse)?.detail || "I encountered an error processing your request.");

      setMessages(prev => [...prev, {
        id: assistantMsgId,
        role: "assistant",
        content: content,
        result: result.data,
        ok: result.ok,
      }]);

      // Refresh sidebar sessions from PostgreSQL so title and updated_at appear
      const updatedList = await fetchSessions("dashboard-user");
      setSessions(updatedList);

    } catch (err: any) {
      console.error(err);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `Error: ${err?.message || "An unexpected error occurred."}`,
      }]);
    } finally {
      setLoading(false);
    }
  }, [activeSessionId]);

  // Active conversation title for Header
  const activeSession = sessions.find(s => s.id === activeSessionId);
  const conversationTitle = activeSession?.title 
    || (messages.length > 0 
      ? (messages[0].content.length > 28 ? `${messages[0].content.slice(0, 28)}…` : messages[0].content)
      : "SIH Assistant");

  if (!isClient) return <div className="min-h-screen bg-background" />;

  return (
    <AppShell
      title={conversationTitle}
      activeSessionId={activeSessionId}
      sidebar={
        <Sidebar 
          sessions={sessions}
          activeSessionId={activeSessionId}
          onNewChat={handleNewChat} 
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          onClearHistory={handleClearAllHistory}
        />
      }
    >
      <div className="flex flex-col h-full relative">
        <ChatContainer 
          messages={messages} 
          loading={loading} 
          onExampleClick={(query, type) => handleSend(query, type, null)} 
        />
        
        {/* Composer fixed at bottom center of chat area */}
        <div className="sticky bottom-0 left-0 right-0 px-4 sm:px-6 pb-4 pt-4 bg-gradient-to-t from-background via-background/90 to-transparent mt-auto">
          <div className="max-w-3xl mx-auto w-full">
            <ChatComposer onSend={handleSend} loading={loading} />
            <p className="text-center text-[11px] text-muted-foreground/60 mt-2 select-none">
              AI can make mistakes. Verify important info.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}


