"use client";

import { ReactNode } from "react";
import { Header } from "./Header";

interface AppShellProps {
  sidebar: ReactNode;
  footer: ReactNode;
  children: ReactNode; // Main chat area
}

export function AppShell({ sidebar, footer, children }: AppShellProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <Header />
      
      <div className="flex flex-1 overflow-hidden relative">
        {/* Sidebar - Hidden on small mobile by default, handled later via drawer if needed, but for now fixed width on lg, smaller on md */}
        <aside className="hidden md:flex w-64 lg:w-72 flex-col border-r border-border bg-card/30">
          {sidebar}
        </aside>

        {/* Main Chat Area */}
        <main className="flex-1 flex flex-col relative overflow-hidden bg-background">
          <div className="flex-1 overflow-y-auto">
            {children}
          </div>
          
          {/* Node Status Footer */}
          <div className="border-t border-border bg-card/30">
            {footer}
          </div>
        </main>
      </div>
    </div>
  );
}
