"use client";

import { useState, useRef, useEffect } from "react";
import { Settings, X, Server, Database, CheckCircle2, XCircle, LayoutPanelLeft, Palette, Network, Cpu, Brain, MessageSquare, Info } from "lucide-react";
import { useTheme } from "next-themes";
import useSWR from "swr";
import { fetchHealth, fetchNodes } from "@/lib/api";

const CATEGORIES = [
  { id: "general", label: "General", icon: LayoutPanelLeft },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "orchestration", label: "Orchestration", icon: Network },
  { id: "nodes", label: "Nodes", icon: Cpu },
  { id: "memory", label: "Memory", icon: Brain },
  { id: "chat", label: "Chat", icon: MessageSquare },
  { id: "about", label: "About", icon: Info },
] as const;

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { setTheme, theme } = useTheme();
  const [activeCategory, setActiveCategory] = useState<typeof CATEGORIES[number]["id"]>("general");

  const { data: health, error: healthError } = useSWR("/health", fetchHealth, { refreshInterval: 15_000 });
  const { data: nodesData } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 15_000 });

  const ok = !healthError && health?.status === "ok";
  const nodes = nodesData?.nodes || [];
  const onlineCount = nodes.filter(n => n.status === "ONLINE").length;

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
      className="backdrop:bg-black/50 bg-transparent m-auto p-0 rounded-xl shadow-2xl overflow-hidden open:animate-in open:fade-in-0 open:zoom-in-95"
    >
      <div className="w-[800px] h-[600px] max-w-[95vw] max-h-[90vh] bg-card border border-border flex flex-col sm:flex-row text-foreground">
        
        {/* Mobile Header (Hidden on Desktop) */}
        <div className="sm:hidden flex items-center justify-between p-4 border-b border-border shrink-0">
          <div className="flex items-center gap-2">
            <Settings size={18} />
            <h2 className="text-base font-semibold">Settings</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1">
            <X size={18} />
          </button>
        </div>

        {/* Sidebar */}
        <div className="w-full sm:w-56 border-r border-border bg-muted/20 flex flex-col sm:h-full overflow-x-auto sm:overflow-y-auto hide-scrollbar shrink-0">
          <div className="hidden sm:flex items-center justify-between p-4 mb-2 shrink-0">
            <h2 className="text-base font-semibold px-2">Settings</h2>
          </div>
          
          <div className="flex sm:flex-col gap-1 p-3 sm:p-2">
            {CATEGORIES.map(c => (
              <button
                key={c.id}
                onClick={() => setActiveCategory(c.id)}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap sm:whitespace-normal ${activeCategory === c.id ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
              >
                <c.icon size={16} />
                {c.label}
              </button>
            ))}
          </div>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col relative overflow-hidden bg-background">
          <div className="hidden sm:block absolute top-4 right-4 z-10">
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1 bg-background/50 backdrop-blur rounded-md">
              <X size={18} />
            </button>
          </div>
          
          <div className="p-6 sm:p-8 flex-1 overflow-y-auto">
            <div className="max-w-xl mx-auto flex flex-col gap-8">
              
              {/* Category Header */}
              <div className="border-b border-border pb-4 mb-2">
                <h2 className="text-xl font-semibold tracking-tight">
                  {CATEGORIES.find(c => c.id === activeCategory)?.label}
                </h2>
              </div>

              {activeCategory === "general" && (
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium">Language</label>
                    <select className="bg-muted text-sm rounded-md px-3 py-2 border-0 ring-1 ring-border focus:ring-primary w-fit">
                      <option>Auto</option>
                      <option>English</option>
                    </select>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Confirm before clearing</span>
                      <span className="text-xs text-muted-foreground">Ask for confirmation when clearing history.</span>
                    </div>
                    <span className="text-xs font-medium bg-primary text-primary-foreground px-2.5 py-1 rounded-full">ON</span>
                  </div>
                </div>
              )}

              {activeCategory === "appearance" && (
                <div className="flex flex-col gap-6">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Theme</span>
                      <span className="text-xs text-muted-foreground">Select your interface color scheme.</span>
                    </div>
                    <div className="flex bg-muted rounded-md p-1 border border-border/50">
                      {["system", "light", "dark"].map((t) => (
                        <button
                          key={t}
                          onClick={() => setTheme(t)}
                          className={`px-3 py-1.5 text-xs rounded-sm capitalize transition-all ${theme === t ? "bg-background shadow-sm text-foreground font-medium" : "text-muted-foreground hover:text-foreground"}`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Compact Mode</span>
                      <span className="text-xs text-muted-foreground">Reduce padding and margins.</span>
                    </div>
                    <span className="text-xs font-medium bg-muted text-muted-foreground px-2.5 py-1 rounded-full">OFF</span>
                  </div>
                </div>
              )}

              {activeCategory === "orchestration" && (
                <div className="flex flex-col gap-6">
                  <div className="flex flex-col gap-3 p-4 bg-muted/30 rounded-xl border border-border/50">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Automatic Routing</span>
                      <span className="text-xs font-medium bg-primary text-primary-foreground px-2.5 py-1 rounded-full">ON</span>
                    </div>
                    <p className="text-xs text-muted-foreground">Automatically route requests to the most appropriate available node based on classification.</p>
                  </div>
                  <div className="flex flex-col gap-3 p-4 bg-muted/30 rounded-xl border border-border/50">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">Fault Tolerance</span>
                      <span className="text-xs font-medium bg-primary text-primary-foreground px-2.5 py-1 rounded-full">ON</span>
                    </div>
                    <p className="text-xs text-muted-foreground">Automatically fall back when a node fails.</p>
                  </div>
                </div>
              )}

              {activeCategory === "nodes" && (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center justify-between p-4 bg-muted/50 rounded-xl border border-border">
                    <div className="flex items-center gap-3">
                      <Server size={18} className="text-primary" />
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold">Orchestrator Connection</span>
                        <span className="text-xs text-muted-foreground">{ok ? "Healthy" : "Unreachable"}</span>
                      </div>
                    </div>
                    {ok ? (
                      <CheckCircle2 size={18} className="text-green-500" />
                    ) : (
                      <XCircle size={18} className="text-red-500" />
                    )}
                  </div>
                  
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mt-2">Node Mesh ({onlineCount}/{nodes.length} Online)</h3>
                  <div className="flex flex-col gap-2">
                    {nodes.map(n => (
                      <div key={n.node_id} className="flex items-center justify-between p-3 border border-border/50 rounded-lg bg-card">
                        <div className="flex items-center gap-3">
                          <span className={`w-2 h-2 rounded-full ${n.status === 'ONLINE' ? 'bg-green-500' : 'bg-red-500'}`} />
                          <div className="flex flex-col">
                            <span className="text-sm font-medium">{n.node_id}</span>
                            <span className="text-xs text-muted-foreground font-mono">{n.model_loaded || 'No model'}</span>
                          </div>
                        </div>
                        <span className="text-xs text-muted-foreground">{n.status}</span>
                      </div>
                    ))}
                    {nodes.length === 0 && (
                      <div className="text-sm text-muted-foreground text-center py-4">No nodes detected.</div>
                    )}
                  </div>
                </div>
              )}

              {activeCategory === "memory" && (
                <div className="flex flex-col gap-6">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Semantic Memory</span>
                      <span className="text-xs text-muted-foreground">Use ChromaDB semantic memory.</span>
                    </div>
                    <span className="text-xs font-medium bg-primary text-primary-foreground px-2.5 py-1 rounded-full">ON</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Search automatically</span>
                      <span className="text-xs text-muted-foreground">Inject context automatically on relevant queries.</span>
                    </div>
                    <span className="text-xs font-medium bg-primary text-primary-foreground px-2.5 py-1 rounded-full">ON</span>
                  </div>
                  <div className="mt-4 pt-4 border-t border-border/50">
                    <button className="text-sm text-red-500 hover:text-red-600 font-medium px-4 py-2 bg-red-500/10 rounded-lg transition-colors w-fit">
                      Clear conversation memory
                    </button>
                  </div>
                </div>
              )}

              {activeCategory === "chat" && (
                <div className="flex flex-col gap-6">
                  <div className="flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium">Automatically Expand Thinking</span>
                      <span className="text-xs text-muted-foreground">Always show routing details on new messages.</span>
                    </div>
                    <span className="text-xs font-medium bg-muted text-muted-foreground px-2.5 py-1 rounded-full">OFF</span>
                  </div>
                </div>
              )}

              {activeCategory === "about" && (
                <div className="flex flex-col items-center justify-center py-8 gap-4 text-center">
                  <div className="w-16 h-16 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-sm">
                    <Network size={32} />
                  </div>
                  <div className="flex flex-col gap-1">
                    <h3 className="text-lg font-semibold">Distributed AI Orchestrator</h3>
                    <p className="text-sm text-muted-foreground">Version 1.0.0</p>
                  </div>
                  <p className="text-sm text-muted-foreground max-w-xs mt-2">
                    SIH 2026 Project. Distributed inference and intelligent model routing across multiple nodes.
                  </p>
                  <div className="flex gap-4 mt-4">
                    <span className="text-xs bg-muted px-2 py-1 rounded-md text-muted-foreground">Made by Omiiii04</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </dialog>
  );
}
