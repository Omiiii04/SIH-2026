"use client";

import { useRef, useEffect } from "react";
import { Settings, X } from "lucide-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const { setTheme, theme } = useTheme();

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
      <div className="w-[400px] max-w-[90vw] bg-card border border-border flex flex-col text-foreground">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Settings size={16} />
            <h2 className="text-sm font-semibold">Settings</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        <div className="p-4 flex flex-col gap-6">
          {/* GENERAL */}
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">General</h3>
            <div className="flex items-center justify-between">
              <span className="text-sm">Theme</span>
              <div className="flex bg-muted rounded-md p-0.5">
                {["system", "light", "dark"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t)}
                    className={`px-3 py-1 text-xs rounded-sm capitalize transition-colors ${theme === t ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {/* SYSTEM */}
          <section className="flex flex-col gap-2">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Orchestration</h3>
            <div className="flex items-center justify-between">
              <span className="text-sm">Automatic Routing</span>
              <span className="text-xs text-primary font-medium bg-primary/10 px-2 py-0.5 rounded-md">Enabled</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Semantic Memory</span>
              <span className="text-xs text-primary font-medium bg-primary/10 px-2 py-0.5 rounded-md">Enabled</span>
            </div>
          </section>
        </div>
      </div>
    </dialog>
  );
}
