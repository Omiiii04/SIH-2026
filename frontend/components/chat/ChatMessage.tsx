"use client";

import type { QueryResponse, NodeFailureResponse, AttachmentMeta } from "@/lib/types";
import { FileText, Code, Image as ImageIcon } from "lucide-react";
import { ThinkingPanel } from "./ThinkingPanel";

export interface MessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  attachments?: AttachmentMeta[];
  result?: QueryResponse | NodeFailureResponse;
  ok?: boolean;
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ChatMessage({ msg }: { msg: MessageData }) {
  const isUser = msg.role === "user";

  if (isUser) {
    return (
      <div className="flex flex-col items-end w-full mb-6 gap-1.5">
        {msg.attachments && msg.attachments.length > 0 && (
          <div className="flex flex-wrap justify-end gap-2 max-w-[85%] sm:max-w-[75%]">
            {msg.attachments.map((att, i) => (
              <div key={i} className="flex flex-col gap-1 items-end">
                {att.kind === "image" && att.preview_url ? (
                  <div className="relative rounded-xl overflow-hidden border border-border/80 shadow-2xs max-w-[220px] max-h-[180px] bg-background">
                    <img
                      src={att.preview_url}
                      alt={att.filename}
                      className="w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-muted/90 border border-border/80 text-xs shadow-2xs">
                    {att.kind === "image" ? (
                      <ImageIcon size={14} className="text-muted-foreground shrink-0" />
                    ) : att.kind === "pdf" ? (
                      <FileText size={14} className="text-rose-500 shrink-0" />
                    ) : att.kind === "code" ? (
                      <Code size={14} className="text-blue-500 shrink-0" />
                    ) : (
                      <FileText size={14} className="text-muted-foreground shrink-0" />
                    )}
                    <span className="font-medium text-foreground truncate max-w-[180px]">{att.filename}</span>
                    {att.size > 0 && (
                      <span className="text-[10px] text-muted-foreground font-mono">{formatBytes(att.size)}</span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {msg.content && msg.content !== "[File attached]" && (
          <div className="max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-2.5 bg-muted/80 text-foreground text-[14.5px] leading-relaxed whitespace-pre-wrap break-words shadow-2xs">
            {msg.content}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full mb-8 text-left">
      <div className="text-[15px] leading-relaxed text-foreground whitespace-pre-wrap break-words">
        {msg.content}
      </div>

      {msg.result && (
        <ThinkingPanel result={msg.result} ok={msg.ok ?? false} />
      )}
    </div>
  );
}

