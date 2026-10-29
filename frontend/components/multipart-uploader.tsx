"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  CirclePause,
  CirclePlay,
  FileVideo,
  LoaderCircle,
  RefreshCw,
  RotateCcw,
  UploadCloud,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  abortUpload,
  completeUpload,
  getUploadSession,
  initiateUpload,
  listUploadedParts,
  signUploadPart,
  type UploadSession,
} from "@/lib/api";
import {
  UploadRequestAbortedError,
  UploadRequestError,
  uploadPartWithProgress,
} from "@/lib/multipart-upload";
import { cn, formatFileSize } from "@/lib/utils";

const ACCEPTED_TYPES = new Set(["video/mp4", "video/quicktime", "video/webm"]);
const MIME_BY_EXTENSION: Record<string, string> = {
  mp4: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
};
const MAX_FILE_SIZE = 1024 * 1024 * 1024;
const MAX_PARALLEL_PARTS = 2;

type UploadUiStatus =
  | "idle"
  | "selected"
  | "uploading"
  | "paused"
  | "verifying"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

type RecoveryRecord = {
  projectId: string;
  fileName: string;
  fileSize: number;
  mimeType: string;
  session: UploadSession;
};

function validatedMimeType(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  const expected = MIME_BY_EXTENSION[extension];
  if (!expected || (file.type && !ACCEPTED_TYPES.has(file.type))) return null;
  if (file.type && file.type !== expected) return null;
  return expected;
}

function validateFile(file: File): string | null {
  if (!validatedMimeType(file)) return "Choose an MP4, MOV, or WebM video file.";
  if (file.size <= 0) return "The selected file is empty.";
  if (file.size > MAX_FILE_SIZE) return "Videos may not exceed 1 GiB.";
  return null;
}

function recoveryKey(projectId: string): string {
  return `howlix-upload:${projectId}`;
}

