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
export type MediaAssetStatus = "pending_upload" | "uploading" | "uploaded" | "validating" | "ready" | "rejected" | "failed" | "aborted";
export type ProcessingJobStatus = "queued" | "processing" | "succeeded" | "failed";

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
    started_at: string | null;
    finished_at: string | null;
  } | null;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, init);
  } catch {
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

export function listProjectMedia(projectId: string): Promise<MediaAsset[]> {
  return request(`/api/v1/projects/${projectId}/media`, { cache: "no-store" });
}

export function getMediaAsset(assetId: string): Promise<MediaAsset> {
  return request(`/api/v1/media/${assetId}`, { cache: "no-store" });
}

