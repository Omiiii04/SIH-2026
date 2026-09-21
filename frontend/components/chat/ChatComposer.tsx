"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, ImagePlus, X, Loader2, Plus, Type, Code, Brain, Database } from "lucide-react";

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
  const [imageFile, setImageFile]   = useState<File | null>(null);
  const [menuOpen, setMenuOpen]     = useState(false);
  const fileRef                     = useRef<HTMLInputElement>(null);

  function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim() || loading) return;
    onSend(query.trim(), inputType, imageFile);
    setQuery("");
    setImageFile(null);
    setInputType("text");
    setMenuOpen(false);
  }

  const selectedType = INPUT_TYPES.find(t => t.value === inputType) || INPUT_TYPES[0];

  return (
    <div className="relative bg-card border border-border/60 rounded-2xl p-2 shadow-sm focus-within:border-primary/50 focus-within:ring-1 focus-within:ring-primary/20 transition-all flex flex-col gap-2">
      {/* Attached image preview */}
      {imageFile && (
        <div className="flex items-center gap-2 bg-primary/10 border border-primary/20 rounded-lg px-3 py-1.5 text-xs text-primary w-fit ml-12">
          <ImagePlus size={13} />
          <span className="truncate max-w-[200px]">{imageFile.name}</span>
          <button type="button" onClick={() => setImageFile(null)}>
            <X size={13} className="hover:text-red-400" />
          </button>
        </div>
      )}

      <div className="flex items-end gap-2">
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
              <div className="h-px bg-border my-1" />
              <button
                type="button"
                onClick={() => { fileRef.current?.click(); setMenuOpen(false); }}
                className="flex items-center gap-2 px-3 py-2 rounded-md text-sm hover:bg-muted text-foreground transition-colors"
              >
                <ImagePlus size={14} />
                Upload Image
              </button>
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
          disabled={!query.trim() || loading}
          onClick={() => handleSubmit()}
          className="h-9 w-9 rounded-xl bg-primary text-primary-foreground shrink-0 shadow-sm"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </Button>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) { setImageFile(f); setInputType("image"); }
          // Reset value to allow selecting same file again
          e.target.value = '';
        }}
      />
    </div>
  );
}
