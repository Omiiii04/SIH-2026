"use client";

import { useState } from "react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Loader2, Plus, Type, Code, Brain, Database, Paperclip, File as FileIcon, Image as ImageIcon, X } from "lucide-react";

const INPUT_TYPES = [
  { value: "text",      label: "Text",      icon: Type },
  { value: "code",      label: "Code",      icon: Code },
  { value: "reasoning", label: "Reasoning", icon: Brain },
  { value: "retrieval", label: "Retrieval", icon: Database },
] as const;

interface Props {
  onSend: (query: string, inputType: string, imageFile: File | null) => void;
  loading: boolean;
}

export function ChatComposer({ onSend, loading }: Props) {
  const [query, setQuery]           = useState("");
  const [inputType, setInputType]   = useState("text");
  const [menuOpen, setMenuOpen]     = useState(false);
  const [file, setFile]             = useState<File | null>(null);
  const fileInputRef                = useRef<HTMLInputElement>(null);

  function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim() && !file) return;
    if (loading) return;
    
    onSend(query.trim(), inputType, file);
    setQuery("");
    setInputType("text");
    setMenuOpen(false);
    setFile(null);
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
    setMenuOpen(false);
  }

  const selectedType = INPUT_TYPES.find(t => t.value === inputType) || INPUT_TYPES[0];

  return (
    <div className="relative bg-card border border-border/60 rounded-2xl shadow-sm focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all flex flex-col gap-1">
      {file && (
        <div className="flex items-center gap-2 p-2 mx-2 mt-2 bg-muted/50 rounded-lg text-xs border border-border/50 animate-in fade-in zoom-in-95">
          {file.type.startsWith("image/") ? (
            <div className="w-8 h-8 rounded bg-background border border-border flex items-center justify-center overflow-hidden shrink-0">
              <img src={URL.createObjectURL(file)} alt="preview" className="object-cover w-full h-full" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded bg-background border border-border flex items-center justify-center shrink-0">
              <FileIcon size={14} className="text-muted-foreground" />
            </div>
          )}
          <span className="truncate font-medium flex-1">{file.name}</span>
          <button onClick={() => setFile(null)} className="text-muted-foreground hover:text-foreground shrink-0 p-1" aria-label="Remove attachment">
            <X size={14} />
          </button>
        </div>
      )}
      
      <div className="flex items-end gap-2 p-2">
        <input type="file" className="hidden" ref={fileInputRef} onChange={handleFileSelect} />
        
        {/* Plus Menu Button */}
        <div className="relative">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={`h-9 w-9 rounded-xl text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-transform ${menuOpen ? 'rotate-45' : ''}`}
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="Input options"
          >
            <Plus size={18} />
          </Button>

          {/* Popover Menu */}
          {menuOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-48 bg-card border border-border rounded-xl shadow-lg p-1.5 flex flex-col gap-0.5 z-10 animate-in fade-in zoom-in-95 origin-bottom-left">
              <div className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
                Attach
              </div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-muted text-foreground"
              >
                <ImageIcon size={14} /> Upload image
              </button>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-muted text-foreground mb-1"
              >
                <FileIcon size={14} /> Upload file
              </button>
              
              <div className="border-t border-border/50 my-1"></div>
              
              <div className="px-2 py-1.5 text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">
                Input Mode
              </div>
              {INPUT_TYPES.map((t) => (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => { setInputType(t.value); setMenuOpen(false); }}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${inputType === t.value ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted text-foreground'}`}
                >
                  <t.icon size={14} />
                  {t.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Text Input */}
        <div className="flex-1 min-h-[44px] flex flex-col justify-center relative">
          {inputType !== 'text' && !query && (
            <div className="absolute left-3 top-2.5 pointer-events-none flex items-center gap-1.5 text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-md">
               <selectedType.icon size={10} /> {selectedType.label}
            </div>
          )}
          <Textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={inputType !== 'text' ? "" : "Ask anything..."}
            className={`min-h-[44px] max-h-[200px] resize-none bg-transparent border-0 focus-visible:ring-0 p-3 py-2.5 text-sm shadow-none ${inputType !== 'text' && !query ? 'indent-24' : ''}`}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); }
            }}
          />
        </div>

        {/* Send Button */}
        <Button
          type="button"
          size="icon"
          disabled={(!query.trim() && !file) || loading}
          onClick={() => handleSubmit()}
          className="h-9 w-9 rounded-xl bg-primary text-primary-foreground shrink-0 shadow-sm"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </Button>
      </div>
    </div>
  );
}
