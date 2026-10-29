"use client";

import { useRef, useState } from "react";
import { FileVideo, UploadCloud, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn, formatFileSize } from "@/lib/utils";

const ACCEPTED_TYPES = new Set(["video/mp4", "video/quicktime", "video/webm"]);
const ACCEPTED_EXTENSIONS = new Set(["mp4", "mov", "webm"]);

function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!ACCEPTED_TYPES.has(file.type) && !ACCEPTED_EXTENSIONS.has(extension)) {
    return "Choose an MP4, MOV, or WebM video file.";
  }
  return null;
}

export function UploadDropzone() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  function selectFile(file: File | undefined) {
    if (!file) return;
    const validationError = validateFile(file);
    setError(validationError);
    setSelectedFile(validationError ? null : file);
  }

  if (selectedFile) {
    return (
      <div className="rounded-2xl border border-violet-400/20 bg-violet-500/[0.05] p-5">
        <div className="flex items-center gap-4">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300"><FileVideo className="h-5 w-5" /></span>
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-zinc-200">{selectedFile.name}</p><p className="mt-1 text-xs text-zinc-500">{formatFileSize(selectedFile.size)} · Selected locally</p></div>
          <Button type="button" variant="ghost" size="icon" aria-label="Remove selected file" onClick={() => { setSelectedFile(null); setError(null); if (inputRef.current) inputRef.current.value = ""; }}><X className="h-4 w-4" /></Button>
        </div>
        <p className="mt-4 rounded-lg border border-amber-300/10 bg-amber-300/[0.05] px-3 py-2 text-xs leading-5 text-amber-100/70">This file has not been uploaded. Backend uploads and processing arrive in Milestone 2.</p>
      </div>
    );
  }

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Choose a video file"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }}
        onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
        onDragOver={(event) => event.preventDefault()}
        onDragLeave={(event) => { event.preventDefault(); setDragging(false); }}
        onDrop={(event) => { event.preventDefault(); setDragging(false); selectFile(event.dataTransfer.files[0]); }}
        className={cn("flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center outline-none transition focus-visible:ring-2 focus-visible:ring-violet-400", dragging ? "border-violet-400 bg-violet-500/10" : "border-white/12 bg-black/15 hover:border-violet-400/35 hover:bg-violet-500/[0.035]")}
      >
        <input ref={inputRef} type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" className="hidden" onChange={(event) => selectFile(event.target.files?.[0])} />
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-violet-400/15 bg-violet-500/10 text-violet-300"><UploadCloud className="h-5 w-5" /></span>
        <p className="mt-5 text-sm font-medium text-zinc-200">Drop a video here, or click to browse</p>
        <p className="mt-2 text-xs text-zinc-600">MP4, MOV, or WebM</p>
      </div>
      {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
    </div>
  );
}

