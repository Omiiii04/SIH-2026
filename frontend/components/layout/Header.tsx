import { Activity, Cpu, Wifi, WifiOff, Menu, PanelLeft } from "lucide-react";
import useSWR from "swr";
import { fetchHealth, fetchNodes } from "@/lib/api";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

export function Header({ onMenuClick, onToggleSidebar }: { onMenuClick?: () => void, onToggleSidebar?: () => void }) {
  const { data: health, error: healthError } = useSWR("/health", fetchHealth, { refreshInterval: 15_000 });
  const { data: nodesData } = useSWR("/api/v1/nodes", fetchNodes, { refreshInterval: 15_000 });
  
  const ok = !healthError && health?.status === "ok";
  const nodes = nodesData?.nodes || [];
  const onlineCount = nodes.filter(n => n.status === "ONLINE").length;

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-12 items-center px-4 md:px-6 gap-4">
        {onMenuClick && (
          <button onClick={onMenuClick} className="md:hidden text-muted-foreground hover:text-foreground" aria-label="Open Mobile Menu">
            <Menu size={18} />
          </button>
        )}
        {onToggleSidebar && (
          <button onClick={onToggleSidebar} className="hidden md:flex text-muted-foreground hover:text-foreground" aria-label="Toggle Sidebar">
            <PanelLeft size={18} />
          </button>
        )}
        
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-primary/10 border border-primary/20 flex items-center justify-center animate-glow">
            <Cpu size={14} className="text-primary" />
          </div>
          <div className="hidden sm:flex flex-col justify-center">
            <h1 className="text-sm font-semibold tracking-tight leading-tight">Distributed AI</h1>
            <p className="text-[10px] text-muted-foreground leading-tight">5-Node Inference Mesh</p>
          </div>
        </div>
        
        <div className="ml-auto flex items-center gap-3">
          <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-500 dark:text-green-400" : "text-red-500 dark:text-red-400"}`}>
            {ok ? <Wifi size={14} /> : <WifiOff size={14} />}
            <span className="hidden sm:inline">
              {ok ? `Orchestrator Online` : "Orchestrator Offline"}
            </span>
          </div>
          
          <div className="hidden sm:block text-[10px] text-muted-foreground border-l border-border pl-3">
            {nodes.length > 0 ? `${onlineCount}/${nodes.length} Nodes` : "Fetching nodes..."}
          </div>

          <Activity size={14} className="text-muted-foreground animate-pulse-online hidden md:block ml-2" />
          <div className="w-px h-4 bg-border hidden sm:block" />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
