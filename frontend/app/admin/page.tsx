"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import useSWR from "swr";

import {
  fetchNodes,
  addNode,
  probeNode,
  enableNode,
  disableNode,
  deleteNode,
  syncNodeConfig,
} from "@/lib/api";
import { ArrowLeft, Server, Plus, Trash2, Power, PowerOff, RefreshCw, Settings2 } from "lucide-react";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

type ActionKey = "probe" | "enable" | "disable" | "delete";

export default function AdminPage() {
  const { data, error, mutate } = useSWR("/api/v1/nodes", fetchNodes, {
    refreshInterval: 5000,
  });

  const [newName, setNewName] = useState("");
  const [newEndpoint, setNewEndpoint] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Per-node pending action tracking
  const [pending, setPending] = useState<Record<string, ActionKey | null>>({});
  const [nodeErrors, setNodeErrors] = useState<Record<string, string | null>>({});

  const [syncLoading, setSyncLoading] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const [returnHref, setReturnHref] = useState("/");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const sid = new URLSearchParams(window.location.search).get("session_id");
      if (sid) setReturnHref(`/?session_id=${encodeURIComponent(sid)}`);
    }
  }, []);

  const setNodePending = (nodeId: string, action: ActionKey | null) =>
    setPending((p) => ({ ...p, [nodeId]: action }));
  const setNodeError = (nodeId: string, msg: string | null) =>
    setNodeErrors((e) => ({ ...e, [nodeId]: msg }));

  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddLoading(true);
    setAddError(null);
    try {
      await addNode(newName, newEndpoint);
      setNewName("");
      setNewEndpoint("");
      mutate();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add node.");
    } finally {
      setAddLoading(false);
    }
  };

  const handleAction = useCallback(
    async (nodeId: string, action: ActionKey) => {
      if (pending[nodeId]) return; // already in flight
      setNodePending(nodeId, action);
      setNodeError(nodeId, null);
      try {
        if (action === "probe") await probeNode(nodeId);
        else if (action === "enable") await enableNode(nodeId);
        else if (action === "disable") await disableNode(nodeId);
        else if (action === "delete") await deleteNode(nodeId);
        mutate();
      } catch (err) {
        const msg =
          action === "probe"
            ? "Failed to probe node. It may be unreachable."
            : action === "enable"
            ? "Failed to enable node. Check if it is reachable."
            : action === "disable"
            ? "Failed to disable node."
            : "Failed to remove node.";
        setNodeError(nodeId, msg);
      } finally {
        setNodePending(nodeId, null);
      }
    },
    [pending, mutate]
  );

  const handleDelete = useCallback(
    async (nodeId: string) => {
      if (!confirm("Remove this node? (It will be soft-disabled.)")) return;
      await handleAction(nodeId, "delete");
    },
    [handleAction]
  );

  const handleSyncConfig = async () => {
    setSyncLoading(true);
    setSyncMsg(null);
    try {
      const res = await syncNodeConfig() as { active_nodes?: number };
      setSyncMsg(`Config synced — ${res.active_nodes ?? "?"} active nodes.`);
      mutate();
    } catch {
      setSyncMsg("Sync failed.");
    } finally {
      setSyncLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      {/* Top Console Bar */}
      <header className="h-12 border-b border-border bg-background px-4 sm:px-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href={returnHref}
            className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={14} />
            <span>Back to Chat</span>
          </Link>
          <span className="text-border">/</span>
          <span className="text-xs font-semibold text-foreground">Node Management</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleSyncConfig}
            disabled={syncLoading}
            title="Sync .env node config"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-md transition-colors text-xs flex items-center gap-1 disabled:opacity-50"
          >
            <Settings2 size={14} />
            <span className="hidden sm:inline text-[11px]">{syncLoading ? "Syncing…" : "Sync Config"}</span>
          </button>
          <ThemeToggle />
        </div>
      </header>

      <main className="p-4 sm:p-8 max-w-5xl mx-auto w-full flex flex-col gap-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight mb-1">Inference Nodes</h1>
          <p className="text-muted-foreground text-xs">
            Manage worker nodes in the distributed mesh. Add, probe, toggle, and configure endpoints.
          </p>
          {syncMsg && (
            <p className="mt-2 text-xs text-muted-foreground">{syncMsg}</p>
          )}
        </div>

        {/* Add Node Card */}
        <div className="bg-card border border-border rounded-xl p-4 sm:p-5 shadow-2xs">
          <h2 className="text-sm font-semibold mb-3">Add Worker Node</h2>
          <form onSubmit={handleAddNode} className="flex flex-col sm:flex-row gap-3 items-end">
            <div className="w-full sm:flex-1">
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                Node Identifier / Name
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 outline-none focus:border-foreground/40"
                placeholder="e.g. WORKER-MAC-M2"
                required
              />
            </div>
            <div className="w-full sm:flex-1">
              <label className="block text-[11px] font-medium text-muted-foreground mb-1">
                HTTP Endpoint
              </label>
              <input
                type="url"
                value={newEndpoint}
                onChange={(e) => setNewEndpoint(e.target.value)}
                className="w-full bg-background border border-border rounded-md px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 outline-none focus:border-foreground/40"
                placeholder="http://192.168.1.100:1234"
                required
              />
            </div>
            <button
              type="submit"
              disabled={addLoading}
              className="w-full sm:w-auto bg-foreground text-background hover:opacity-90 h-[34px] px-3.5 py-1.5 rounded-md flex items-center justify-center gap-1.5 text-xs font-medium transition-opacity shrink-0 disabled:opacity-50"
            >
              <Plus size={14} /> {addLoading ? "Adding…" : "Add Node"}
            </button>
          </form>
          {addError && (
            <p className="mt-2 text-xs text-rose-500">{addError}</p>
          )}
        </div>

        {/* Registered Nodes */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Registered Nodes</h2>
            {data && (
              <span className="text-xs text-muted-foreground font-mono">
                {data.nodes.filter((n: any) => n.status === "ONLINE").length}/{data.nodes.length} online
              </span>
            )}
          </div>

          {error && (
            <div className="p-4 text-xs text-rose-500 bg-rose-500/10 border border-rose-500/20 rounded-lg">
              Failed to connect to Orchestrator API.
            </div>
          )}

          {!data && !error && (
            <div className="p-8 text-center text-xs text-muted-foreground">
              Loading node status…
            </div>
          )}

          {data && data.nodes.length === 0 ? (
            <div className="text-center py-10 bg-muted/30 rounded-xl border border-dashed border-border text-muted-foreground text-xs">
              No worker nodes registered.
            </div>
          ) : (
            data && (
              <div className="flex flex-col gap-2">
                {data.nodes.map((node: any) => {
                  const isOnline = node.status === "ONLINE";
                  const act = pending[node.node_id];
                  const busy = Boolean(act);
                  const nodeErr = nodeErrors[node.node_id];

                  return (
                    <div
                      key={node.node_id}
                      className={`bg-card border border-border rounded-lg p-4 transition-colors ${!node.enabled ? "opacity-50" : ""}`}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`w-2 h-2 rounded-full shrink-0 ${isOnline ? "bg-emerald-500" : "bg-rose-500"}`}
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-semibold text-foreground">
                                {node.name || node.node_id}
                              </span>
                              <span className="font-mono text-[11px] text-muted-foreground">
                                ({node.node_id})
                              </span>
                              {!node.enabled && (
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                                  Disabled
                                </span>
                              )}
                            </div>
                            <div className="text-[11px] font-mono text-muted-foreground mt-0.5">
                              {node.endpoint}
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 self-end sm:self-center">
                          <button
                            onClick={() => handleAction(node.node_id, "probe")}
                            disabled={busy}
                            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted/60 rounded-md transition-colors text-xs flex items-center gap-1 disabled:opacity-40"
                            title="Probe Node"
                          >
                            <RefreshCw size={13} className={act === "probe" ? "animate-spin" : ""} />
                            <span className="text-[11px] hidden sm:inline">
                              {act === "probe" ? "Probing…" : "Probe"}
                            </span>
                          </button>

                          {node.enabled ? (
                            <button
                              onClick={() => handleAction(node.node_id, "disable")}
                              disabled={busy}
                              className="p-1.5 text-muted-foreground hover:text-amber-500 hover:bg-amber-500/10 rounded-md transition-colors text-xs flex items-center gap-1 disabled:opacity-40"
                              title="Disable Node"
                            >
                              <PowerOff size={13} />
                              <span className="text-[11px] hidden sm:inline">
                                {act === "disable" ? "Disabling…" : "Disable"}
                              </span>
                            </button>
                          ) : (
                            <button
                              onClick={() => handleAction(node.node_id, "enable")}
                              disabled={busy}
                              className="p-1.5 text-muted-foreground hover:text-emerald-500 hover:bg-emerald-500/10 rounded-md transition-colors text-xs flex items-center gap-1 disabled:opacity-40"
                              title="Enable Node"
                            >
                              <Power size={13} />
                              <span className="text-[11px] hidden sm:inline">
                                {act === "enable" ? "Enabling…" : "Enable"}
                              </span>
                            </button>
                          )}

                          <button
                            onClick={() => handleDelete(node.node_id)}
                            disabled={busy}
                            className="p-1.5 text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 rounded-md transition-colors text-xs flex items-center gap-1 disabled:opacity-40"
                            title="Remove Node"
                          >
                            <Trash2 size={13} />
                            <span className="text-[11px] hidden sm:inline">
                              {act === "delete" ? "Removing…" : "Remove"}
                            </span>
                          </button>
                        </div>
                      </div>

                      {nodeErr && (
                        <p className="text-[11px] text-rose-500 mb-2">{nodeErr}</p>
                      )}

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs pt-3 border-t border-border/50">
                        <div>
                          <span className="block text-[10px] text-muted-foreground uppercase tracking-wider">
                            Status
                          </span>
                          <span className="font-medium text-foreground">{node.status}</span>
                        </div>
                        <div>
                          <span className="block text-[10px] text-muted-foreground uppercase tracking-wider">
                            Latency
                          </span>
                          <span className="font-mono text-foreground">
                            {node.latency_ms !== null ? `${node.latency_ms} ms` : "—"}
                          </span>
                        </div>
                        <div className="col-span-2 sm:col-span-2">
                          <span className="block text-[10px] text-muted-foreground uppercase tracking-wider">
                            Loaded Models
                          </span>
                          <span
                            className="font-mono text-[11px] text-foreground truncate block"
                            title={node.models?.join(", ")}
                          >
                            {node.models?.length > 0
                              ? node.models.join(", ")
                              : node.model_loaded || "—"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
      </main>
    </div>
  );
}
