"use client";

import Link from "next/link";
import { Menu, PanelLeft, Server } from "lucide-react";
import useSWR from "swr";
import { fetchHealth } from "@/lib/api";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

interface HeaderProps {
  title?: string;
  onMenuClick?: () => void;
  onToggleSidebar?: () => void;
}

export function Header({ title = "SIH Assistant", onMenuClick, onToggleSidebar }: HeaderProps) {
  const { data: health, error: healthError } = useSWR("/health", fetchHealth, { refreshInterval: 30_000 });
  const isOnline = !healthError && health?.status === "ok";

  return (
    <header className="sticky top-0 z-30 h-12 border-b border-border bg-background/80 backdrop-blur-md px-3 sm:px-4 flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            aria-label="Open sidebar"
          >
            <Menu size={18} />
          </button>
        )}
        {onToggleSidebar && (
          <button
            onClick={onToggleSidebar}
            className="hidden md:flex p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
            aria-label="Toggle sidebar"
          >
            <PanelLeft size={18} />
          </button>
        )}

        <div className="flex items-center gap-2 ml-1">
          <span className="text-sm font-medium tracking-tight text-foreground truncate max-w-[200px] sm:max-w-xs">
            {title}
          </span>
          <span
            title={isOnline ? "System Online" : "System Reconnecting"}
            className={`w-1.5 h-1.5 rounded-full ${isOnline ? "bg-emerald-500" : "bg-amber-500/70"}`}
          />
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Link
          href="/admin"
          className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors flex items-center gap-1.5 text-xs font-medium"
          title="Nodes Management"
        >
          <Server size={15} />
          <span className="hidden sm:inline">Admin</span>
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}

