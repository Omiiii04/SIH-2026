"use client";

import { useState, useRef, useCallback } from "react";
import {
  Upload,
  FileText,
  Search,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  X,
} from "lucide-react";
import { uploadRagDocument, queryRagDocuments } from "@/lib/api";
import type { RagUploadResult, RagChunk } from "@/lib/api";

// ── Persisted document list (localStorage) ────────────────────────────────

const STORAGE_KEY = "rag_indexed_docs";

function loadDocs(): RagUploadResult[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveDocs(docs: RagUploadResult[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(docs));
}

// ── Component ──────────────────────────────────────────────────────────────

export function RagDocuments() {
  const [docs, setDocs] = useState<RagUploadResult[]>(loadDocs);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastUploaded, setLastUploaded] = useState<RagUploadResult | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<RagChunk[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [expandedChunk, setExpandedChunk] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Upload ──────────────────────────────────────────────────────────────

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    const file = Array.from(files)[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);
    setLastUploaded(null);

    try {
      const result = await uploadRagDocument(file);
      const updated = [result, ...docs.filter((d) => d.doc_id !== result.doc_id)];
      saveDocs(updated);
      setDocs(updated);
      setLastUploaded(result);
    } catch (err: any) {
      let msg = err?.message || "Upload failed.";
      // Try to parse FastAPI 422 detail
      try {
        const parsed = JSON.parse(msg);
        msg = parsed?.detail || msg;
      } catch {}
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  }, [docs]);

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  // ── Search ──────────────────────────────────────────────────────────────

  async function handleSearch() {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError(null);
    setSearchResults(null);

    try {
      const res = await queryRagDocuments(searchQuery.trim(), 5);
      setSearchResults(res.results);
    } catch (err: any) {
      setSearchError(err?.message || "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  // ── Remove doc from local list ──────────────────────────────────────────
  function removeDoc(doc_id: string) {
    const updated = docs.filter((d) => d.doc_id !== doc_id);
    saveDocs(updated);
    setDocs(updated);
  }

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col gap-5 text-xs">

      {/* ── Upload zone ── */}
      <div>
        <p className="font-medium text-foreground mb-1">Index a Document</p>
        <p className="text-[11px] text-muted-foreground mb-2">
          Upload PDF, TXT, MD, CSV, or code files to index them for RAG retrieval.
        </p>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            cursor-pointer border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center gap-2
            transition-colors select-none
            ${dragging
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50 hover:bg-muted/30"}
          `}
        >
          {uploading ? (
            <Loader2 size={20} className="animate-spin text-muted-foreground" />
          ) : (
            <Upload size={20} className="text-muted-foreground" />
          )}
          <p className="text-[11px] text-muted-foreground text-center">
            {uploading ? "Uploading & indexing…" : "Drop a file here or click to browse"}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.txt,.md,.csv,.tsv,.py,.js,.ts,.jsx,.tsx,.json,.html,.css,.sql,.sh,.yaml,.yml"
            onChange={(e) => e.target.files && handleFiles(e.target.files)}
          />
        </div>

        {/* Success banner */}
        {lastUploaded && !uploading && (
          <div className="mt-2 flex items-start gap-2 p-2.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">{lastUploaded.filename}</p>
              <p className="text-[11px] opacity-80">
                {lastUploaded.chunks} chunks · {lastUploaded.chars.toLocaleString()} chars indexed
              </p>
            </div>
          </div>
        )}

        {/* Error banner */}
        {uploadError && (
          <div className="mt-2 flex items-start gap-2 p-2.5 rounded-md bg-rose-500/10 border border-rose-500/20 text-rose-500">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <p className="text-[11px] break-words">{uploadError}</p>
          </div>
        )}
      </div>

      {/* ── Indexed docs list ── */}
      {docs.length > 0 && (
        <div className="border-t border-border/50 pt-4 flex flex-col gap-2">
          <p className="font-medium text-foreground">
            Indexed Documents
            <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">({docs.length})</span>
          </p>
          <div className="flex flex-col gap-1">
            {docs.map((doc) => (
              <div
                key={doc.doc_id}
                className="flex items-center justify-between px-2.5 py-2 rounded-md border border-border/60 bg-background"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText size={13} className="text-muted-foreground shrink-0" />
                  <div className="min-w-0">
                    <p className="font-medium text-foreground truncate">{doc.filename}</p>
                    <p className="text-[11px] text-muted-foreground">
                      {doc.chunks} chunks · {doc.chars.toLocaleString()} chars
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => removeDoc(doc.doc_id)}
                  className="ml-2 shrink-0 text-muted-foreground hover:text-rose-500 transition-colors"
                  title="Remove from list (does not delete from Chroma)"
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Semantic search ── */}
      <div className="border-t border-border/50 pt-4 flex flex-col gap-2">
        <p className="font-medium text-foreground">Search Indexed Documents</p>
        <div className="flex gap-1.5">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Ask anything about your docs…"
            className="flex-1 bg-muted/50 border border-border rounded-md px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
          <button
            onClick={handleSearch}
            disabled={searching || !searchQuery.trim()}
            className="px-2.5 py-1.5 bg-primary text-primary-foreground rounded-md text-xs font-medium hover:opacity-90 disabled:opacity-50 transition-opacity flex items-center gap-1"
          >
            {searching ? <Loader2 size={12} className="animate-spin" /> : <Search size={12} />}
            {searching ? "…" : "Search"}
          </button>
        </div>

        {searchError && (
          <p className="text-[11px] text-rose-500 flex items-center gap-1">
            <AlertCircle size={11} /> {searchError}
          </p>
        )}

        {searchResults !== null && (
          <div className="flex flex-col gap-1.5 mt-1">
            {searchResults.length === 0 ? (
              <p className="text-[11px] text-muted-foreground text-center py-3">No matching chunks found.</p>
            ) : (
              searchResults.map((chunk) => {
                const isOpen = expandedChunk === chunk.chunk_id;
                return (
                  <div
                    key={chunk.chunk_id}
                    className="border border-border/60 rounded-md overflow-hidden bg-background"
                  >
                    <button
                      onClick={() => setExpandedChunk(isOpen ? null : chunk.chunk_id)}
                      className="w-full flex items-center justify-between px-2.5 py-2 text-left hover:bg-muted/40 transition-colors"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-foreground truncate text-[11px]">{chunk.filename}</p>
                        <p className="text-[10px] text-muted-foreground">
                          Chunk {chunk.chunk_index + 1} · Score {(chunk.score * 100).toFixed(0)}%
                        </p>
                      </div>
                      {isOpen ? (
                        <ChevronUp size={13} className="text-muted-foreground shrink-0 ml-2" />
                      ) : (
                        <ChevronDown size={13} className="text-muted-foreground shrink-0 ml-2" />
                      )}
                    </button>
                    {isOpen && (
                      <div className="px-2.5 pb-2.5 pt-0">
                        <p className="text-[11px] text-foreground/80 whitespace-pre-wrap leading-relaxed">
                          {chunk.text}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
}
