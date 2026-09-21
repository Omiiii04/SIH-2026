import { Activity, Cpu, Wifi, WifiOff } from "lucide-react";
import useSWR from "swr";
import { fetchHealth } from "@/lib/api";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

function OrchestratorStatus() {
  const { data, error } = useSWR("/health", fetchHealth, { refreshInterval: 15_000 });
  const ok = !error && data?.status === "ok";
  return (
    <div className={`flex items-center gap-1.5 text-xs ${ok ? "text-green-500 dark:text-green-400" : "text-red-500 dark:text-red-400"}`}>
      {ok ? <Wifi size={14} /> : <WifiOff size={14} />}
      <span className="hidden sm:inline">{ok ? "Service Online" : "Service Offline"}</span>
    </div>
  );
}

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex h-12 items-center px-4 md:px-6 gap-4">
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
          <OrchestratorStatus />
          <Activity size={14} className="text-muted-foreground animate-pulse-online hidden sm:block" />
          <div className="w-px h-4 bg-border hidden sm:block" />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
