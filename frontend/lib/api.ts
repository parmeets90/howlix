import { createClient } from "@/lib/supabase/client";

export type ProjectStatus = "draft";

export type Project = {
  id: string;
  title: string;
  description: string | null;
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
};

export type CreateProjectInput = {
  title: string;
  description?: string;
};

type ApiErrorBody = {
  error?: {
    message?: string;
  };
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export type UploadSessionStatus = "initiated" | "uploading" | "completed" | "aborted" | "expired" | "failed";
export type MediaAssetStatus = "pending_upload" | "importing" | "uploading" | "uploaded" | "validating" | "ready" | "rejected" | "failed" | "aborted";
export type ProcessingJobStatus = "queued" | "processing" | "retry" | "succeeded" | "failed" | "cancelled";
export type YouTubeImportStatus = "queued" | "processing" | "retry" | "completed" | "failed" | "cancelled";
export type TranscriptStatus = "queued" | "processing" | "retry" | "completed" | "failed";
export type MomentAnalysisStatus = "queued" | "processing" | "retry" | "completed" | "failed";
export type MomentReviewStatus = "pending" | "approved" | "rejected";
export type ClipExportStatus = "queued" | "processing" | "retry" | "completed" | "failed" | "cancelled";
export type ExportAspectRatio = "9:16" | "1:1" | "16:9";
export type CaptionPreset = "none" | "minimal" | "bold" | "karaoke";
export type FramingMode = "center" | "face" | "manual";

export type UploadSession = {
  id: string;
  asset_id: string;
  status: UploadSessionStatus;
  part_size_bytes: number;
  expected_size_bytes: number;
  total_parts: number;
  created_at: string;
  expires_at: string;
  completed_at: string | null;
};

export type UploadedPart = { part_number: number; etag: string; size: number };

export type MediaAsset = {
  id: string;
  project_id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  frame_rate: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  container_format: string | null;
  status: MediaAssetStatus;
  created_at: string;
  updated_at: string;
  preview_url: string | null;
  preview_url_expires_at: string | null;
  latest_job: {
    id: string;
    status: ProcessingJobStatus;
    attempts: number;
    max_attempts: number;
    error_message: string | null;
    progress_stage: string | null;
    progress_completed: number | null;
    progress_total: number | null;
    started_at: string | null;
    finished_at: string | null;
  } | null;
};

export type YouTubeImport = {
  id: string;
  project_id: string;
  asset_id: string;
  source_url: string;
  canonical_url: string;
  video_id: string;
  status: YouTubeImportStatus;
  title: string | null;
  channel_name: string | null;
  source_duration_seconds: number | null;
  error_message: string | null;
  permission_confirmed_at: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  job: MediaAsset["latest_job"];
};

export type TranscriptSegment = {
  id: string;
  start_ms: number;
  end_ms: number;
  text: string;
};

export type TranscriptWord = {
  id: string;
  segment_id: string | null;
  start_ms: number;
  end_ms: number;
  word: string;
  confidence: number | null;
};

export type Transcript = {
  id: string;
  asset_id: string;
  provider: string;
  model: string;
  language: string | null;
  status: TranscriptStatus;
  full_text: string | null;
  segments: TranscriptSegment[];
  words: TranscriptWord[];
  created_at: string;
  updated_at: string;
};

export type TranscriptionStatus = {
  asset_id: string;
  transcript_id: string | null;
  transcript_status: TranscriptStatus | null;
  job: MediaAsset["latest_job"];
};

export type MomentAnalysis = {
  id: string;
  asset_id: string;
  transcript_id: string;
  status: MomentAnalysisStatus;
  provider: string;
  model: string;
  prompt_version: string;
  analysis_version: string;
  settings: Record<string, unknown>;
  usage: Record<string, number> | null;
  error_message: string | null;
  recommendation_count: number;
  job: MediaAsset["latest_job"];
  created_at: string;
  completed_at: string | null;
};

export type MomentScoreFactor = {
  score: number | null;
  weight: number;
  assessed: boolean;
};

export type MomentCandidate = {
  id: string;
  analysis_run_id: string;
  asset_id: string;
  start_ms: number;
  end_ms: number;
  ai_start_ms: number;
  ai_end_ms: number;
  duration_ms: number;
  suggested_title: string;
  hook_text: string;
  topic: string;
  category: string;
  overall_score: number;
  score_breakdown: Record<string, MomentScoreFactor>;
  explanation: string;
  confidence_notes: string;
  needs_context: boolean;
  rank: number;
  review_status: MomentReviewStatus;
  transcript_excerpt: string;
  created_at: string;
  updated_at: string;
};

export type ClipExportSettings = {
  aspect_ratio?: ExportAspectRatio;
  quality?: "720p" | "1080p";
  framing_mode?: FramingMode;
  caption_preset?: CaptionPreset;
  fps?: number;
  manual_crop_x?: number;
  manual_crop_y?: number;
  caption_font_size?: number;
  caption_text_color?: string;
  caption_highlight_color?: string;
  caption_vertical_position?: "bottom" | "center" | "top";
};

export type ClipExport = {
  id: string;
  moment_id: string;
  asset_id: string;
  status: ClipExportStatus;
  aspect_ratio: ExportAspectRatio;
  resolution: string;
  fps: number;
  caption_preset: CaptionPreset;
  framing_mode: FramingMode;
  render_settings: Record<string, unknown>;
  file_size_bytes: number | null;
  duration_ms: number;
  video_codec: string | null;
  audio_codec: string | null;
  error_message: string | null;
  job: MediaAsset["latest_job"];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type Account = { user_id: string; email: string | null };
export type Usage = {
  projects_used: number;
  projects_limit: number;
  stored_media_bytes: number;
  stored_media_limit_bytes: number;
  transcription_seconds: number;
  transcription_limit_seconds: number;
  analysis_jobs: number;
  analysis_jobs_limit: number;
  concurrent_renders: number;
  concurrent_renders_limit: number;
  period_start: string;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    const { data } = await createClient().auth.getSession();
    if (!data.session?.access_token) throw new ApiError("Your session has expired. Sign in again.", 401);
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${data.session.access_token}`);
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch (cause) {
    if (cause instanceof ApiError) throw cause;
    throw new Error("Could not connect to the Howlix API. Make sure the backend is running.");
  }

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // The fallback below is intentionally used for non-JSON server errors.
    }
    throw new ApiError(
      body?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

export function getAccount(): Promise<Account> {
  return request<Account>("/api/v1/account", { cache: "no-store" });
}

export function getUsage(): Promise<Usage> {
  return request<Usage>("/api/v1/account/usage", { cache: "no-store" });
}

export function listProjects(): Promise<Project[]> {
  return request<Project[]>("/api/v1/projects", { cache: "no-store" });
}

export function createProject(input: CreateProjectInput): Promise<Project> {
  return request<Project>("/api/v1/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/api/v1/projects/${projectId}`, { cache: "no-store" });
}

export function initiateUpload(
  projectId: string,
  input: { original_filename: string; mime_type: string; file_size_bytes: number },
): Promise<{ session: UploadSession }> {
  return request(`/api/v1/projects/${projectId}/uploads/initiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function signUploadPart(
  sessionId: string,
  partNumber: number,
): Promise<{ part_number: number; upload_url: string; expires_at: string }> {
  return request(`/api/v1/uploads/${sessionId}/parts/sign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ part_number: partNumber }),
  });
}

