"use client";

import { ReactNode, useState } from "react";
import { Header } from "./Header";
import { X } from "lucide-react";

interface AppShellProps {
  sidebar: ReactNode;
  footer: ReactNode;
  children: ReactNode; // Main chat area
}

export function AppShell({ sidebar, footer, children }: AppShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <Header 
        onMenuClick={() => setMobileMenuOpen(true)} 
        onToggleSidebar={() => setDesktopSidebarOpen(!desktopSidebarOpen)}
      />
      
      <div className="flex flex-1 overflow-hidden relative">
        {/* Mobile Sidebar Overlay */}
        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 flex">
            <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} />
            <div className="relative w-[280px] h-full bg-card shadow-2xl flex flex-col border-r border-border animate-in slide-in-from-left">
              <button 
                onClick={() => setMobileMenuOpen(false)} 
                className="absolute right-4 top-4 text-muted-foreground hover:text-foreground z-10"
              >
                <X size={18} />
              </button>
              {sidebar}
            </div>
          </div>
        )}

        {/* Desktop Sidebar */}
        <aside className={`hidden md:flex flex-col border-r border-border bg-card/30 transition-all duration-300 ${desktopSidebarOpen ? 'w-64 lg:w-72' : 'w-0 overflow-hidden border-r-0'}`}>
          <div className="w-64 lg:w-72 h-full flex flex-col">
            {sidebar}
          </div>
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
