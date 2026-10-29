import { describe, expect, it } from "vitest";

import {
  UploadRequestAbortedError,
  uploadPartWithProgress,
} from "./multipart-upload";

class FakeXhr {
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 200;
  etag: string | null = '"etag-1"';
  mode: "success" | "error" | "abort" = "success";

  open() {}

  getResponseHeader(name: string) {
    return name.toLowerCase() === "etag" ? this.etag : null;
  }

  send(blob: Blob) {
    this.upload.onprogress?.({ lengthComputable: true, loaded: blob.size / 2 } as ProgressEvent);
    if (this.mode === "error") this.onerror?.();
    else if (this.mode === "abort") this.onabort?.();
    else this.onload?.();
  }
}

function factory(fake: FakeXhr) {
  return () => fake as unknown as XMLHttpRequest;
}

describe("uploadPartWithProgress", () => {
  it("reports real XHR byte progress and returns the R2 ETag", async () => {
    const fake = new FakeXhr();
    const progress: number[] = [];
    const etag = await uploadPartWithProgress(
      "https://r2.test/signed",
      new Blob([new Uint8Array(10)]),
      (loaded) => progress.push(loaded),
      undefined,
      factory(fake),
    );
    expect(etag).toBe('"etag-1"');
    expect(progress).toEqual([5, 10]);
  });

  it("surfaces R2 HTTP errors", async () => {
    const fake = new FakeXhr();
    fake.status = 503;
    await expect(
      uploadPartWithProgress(
        "https://r2.test/signed",
        new Blob(["part"]),
        () => undefined,
        undefined,
        factory(fake),
      ),
    ).rejects.toMatchObject({ status: 503 });
  });

  it("distinguishes paused or cancelled requests from network failures", async () => {
    const fake = new FakeXhr();
    fake.mode = "abort";
    await expect(
      uploadPartWithProgress(
        "https://r2.test/signed",
        new Blob(["part"]),
        () => undefined,
        undefined,
        factory(fake),
      ),
    ).rejects.toBeInstanceOf(UploadRequestAbortedError);
  });

  it("explains missing CORS ETag exposure", async () => {
    const fake = new FakeXhr();
    fake.etag = null;
    await expect(
      uploadPartWithProgress(
        "https://r2.test/signed",
        new Blob(["part"]),
        () => undefined,
        undefined,
        factory(fake),
      ),
    ).rejects.toThrow("ExposeHeaders");
  });
});
