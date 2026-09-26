"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";
import { fetchNodes } from "@/lib/api";
import { Server, Activity, Plus, Trash2, Power, PowerOff, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export default function AdminPage() {
  const { data, error } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 5000 });
  
  const [newName, setNewName] = useState("");
  const [newEndpoint, setNewEndpoint] = useState("");
  const [loading, setLoading] = useState(false);

  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch("/api/v1/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newName, endpoint: newEndpoint, priority: 1 })
      });
      if (res.ok) {
        setNewName("");
        setNewEndpoint("");
        mutate("/api/v1/nodes");
      } else {
        alert(await res.text());
      }
    } catch (err) {
      alert("Failed to add node.");
    }
    setLoading(false);
  };

  const handleAction = async (nodeId: string, action: string) => {
    try {
      const res = await fetch(`/api/v1/nodes/${nodeId}/${action}`, { method: "POST" });
      if (res.ok) {
        mutate("/api/v1/nodes");
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleDelete = async (nodeId: string) => {
    if (!confirm("Are you sure you want to remove this node?")) return;
    try {
      const res = await fetch(`/api/v1/nodes/${nodeId}`, { method: "DELETE" });
      if (res.ok) {
        mutate("/api/v1/nodes");
      }
    } catch (err) {
      console.error(err);
    }
  };

  if (error) return <div className="p-8 text-red-500">Failed to load nodes</div>;
  if (!data) return <div className="p-8 text-muted-foreground">Loading...</div>;

  return (
    <div className="p-8 max-w-6xl mx-auto flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2 mb-2">
          <Server size={24} /> Node Management
        </h1>
        <p className="text-muted-foreground text-sm">
          Dynamic LAN Node Registry. Add, remove, and probe worker nodes.
        </p>
      </div>

      <div className="bg-card border rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold mb-4">Add New Node</h2>
        <form onSubmit={handleAddNode} className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs text-muted-foreground mb-1 uppercase tracking-wider">Node Name</label>
            <input 
              type="text" 
              value={newName} 
              onChange={e => setNewName(e.target.value)}
              className="w-full bg-background border rounded-md px-3 py-2 text-sm"
              placeholder="e.g. My Mac Studio"
              required 
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs text-muted-foreground mb-1 uppercase tracking-wider">Endpoint</label>
            <input 
              type="url" 
              value={newEndpoint} 
              onChange={e => setNewEndpoint(e.target.value)}
              className="w-full bg-background border rounded-md px-3 py-2 text-sm"
              placeholder="http://192.168.1.100:1234"
              required 
            />
          </div>
          <button 
            type="submit" 
            disabled={loading}
            className="bg-primary text-primary-foreground hover:bg-primary/90 h-9 px-4 py-2 rounded-md flex items-center gap-2 text-sm font-medium transition-colors"
          >
            <Plus size={16} /> Add Node
          </button>
        </form>
      </div>

      <div className="grid gap-4">
        <h2 className="text-lg font-semibold">Registered Nodes</h2>
        {data.nodes.length === 0 ? (
          <div className="text-center py-12 bg-muted/50 rounded-xl border border-dashed border-border/50 text-muted-foreground">
            No nodes registered yet.
          </div>
        ) : (
          data.nodes.map((node: any) => {
            const isOnline = node.status === "ONLINE";
            return (
              <div key={node.node_id} className={`bg-card border rounded-xl p-5 shadow-sm transition-colors ${!node.enabled ? 'opacity-50 grayscale' : ''}`}>
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <div className="flex items-center gap-3 mb-1">
                      <h3 className="text-base font-semibold">{node.name || node.node_id}</h3>
                      <Badge variant="outline" className={`text-xs ${isOnline ? "bg-green-500/10 text-green-500 border-green-500/30" : "bg-red-500/10 text-red-500 border-red-500/30"}`}>
                        {node.status}
                      </Badge>
                      {!node.enabled && (
                        <Badge variant="secondary" className="text-xs">DISABLED</Badge>
                      )}
                    </div>
                    <div className="text-sm font-mono text-muted-foreground">{node.node_id} • {node.endpoint}</div>
                  </div>
                  
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={() => handleAction(node.node_id, 'probe')}
                      className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
                      title="Probe Node"
                    >
                      <RefreshCw size={16} />
                    </button>
                    {node.enabled ? (
                      <button 
                        onClick={() => handleAction(node.node_id, 'disable')}
                        className="p-2 text-muted-foreground hover:text-orange-500 hover:bg-orange-500/10 rounded-md transition-colors"
                        title="Disable"
                      >
                        <PowerOff size={16} />
                      </button>
                    ) : (
                      <button 
                        onClick={() => handleAction(node.node_id, 'enable')}
                        className="p-2 text-muted-foreground hover:text-green-500 hover:bg-green-500/10 rounded-md transition-colors"
                        title="Enable"
                      >
                        <Power size={16} />
                      </button>
                    )}
                    <button 
                      onClick={() => handleDelete(node.node_id)}
                      className="p-2 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded-md transition-colors"
                      title="Remove"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm mt-4 pt-4 border-t border-border/50">
                  <div>
                    <span className="block text-xs text-muted-foreground mb-1 uppercase tracking-wider">Latency</span>
                    <span className="font-mono">{node.latency_ms !== null ? `${node.latency_ms} ms` : '—'}</span>
                  </div>
                  <div>
                    <span className="block text-xs text-muted-foreground mb-1 uppercase tracking-wider">Models Loaded</span>
                    <span className="font-mono truncate block" title={node.models?.join(", ")}>
                      {node.models?.length > 0 ? node.models.join(", ") : '—'}
                    </span>
                  </div>
                  <div className="col-span-2">
                    <span className="block text-xs text-muted-foreground mb-1 uppercase tracking-wider">Discovered Capabilities</span>
                    <div className="flex flex-wrap gap-1">
                      {node.capabilities?.map((cap: string) => (
                        <Badge key={cap} variant="secondary" className="font-mono text-[10px] px-1.5 py-0.5">{cap}</Badge>
                      )) || <span className="text-muted-foreground text-xs font-mono">None</span>}
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
