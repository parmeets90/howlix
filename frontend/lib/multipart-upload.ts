export class UploadRequestError extends Error {
  constructor(message: string, public readonly status: number | null = null) {
    super(message);
    this.name = "UploadRequestError";
  }
}

export class UploadRequestAbortedError extends UploadRequestError {
  constructor() {
    super("The upload request was interrupted.");
    this.name = "UploadRequestAbortedError";
  }
}

export type XhrFactory = () => XMLHttpRequest;

export function uploadPartWithProgress(
  url: string,
  blob: Blob,
  onProgress: (loaded: number) => void,
  onRequestCreated?: (request: XMLHttpRequest) => void,
  xhrFactory: XhrFactory = () => new XMLHttpRequest(),
): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = xhrFactory();
    onRequestCreated?.(request);
    request.open("PUT", url, true);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.min(event.loaded, blob.size));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        const etag = request.getResponseHeader("ETag");
        if (!etag) {
          reject(
            new UploadRequestError(
              "The upload service could not confirm this part. Please try again.",
              request.status,
            ),
          );
          return;
        }
        onProgress(blob.size);
        resolve(etag);
        return;
      }
      reject(
        new UploadRequestError(
          request.status === 401 || request.status === 403
            ? "The signed upload URL expired."
            : `The upload service could not save this part (${request.status}).`,
          request.status,
        ),
      );
    };
    request.onerror = () => reject(new UploadRequestError("Your connection was interrupted. Please try again."));
    request.onabort = () => reject(new UploadRequestAbortedError());
    request.send(blob);
  });
}

