"use client";

import { useState, useRef, useEffect } from "react";
import { Plus, ArrowUp, Loader2, X, FileText } from "lucide-react";

interface Props {
  onSend: (query: string, inputType: string, attachedFile: File | null) => void;
  loading: boolean;
}


export function ChatComposer({ onSend, loading }: Props) {
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Manage object URL memory safely
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    if (file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
      return () => {
        URL.revokeObjectURL(url);
      };
    } else {
      setPreviewUrl(null);
    }
  }, [file]);

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
    // reset input so selecting the same file again works
    e.target.value = "";
  }

  function handleRemoveFile() {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handleSubmit(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim() && !file) return;
    if (loading) return;

    onSend(query.trim(), "auto", file);
    setQuery("");
    setFile(null);


    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function handleInput(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setQuery(e.target.value);
    // Auto-grow textarea up to 180px
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }

  const canSubmit = (query.trim().length > 0 || file !== null) && !loading;

  return (
    <div className="w-full bg-background rounded-2xl border border-border shadow-xs focus-within:border-foreground/30 transition-all flex flex-col p-1.5">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        className="hidden"
        accept="image/*,.pdf,.txt,.py,.js,.json,.md"
      />

      {/* Attachment Preview Chip */}
      {file && (
        <div className="flex items-center gap-2 px-3 py-1.5 mb-1 bg-muted/60 rounded-xl text-xs w-fit max-w-[85%] border border-border/60 animate-in fade-in duration-150">
          {previewUrl ? (
            <div className="w-6 h-6 rounded bg-background border border-border overflow-hidden shrink-0">
              <img src={previewUrl} alt="attachment preview" className="w-full h-full object-cover" />
            </div>
          ) : (
            <FileText size={15} className="text-muted-foreground shrink-0" />
          )}
          <span className="truncate text-foreground font-medium text-xs max-w-[200px] sm:max-w-xs">
            {file.name}
          </span>
          <button
            type="button"
            onClick={handleRemoveFile}
            className="p-0.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors ml-1"
            aria-label="Remove attachment"
          >
            <X size={13} />
          </button>
        </div>
      )}

      {/* Input Row */}
      <div className="flex items-end gap-1 px-1">
        {/* Attachment Button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="h-8 w-8 rounded-full flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors shrink-0 mb-0.5"
          aria-label="Attach file or image"
        >
          <Plus size={18} />
        </button>

        {/* Textarea */}
        <textarea
          ref={textareaRef}
          rows={1}
          value={query}
          onChange={handleInput}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder={file ? "Add instructions for the attachment..." : "Ask anything..."}
          className="flex-1 max-h-[180px] min-h-[36px] py-2 px-2 text-[14.5px] leading-relaxed bg-transparent resize-none outline-none text-foreground placeholder:text-muted-foreground/70"
        />

        {/* Send Button */}
        <button
          type="button"
          disabled={!canSubmit}
          onClick={() => handleSubmit()}
          className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 mb-0.5 transition-all ${
            canSubmit
              ? "bg-foreground text-background hover:opacity-90"
              : "bg-muted text-muted-foreground/40 cursor-not-allowed"
          }`}
          aria-label="Send message"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <ArrowUp size={16} />}
        </button>
      </div>
    </div>
  );
}

