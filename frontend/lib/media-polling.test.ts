import { describe, expect, it } from "vitest";

import type { MediaAsset } from "@/lib/api";
import { mergeMediaWithoutReloadingVideo } from "@/lib/media-polling";

function media(overrides: Partial<MediaAsset> = {}): MediaAsset {
  return {
    id: "asset-1",
    project_id: "project-1",
    original_filename: "video.mp4",
    mime_type: "video/mp4",
    file_size_bytes: 1234,
    duration_seconds: 42,
    width: 1280,
    height: 720,
    frame_rate: 30,
    video_codec: "h264",
    audio_codec: "aac",
    container_format: "mov,mp4",
    status: "ready",
    created_at: "2026-11-03T00:00:00Z",
    updated_at: "2026-11-03T00:01:00Z",
    preview_url: "https://example.test/first-signed-url",
    preview_url_expires_at: "2026-11-03T00:06:00Z",
    latest_job: null,
    ...overrides,
  };
}

describe("mergeMediaWithoutReloadingVideo", () => {
  it("keeps the existing media object when only its signed preview URL changes", () => {
    const current = [media()];
    const incoming = [
      media({
        preview_url: "https://example.test/new-signed-url",
        preview_url_expires_at: "2026-11-03T00:10:00Z",
      }),
    ];

    const result = mergeMediaWithoutReloadingVideo(current, incoming);

    expect(result).toBe(current);
    expect(result[0].preview_url).toBe("https://example.test/first-signed-url");
  });

  it("accepts incoming media when processing state changes", () => {
    const current = [media({ status: "validating" })];
    const incoming = [
      media({
        status: "ready",
        updated_at: "2026-11-03T00:02:00Z",
      }),
    ];

    const result = mergeMediaWithoutReloadingVideo(current, incoming);

    expect(result).not.toBe(current);
    expect(result[0]).toBe(incoming[0]);
  });
});