export function MultipartUploader({
  projectId,
  onUploadComplete,
}: {
  projectId: string;
  onUploadComplete?: (assetId: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const activeRequests = useRef(new Set<XMLHttpRequest>());
  const sessionRef = useRef<UploadSession | null>(null);
  const pausedRef = useRef(false);
  const cancelledRef = useRef(false);
  const resumeWaiters = useRef<Array<() => void>>([]);
  const uploadedBytes = useRef(new Map<number, number>());
  const activeBytes = useRef(new Map<number, number>());

  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [recovery, setRecovery] = useState<RecoveryRecord | null>(null);
  const [status, setStatus] = useState<UploadUiStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const raw = window.localStorage.getItem(recoveryKey(projectId));
    if (!raw) return;
    let record: RecoveryRecord;
    try {
      record = JSON.parse(raw) as RecoveryRecord;
    } catch {
      window.localStorage.removeItem(recoveryKey(projectId));
      return;
    }
    getUploadSession(record.session.id)
      .then((session) => {
        if (session.status === "initiated" || session.status === "uploading") {
          setRecovery({ ...record, session });
        } else {
          window.localStorage.removeItem(recoveryKey(projectId));
        }
      })
      .catch(() => window.localStorage.removeItem(recoveryKey(projectId)));
  }, [projectId]);

  function updateProgress(fileSize: number) {
    const completed = [...uploadedBytes.current.values()].reduce((sum, size) => sum + size, 0);
    const active = [...activeBytes.current.values()].reduce((sum, size) => sum + size, 0);
    setProgress(Math.min(100, Math.round(((completed + active) / fileSize) * 1000) / 10));
  }

  function selectFile(file: File | undefined) {
    if (!file) return;
    const validationError = validateFile(file);
    if (!validationError && recovery) {
      if (file.name !== recovery.fileName || file.size !== recovery.fileSize) {
        setError("Select the same file to resume this upload, or discard the saved session.");
        return;
      }
      sessionRef.current = recovery.session;
    }
    setError(validationError);
    setSelectedFile(validationError ? null : file);
    setStatus(validationError ? "idle" : "selected");
  }

  function persistRecovery(file: File, session: UploadSession, mimeType: string) {
    const record: RecoveryRecord = {
      projectId,
      fileName: file.name,
      fileSize: file.size,
      mimeType,
      session,
    };
    window.localStorage.setItem(recoveryKey(projectId), JSON.stringify(record));
    setRecovery(record);
  }

  async function waitWhilePaused() {
    if (!pausedRef.current) return;
    await new Promise<void>((resolve) => resumeWaiters.current.push(resolve));
  }

  function resumeAllWaiters() {
    const waiters = resumeWaiters.current.splice(0);
    waiters.forEach((resolve) => resolve());
  }

  async function uploadSelectedFile() {
    const file = selectedFile;
    if (!file) return;
    const mimeType = validatedMimeType(file);
    if (!mimeType) return;
    setError(null);
    setStatus("uploading");
    pausedRef.current = false;
    cancelledRef.current = false;
    uploadedBytes.current.clear();
    activeBytes.current.clear();

    try {
      let session = sessionRef.current;
      if (!session) {
        session = (
          await initiateUpload(projectId, {
            original_filename: file.name,
            mime_type: mimeType,
            file_size_bytes: file.size,
          })
        ).session;
        sessionRef.current = session;
        persistRecovery(file, session, mimeType);
      }
      const activeSession = session;
      const remote = await listUploadedParts(activeSession.id);
      const etags = new Map<number, string>();
      for (const part of remote.parts) {
        etags.set(part.part_number, part.etag);
        uploadedBytes.current.set(part.part_number, part.size);
      }
      updateProgress(file.size);
      const queue = Array.from(
        { length: activeSession.total_parts },
        (_, index) => index + 1,
      ).filter((partNumber) => !etags.has(partNumber));

      const uploadWorker = async () => {
        while (queue.length > 0) {
          if (cancelledRef.current) return;
          await waitWhilePaused();
          if (cancelledRef.current) return;
          const partNumber = queue.shift();
          if (!partNumber) return;
          const start = (partNumber - 1) * activeSession.part_size_bytes;
          const blob = file.slice(
            start,
            Math.min(start + activeSession.part_size_bytes, file.size),
          );
          let completed = false;
          for (let attempt = 0; attempt < 3 && !completed; attempt += 1) {
            await waitWhilePaused();
            const signed = await signUploadPart(activeSession.id, partNumber);
            let request: XMLHttpRequest | null = null;
            try {
              const etag = await uploadPartWithProgress(
                signed.upload_url,
                blob,
                (loaded) => {
                  activeBytes.current.set(partNumber, loaded);
                  updateProgress(file.size);
                },
                (created) => {
                  request = created;
                  activeRequests.current.add(created);
                },
              );
              etags.set(partNumber, etag);
              activeBytes.current.delete(partNumber);
              uploadedBytes.current.set(partNumber, blob.size);
              updateProgress(file.size);
              completed = true;
            } catch (uploadError) {
              activeBytes.current.delete(partNumber);
              updateProgress(file.size);
              if (uploadError instanceof UploadRequestAbortedError && pausedRef.current) {
                queue.push(partNumber);
                break;
              }
              if (
                uploadError instanceof UploadRequestError &&
                (uploadError.status === 401 || uploadError.status === 403) &&
                attempt < 2
              ) {
                continue;
              }
              throw uploadError;
            } finally {
              if (request) activeRequests.current.delete(request);
            }
          }
        }
      };

      await Promise.all(
        Array.from(
          { length: Math.min(MAX_PARALLEL_PARTS, Math.max(queue.length, 1)) },
          () => uploadWorker(),
        ),
      );
      if (cancelledRef.current) return;
      if (etags.size !== activeSession.total_parts) {
        throw new Error("Not all upload parts completed. Retry the upload to continue.");
      }
      setStatus("verifying");
      const completed = await completeUpload(
        activeSession.id,
        [...etags.entries()]
          .sort(([left], [right]) => left - right)
          .map(([part_number, etag]) => ({ part_number, etag })),
      );
      window.localStorage.removeItem(recoveryKey(projectId));
      setRecovery(null);
      setProgress(100);
      setStatus("processing");
      onUploadComplete?.(completed.asset_id);
      setStatus("completed");
    } catch (uploadError) {
      if (cancelledRef.current) return;
      setError(uploadError instanceof Error ? uploadError.message : "The upload failed.");
      setStatus("failed");
    }
  }

  function pauseUpload() {
    pausedRef.current = true;
    setStatus("paused");
    activeRequests.current.forEach((request) => request.abort());
  }

  function resumeUpload() {
    pausedRef.current = false;
    setStatus("uploading");
    resumeAllWaiters();
  }

  async function cancelUpload() {
    cancelledRef.current = true;
    pausedRef.current = false;
    activeRequests.current.forEach((request) => request.abort());
    resumeAllWaiters();
    const session = sessionRef.current;
    if (session && session.status !== "completed") {
      try {
        await abortUpload(session.id);
      } catch (abortError) {
        setError(abortError instanceof Error ? abortError.message : "The upload could not be cancelled.");
        setStatus("failed");
        return;
      }
    }
    window.localStorage.removeItem(recoveryKey(projectId));
    sessionRef.current = null;
    setRecovery(null);
    setProgress(0);
    setStatus("cancelled");
  }

  async function discardRecovery() {
    if (recovery) {
      try {
        await abortUpload(recovery.session.id);
      } catch {
        // R2 lifecycle cleanup remains the safety net if the old session is already gone.
      }
    }
    window.localStorage.removeItem(recoveryKey(projectId));
    sessionRef.current = null;
    setRecovery(null);
    setSelectedFile(null);
    setError(null);
    setStatus("idle");
  }

  const active = ["uploading", "paused", "verifying", "processing"].includes(status);

  return (
    <div className="space-y-4">
      {recovery && !selectedFile && (
        <div className="flex flex-col gap-3 rounded-xl border border-violet-400/20 bg-violet-500/[0.06] p-4 sm:flex-row sm:items-center sm:justify-between">
          <div><p className="text-sm font-medium text-violet-100">Upload recovery available</p><p className="mt-1 text-xs text-zinc-500">Select {recovery.fileName} again to reconcile completed R2 parts.</p></div>
          <Button type="button" size="sm" variant="ghost" onClick={() => void discardRecovery()}>Discard session</Button>
        </div>
      )}

      {!selectedFile ? (
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
          className={cn(
            "flex min-h-56 cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center outline-none transition focus-visible:ring-2 focus-visible:ring-violet-400",
            dragging ? "border-violet-400 bg-violet-500/10" : "border-white/12 bg-black/15 hover:border-violet-400/35 hover:bg-violet-500/[0.035]",
          )}
        >
          <input ref={inputRef} type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" className="hidden" onChange={(event) => selectFile(event.target.files?.[0])} />
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-violet-400/15 bg-violet-500/10 text-violet-300"><UploadCloud className="h-5 w-5" /></span>
          <p className="mt-5 text-sm font-medium text-zinc-200">Drop a video here, or click to browse</p>
          <p className="mt-2 text-xs text-zinc-600">MP4, MOV, or WebM · up to 1 GiB</p>
        </div>
      ) : (
        <div className="rounded-2xl border border-violet-400/20 bg-violet-500/[0.05] p-5">
          <div className="flex items-center gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300"><FileVideo className="h-5 w-5" /></span>
            <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-zinc-200">{selectedFile.name}</p><p className="mt-1 text-xs text-zinc-500">{formatFileSize(selectedFile.size)} · Direct to private R2 storage</p></div>
            {!active && status !== "completed" && <Button type="button" variant="ghost" size="icon" aria-label="Remove selected file" onClick={() => { setSelectedFile(null); setError(null); setStatus("idle"); if (inputRef.current) inputRef.current.value = ""; }}><X className="h-4 w-4" /></Button>}
          </div>

          {status !== "selected" && status !== "idle" && (
            <div className="mt-5">
              <div className="flex items-center justify-between text-xs"><span className="capitalize text-zinc-400">{status === "verifying" ? "Verifying upload" : status === "processing" ? "Validation queued" : status}</span><span className="font-mono text-zinc-500">{progress.toFixed(1)}%</span></div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/[0.06]"><div className="h-full rounded-full bg-violet-500 transition-[width] duration-150" style={{ width: `${progress}%` }} /></div>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            {(status === "selected" || status === "failed") && <Button type="button" size="sm" onClick={() => void uploadSelectedFile()}>{status === "failed" ? <><RotateCcw className="h-3.5 w-3.5" /> Retry</> : <><UploadCloud className="h-3.5 w-3.5" /> {recovery ? "Resume upload" : "Start upload"}</>}</Button>}
            {status === "uploading" && <Button type="button" size="sm" variant="secondary" onClick={pauseUpload}><CirclePause className="h-3.5 w-3.5" /> Pause</Button>}
            {status === "paused" && <Button type="button" size="sm" onClick={resumeUpload}><CirclePlay className="h-3.5 w-3.5" /> Resume</Button>}
            {active && status !== "processing" && <Button type="button" size="sm" variant="ghost" onClick={() => void cancelUpload()}><X className="h-3.5 w-3.5" /> Cancel</Button>}
            {(status === "verifying" || status === "processing") && <span className="inline-flex items-center gap-2 px-2 text-xs text-zinc-500"><LoaderCircle className="h-3.5 w-3.5 animate-spin" /> {status === "verifying" ? "Reconciling R2 parts" : "Waiting for the worker"}</span>}
            {status === "completed" && <span className="inline-flex items-center gap-2 text-sm text-emerald-300"><Check className="h-4 w-4" /> Upload completed</span>}
            {status === "cancelled" && <Button type="button" size="sm" variant="secondary" onClick={() => { setSelectedFile(null); setStatus("idle"); }}><RefreshCw className="h-3.5 w-3.5" /> Choose another file</Button>}
          </div>
        </div>
      )}
      {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
    </div>
  );
}
