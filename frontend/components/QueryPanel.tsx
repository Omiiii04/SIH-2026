"use client";

import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { submitQuery } from "@/lib/api";
import type { QueryResponse, NodeFailureResponse, HistoryEntry } from "@/lib/types";
import { Send, ImagePlus, X, Loader2 } from "lucide-react";

const INPUT_TYPES = [
  { value: "text",      label: "Text" },
  { value: "code",      label: "Code" },
  { value: "reasoning", label: "Reasoning" },
  { value: "retrieval", label: "Retrieval" },
  { value: "image",     label: "Image" },
] as const;

interface Props {
  onResult: (r: QueryResponse | NodeFailureResponse, ok: boolean) => void;
  onHistoryEntry: (e: HistoryEntry) => void;
  sessionId: string;
}

export function QueryPanel({ onResult, onHistoryEntry, sessionId }: Props) {
  const [query, setQuery]           = useState("");
  const [inputType, setInputType]   = useState("text");
  const [loading, setLoading]       = useState(false);
  const [imageFile, setImageFile]   = useState<File | null>(null);
  const fileRef                     = useRef<HTMLInputElement>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || loading) return;

    // If image uploaded, force input_type to image
    const effectiveType = imageFile ? "image" : inputType;

    setLoading(true);
    try {
      const { ok, data } = await submitQuery({
        user_id: "dashboard-user",
        query: query.trim(),
        input_type: effectiveType,
        session_id: sessionId,
      });
      onResult(data, ok);

      const qr = data as QueryResponse;
      onHistoryEntry({
        request_id: qr.request_id ?? crypto.randomUUID(),
        timestamp: new Date().toISOString(),
        query: query.trim(),
        selected_node: qr.selected_node ?? (data as NodeFailureResponse).selected_node ?? "—",
        latency_ms: qr.latency_ms ?? (data as NodeFailureResponse).latency_ms ?? 0,
        status: ok ? "success" : "error",
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form
      id="query-panel"
      onSubmit={handleSubmit}
      className="glass rounded-xl p-4 flex flex-col gap-3"
    >
      {/* Input type selector */}
      <div className="flex flex-wrap gap-1.5">
        {INPUT_TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            id={`input-type-${t.value}`}
            onClick={() => setInputType(t.value)}
            className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
              inputType === t.value
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Image attachment */}
      {imageFile ? (
        <div className="flex items-center gap-2 bg-primary/10 border border-primary/30 rounded-lg px-3 py-2 text-xs text-primary">
          <ImagePlus size={13} />
          <span className="truncate flex-1">{imageFile.name}</span>
          <button type="button" onClick={() => setImageFile(null)}>
            <X size={13} className="hover:text-red-400" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors w-fit"
        >
          <ImagePlus size={13} /> Attach image (optional)
        </button>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) { setImageFile(f); setInputType("image"); }
        }}
      />

      {/* Query textarea */}
      <Textarea
        id="query-input"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Enter your query… (Shift+Enter for new line)"
        className="min-h-[100px] resize-none bg-transparent border-border/50 text-sm"
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e as never); }
        }}
      />

      {/* Submit */}
      <Button
        id="submit-query"
        type="submit"
        disabled={!query.trim() || loading}
        className="self-end gap-2"
      >
        {loading ? (
          <><Loader2 size={14} className="animate-spin" /> Routing…</>
        ) : (
          <><Send size={14} /> Submit Query</>
        )}
      </Button>
    </form>
  );
}
