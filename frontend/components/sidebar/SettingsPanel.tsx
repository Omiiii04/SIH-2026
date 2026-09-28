"use client";

import { useState, useRef, useEffect } from "react";
import { Settings, X, Server, LayoutPanelLeft, Palette, Network, Cpu, Brain, MessageSquare, Info, Trash2, Loader2 } from "lucide-react";
import { useTheme } from "next-themes";
import useSWR from "swr";
import { fetchHealth, fetchNodes, clearAllSessions } from "@/lib/api";

const CATEGORIES = [
  { id: "general", label: "General", icon: LayoutPanelLeft },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "orchestration", label: "Orchestration", icon: Network },
  { id: "nodes", label: "Nodes", icon: Cpu },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "about", label: "About", icon: Info },
] as const;

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  onClearHistory?: () => void;
}

export function SettingsPanel({ open, onClose, onClearHistory }: SettingsPanelProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { setTheme, theme } = useTheme();
  const [activeCategory, setActiveCategory] = useState<typeof CATEGORIES[number]["id"]>("general");
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  const { data: health, error: healthError } = useSWR("/health", fetchHealth, { refreshInterval: 15_000 });
  const { data: nodesData } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 15_000 });

  const ok = !healthError && health?.status === "ok";
  const nodes = nodesData?.nodes || [];
  const onlineCount = nodes.filter(n => n.status === "ONLINE").length;

  async function handleClearHistory() {
    setClearing(true);
    try {
      await clearAllSessions("dashboard-user");
      setConfirmClear(false);
      onClearHistory?.();
      onClose();
    } catch (err) {
      console.error("Failed to clear chat history:", err);
    } finally {
      setClearing(false);
    }
  }

  useEffect(() => {
    if (open) {
      dialogRef.current?.showModal();
    } else {
      dialogRef.current?.close();
    }
  }, [open]);

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      className="backdrop:bg-black/50 bg-transparent m-auto p-0 rounded-xl shadow-xl overflow-hidden open:animate-in open:fade-in-0 open:zoom-in-95 duration-150"
    >
      <div className="w-[740px] h-[520px] max-w-[95vw] max-h-[85vh] bg-card border border-border flex flex-col sm:flex-row text-foreground">
        
        {/* Mobile Header */}
        <div className="sm:hidden flex items-center justify-between p-3.5 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Settings size={16} />
            <h2 className="text-sm font-semibold">Settings</h2>
          </div>
          <button onClick={onClose} className="p-1 text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {/* Sidebar */}
        <div className="w-full sm:w-52 border-r border-border bg-muted/30 flex flex-col sm:h-full overflow-x-auto sm:overflow-y-auto shrink-0">
          <div className="hidden sm:flex items-center justify-between p-4 pb-2 shrink-0">
            <h2 className="text-sm font-semibold tracking-tight">Settings</h2>
          </div>
          
          <div className="flex sm:flex-col gap-0.5 p-2">
            {CATEGORIES.map(c => (
              <button
                key={c.id}
                onClick={() => setActiveCategory(c.id)}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors text-left ${
                  activeCategory === c.id 
                    ? "bg-muted text-foreground font-semibold" 
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                <c.icon size={15} />
                <span>{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col relative overflow-hidden bg-background">
          <div className="hidden sm:block absolute top-3.5 right-3.5 z-10">
            <button 
              onClick={onClose} 
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
          
          <div className="p-6 flex-1 overflow-y-auto">
            <div className="max-w-md flex flex-col gap-6">
              
              <div className="border-b border-border pb-3">
                <h3 className="text-base font-semibold tracking-tight">
                  {CATEGORIES.find(c => c.id === activeCategory)?.label}
                </h3>
              </div>

              {activeCategory === "general" && (
                <div className="flex flex-col gap-4 text-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-foreground">Language</p>
                      <p className="text-muted-foreground text-[11px]">Interface display language</p>
                    </div>
                    <select className="bg-muted text-foreground text-xs rounded-md px-2.5 py-1.5 border border-border focus:ring-1 focus:ring-ring outline-none">
                      <option>System Default</option>
                      <option>English</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-border/50">
                    <div>
                      <p className="font-medium text-foreground">Clear confirmation</p>
                      <p className="text-muted-foreground text-[11px]">Confirm before starting new chats</p>
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">Enabled</span>
                  </div>
                </div>
              )}

              {activeCategory === "appearance" && (
                <div className="flex flex-col gap-4 text-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-foreground">Theme</p>
                      <p className="text-muted-foreground text-[11px]">Select your color theme</p>
                    </div>
                    <div className="flex bg-muted rounded-md p-0.5 border border-border">
                      {["system", "light", "dark"].map((t) => (
                        <button
                          key={t}
                          onClick={() => setTheme(t)}
                          className={`px-2.5 py-1 text-xs rounded capitalize transition-colors ${
                            theme === t 
                              ? "bg-background shadow-2xs text-foreground font-medium" 
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {activeCategory === "orchestration" && (
                <div className="flex flex-col gap-3 text-xs">
                  <div className="p-3 bg-muted/40 rounded-lg border border-border flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">Automated Task Classification</span>
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">Active</span>
                    </div>
                    <p className="text-muted-foreground text-[11px]">
                      Orchestrator automatically determines task intent (Code, Reasoning, QA, Vision) and routes queries to optimal nodes.
                    </p>
                  </div>
                  <div className="p-3 bg-muted/40 rounded-lg border border-border flex flex-col gap-1">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-foreground">Dynamic Fallback Routing</span>
                      <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">Active</span>
                    </div>
                    <p className="text-muted-foreground text-[11px]">
                      Queries automatically re-route to healthy fallback nodes if the primary node is offline or degraded.
                    </p>
                  </div>
                </div>
              )}

              {activeCategory === "nodes" && (
                <div className="flex flex-col gap-3 text-xs">
                  <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border">
                    <div className="flex items-center gap-2">
                      <Server size={15} className="text-muted-foreground" />
                      <div>
                        <p className="font-medium text-foreground">Orchestrator API</p>
                        <p className="text-[11px] text-muted-foreground">{ok ? "Online & Healthy" : "Offline / Unreachable"}</p>
                      </div>
                    </div>
                    <span className={`w-2 h-2 rounded-full ${ok ? "bg-emerald-500" : "bg-rose-500"}`} />
                  </div>
                  
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-[11px] font-medium text-muted-foreground">Inference Nodes</span>
                    <span className="text-[11px] text-muted-foreground">{onlineCount}/{nodes.length} Online</span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    {nodes.map(n => (
                      <div key={n.node_id} className="flex items-center justify-between p-2.5 border border-border/70 rounded-md bg-background">
                        <div className="flex items-center gap-2">
                          <span className={`w-1.5 h-1.5 rounded-full ${n.status === 'ONLINE' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                          <span className="font-mono text-xs text-foreground">{n.node_id}</span>
                        </div>
                        <span className="text-[11px] text-muted-foreground font-mono">{n.model_loaded || n.status}</span>
                      </div>
                    ))}
                    {nodes.length === 0 && (
                      <p className="text-xs text-muted-foreground text-center py-4">No nodes registered.</p>
                    )}
                  </div>
                </div>
              )}

              {activeCategory === "memory" && (
                <div className="flex flex-col gap-4 text-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-foreground">Semantic Vector Store</p>
                      <p className="text-[11px] text-muted-foreground">Persist past chat interactions in ChromaDB</p>
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">Enabled</span>
                  </div>
                </div>
              )}

              {activeCategory === "chat" && (
                <div className="flex flex-col gap-4 text-xs">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-foreground">Routing telemetry details</p>
                      <p className="text-[11px] text-muted-foreground">Always collapsed by default under responses</p>
                    </div>
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-muted text-foreground border border-border">Collapsed</span>
                  </div>

                  <div className="pt-3 border-t border-border flex flex-col gap-2">
                    <div>
                      <p className="font-medium text-foreground">Conversation Management</p>
                      <p className="text-[11px] text-muted-foreground">Permanently delete all stored chat sessions from the database</p>
                    </div>
                    {!confirmClear ? (
                      <button
                        type="button"
                        onClick={() => setConfirmClear(true)}
                        className="text-xs text-rose-500 hover:text-rose-600 font-medium px-3 py-1.5 bg-rose-500/10 rounded-md transition-colors w-fit flex items-center gap-1.5"
                      >
                        <Trash2 size={13} />
                        <span>Clear chat history</span>
                      </button>
                    ) : (
                      <div className="p-3 rounded-lg border border-rose-500/30 bg-rose-500/5 flex flex-col gap-2">
                        <p className="text-xs text-foreground font-medium">Delete all chat history for this user? This cannot be undone.</p>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={clearing}
                            onClick={handleClearHistory}
                            className="px-3 py-1 text-xs font-medium rounded-md bg-rose-500 text-white hover:bg-rose-600 transition-colors flex items-center gap-1.5"
                          >
                            {clearing ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                            <span>Yes, clear all history</span>
                          </button>
                          <button
                            type="button"
                            disabled={clearing}
                            onClick={() => setConfirmClear(false)}
                            className="px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeCategory === "about" && (
                <div className="flex flex-col items-center justify-center py-6 gap-2 text-center text-xs">
                  <h4 className="text-sm font-semibold text-foreground">Distributed AI Orchestrator</h4>
                  <p className="text-muted-foreground text-[11px]">SIH 2026 • Intelligent Multi-Node Inference System</p>
                  <p className="text-muted-foreground text-[11px] max-w-xs mt-2">
                    Minimal conversational frontend with autonomous task classification, capability-based routing, and local memory search.
                  </p>
                </div>
              )}

            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
}

