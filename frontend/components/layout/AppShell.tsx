"use client";

import { ReactNode, useState, useEffect } from "react";
import { Header } from "./Header";
import { X } from "lucide-react";

interface AppShellProps {
  sidebar: ReactNode | ((close: () => void) => ReactNode);
  footer?: ReactNode;
  title?: string;
  activeSessionId?: string | null;
  children: ReactNode;
}

export function AppShell({ sidebar, footer, title, activeSessionId, children }: AppShellProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(true);

  // Automatically close mobile menu when active conversation changes
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [activeSessionId]);

  const renderSidebar = typeof sidebar === "function" ? sidebar(() => setMobileMenuOpen(false)) : sidebar;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      <Header 
        title={title}
        activeSessionId={activeSessionId}
        onMenuClick={() => setMobileMenuOpen(true)} 
        onToggleSidebar={() => setDesktopSidebarOpen(!desktopSidebarOpen)}
      />
      
      <div className="flex flex-1 overflow-hidden relative">
        {/* Mobile Sidebar Overlay */}
        {mobileMenuOpen && (
          <div className="md:hidden fixed inset-0 z-50 flex">
            <div 
              className="absolute inset-0 bg-black/40 backdrop-blur-xs transition-opacity" 
              onClick={() => setMobileMenuOpen(false)} 
            />
            <div className="relative w-[280px] h-full bg-sidebar flex flex-col border-r border-sidebar-border shadow-xl animate-in slide-in-from-left duration-200">
              <button 
                onClick={() => setMobileMenuOpen(false)} 
                className="absolute right-3.5 top-3.5 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 z-10 transition-colors"
                aria-label="Close menu"
              >
                <X size={18} />
              </button>
              {renderSidebar}
            </div>
          </div>
        )}

        {/* Desktop Sidebar */}
        <aside 
          className={`hidden md:flex flex-col border-r border-border bg-sidebar shrink-0 transition-all duration-200 ${
            desktopSidebarOpen ? 'w-64 lg:w-68' : 'w-0 overflow-hidden border-r-0'
          }`}
        >
          <div className="w-64 lg:w-68 h-full flex flex-col">
            {renderSidebar}
          </div>
        </aside>


        {/* Main Content Area */}
        <main className="flex-1 flex flex-col relative overflow-hidden bg-background">
          <div className="flex-1 overflow-y-auto">
            {children}
          </div>
          
          {footer && (
            <div className="border-t border-border bg-card/40 shrink-0">
              {footer}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