export function listUploadedParts(sessionId: string): Promise<{ session_id: string; parts: UploadedPart[] }> {
  return request(`/api/v1/uploads/${sessionId}/parts`, { cache: "no-store" });
}

export function completeUpload(
  sessionId: string,
  parts: Array<{ part_number: number; etag: string }>,
): Promise<{ session: UploadSession; asset_id: string; asset_status: MediaAssetStatus; validation_job_id: string | null }> {
  return request(`/api/v1/uploads/${sessionId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ parts }),
  });
}

export function abortUpload(sessionId: string): Promise<UploadSession> {
  return request(`/api/v1/uploads/${sessionId}/abort`, { method: "POST" });
}

export function getUploadSession(sessionId: string): Promise<UploadSession> {
  return request(`/api/v1/uploads/${sessionId}`, { cache: "no-store" });
}

export function createYouTubeImport(
  projectId: string,
  input: { url: string; permission_confirmed: boolean },
): Promise<YouTubeImport> {
  return request(`/api/v1/projects/${projectId}/youtube-imports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function listYouTubeImports(projectId: string): Promise<YouTubeImport[]> {
  return request(`/api/v1/projects/${projectId}/youtube-imports`, { cache: "no-store" });
}

export function cancelYouTubeImport(importId: string): Promise<YouTubeImport> {
  return request(`/api/v1/youtube-imports/${importId}/cancel`, { method: "POST" });
}

export function retryYouTubeImport(importId: string): Promise<YouTubeImport> {
  return request(`/api/v1/youtube-imports/${importId}/retry`, { method: "POST" });
}

export function listProjectMedia(projectId: string): Promise<MediaAsset[]> {
  return request(`/api/v1/projects/${projectId}/media`, { cache: "no-store" });
}

export function getMediaAsset(assetId: string): Promise<MediaAsset> {
  return request(`/api/v1/media/${assetId}`, { cache: "no-store" });
}

export function requestTranscription(assetId: string): Promise<TranscriptionStatus> {
  return request(`/api/v1/media/${assetId}/transcribe`, { method: "POST" });
}

export function getTranscript(assetId: string): Promise<Transcript> {
  return request(`/api/v1/media/${assetId}/transcript`, { cache: "no-store" });
}

export function getTranscriptionStatus(assetId: string): Promise<TranscriptionStatus> {
  return request(`/api/v1/media/${assetId}/transcription-status`, { cache: "no-store" });
}

export function discoverMoments(assetId: string): Promise<MomentAnalysis> {
  return request(`/api/v1/media/${assetId}/discover-moments`, { method: "POST" });
}

export function getMomentAnalysis(assetId: string): Promise<MomentAnalysis> {
  return request(`/api/v1/media/${assetId}/moment-analysis`, { cache: "no-store" });
}

export function listMoments(assetId: string, reviewStatus?: MomentReviewStatus): Promise<MomentCandidate[]> {
  const query = reviewStatus ? `?review_status=${reviewStatus}` : "";
  return request(`/api/v1/media/${assetId}/moments${query}`, { cache: "no-store" });
}

export function getMoment(momentId: string): Promise<MomentCandidate> {
  return request(`/api/v1/moments/${momentId}`, { cache: "no-store" });
}

export function updateMoment(
  momentId: string,
  input: { suggested_title?: string; start_ms?: number; end_ms?: number; reset_boundaries?: boolean },
): Promise<MomentCandidate> {
  return request(`/api/v1/moments/${momentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function reviewMoment(momentId: string, reviewStatus: MomentReviewStatus): Promise<MomentCandidate> {
  return request(`/api/v1/moments/${momentId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ review_status: reviewStatus }),
  });
}

export function createClipExport(momentId: string, settings: ClipExportSettings): Promise<ClipExport> {
  return request(`/api/v1/moments/${momentId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function listClipExports(momentId: string): Promise<ClipExport[]> {
  return request(`/api/v1/moments/${momentId}/exports`, { cache: "no-store" });
}

export function getClipExport(exportId: string): Promise<ClipExport> {
  return request(`/api/v1/exports/${exportId}`, { cache: "no-store" });
}

export function getClipExportDownload(exportId: string): Promise<{ export_id: string; download_url: string; expires_at: string }> {
  return request(`/api/v1/exports/${exportId}/download`, { cache: "no-store" });
}

export function cancelClipExport(exportId: string): Promise<ClipExport> {
  return request(`/api/v1/exports/${exportId}/cancel`, { method: "POST" });
}

