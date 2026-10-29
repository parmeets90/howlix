# Cloudflare R2 setup

Howlix uses a private Cloudflare R2 bucket for original video objects. Supabase remains the metadata database; do not use Supabase Storage for videos and do not store video bytes in Postgres.

## 1. Create the private bucket

1. Sign in to the Cloudflare dashboard.
2. Open **Storage & databases > R2 Object Storage**.
3. Select **Create bucket**.
4. Name it `howlix-media` and create it in the automatic location unless you have a specific data-location requirement.
5. Keep public development URLs and custom-domain public access disabled.

The application serves previews with temporary presigned GET URLs. The bucket must not be public.

## 2. Create scoped S3 credentials

1. In R2, open **Manage API tokens**.
2. Create an account API token with **Object Read & Write** permission.
3. Scope it to the `howlix-media` bucket only.
4. Record the Access Key ID and Secret Access Key when Cloudflare displays them. The secret is shown once.
5. Copy `.env.example` to `.env` and set the backend-only values:

```dotenv
R2_ACCOUNT_ID=your-cloudflare-account-id
R2_ACCESS_KEY_ID=your-r2-access-key-id
R2_SECRET_ACCESS_KEY=your-r2-secret-access-key
R2_BUCKET_NAME=howlix-media
R2_REGION=auto
```

`R2_ENDPOINT_URL` can stay blank; Howlix derives `https://<account-id>.r2.cloudflarestorage.com`. Never add these variables to `frontend/.env.local`, and never prefix them with `NEXT_PUBLIC_`.

Cloudflare reference: [R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/) and [S3 credentials](https://developers.cloudflare.com/r2/get-started/s3/).

## 3. Configure browser CORS

Open **R2 Object Storage > howlix-media > Settings > CORS Policy**, choose **Add CORS policy**, and paste this JSON:

```json
[
  {
    "AllowedOrigins": [
      "http://localhost:3000"
    ],
    "AllowedMethods": [
      "PUT",
      "GET",
      "HEAD"
    ],
    "AllowedHeaders": [
      "Content-Type"
    ],
    "ExposeHeaders": [
      "ETag",
      "Content-Length",
      "Accept-Ranges",
      "Content-Range"
    ],
    "MaxAgeSeconds": 3600
  }
]
```

`ETag` exposure is required because the browser must return each uploaded part's ETag to FastAPI. Match the frontend origin exactly, including scheme and port. Cloudflare notes that a policy change can take up to about 30 seconds to propagate.

Cloudflare reference: [R2 CORS](https://developers.cloudflare.com/r2/buckets/cors/).

## 4. Configure incomplete-upload cleanup

Howlix expires application upload sessions after 24 hours and its worker aborts the corresponding multipart uploads. Add an R2 lifecycle rule as a storage-side safety net:

1. Open **howlix-media > Settings > Object lifecycle rules**.
2. Create a rule for the entire bucket.
3. Enable **Abort incomplete multipart uploads** after 1 day.
4. Do not add an expiration rule for completed original videos unless your product retention policy explicitly requires it.

R2 otherwise aborts incomplete multipart uploads after seven days by default. The application worker plus the one-day rule prevents abandoned parts from lingering unnecessarily.

Cloudflare reference: [R2 object lifecycles](https://developers.cloudflare.com/r2/buckets/object-lifecycles/) and [multipart constraints](https://developers.cloudflare.com/r2/objects/upload-objects/).

## 5. Configure Supabase Postgres

Follow [Supabase setup](supabase.md) and keep `HOWLIX_DATABASE_URL` in the root `.env`. Then apply both migrations:

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
alembic upgrade head
```

This preserves the existing `projects` table and adds `media_assets`, `upload_sessions`, and `processing_jobs`.

## 6. Install FFmpeg on Windows

FFprobe is bundled with FFmpeg:

```powershell
winget install --id Gyan.FFmpeg --exact
```

Open a new PowerShell window and verify:

```powershell
ffmpeg -version
ffprobe -version
```

If FFprobe is installed elsewhere, set `FFPROBE_PATH` in `.env` to its full executable path.

## 7. Run Howlix

Use three PowerShell windows from the repository root.

Backend API:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Worker:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

Frontend:

```powershell
cd frontend
npm run dev
```

Open `http://localhost:3000`, create a project, select an MP4, MOV, or WebM video no larger than 1 GiB, and start the upload. Keep the worker running. The project detail page progresses from uploading to validating and then ready/rejected.

## 8. Diagnose common failures

### Browser reports a CORS or network error

- Confirm the R2 bucket is still private; public access is not needed.
- Confirm `AllowedOrigins` exactly matches `http://localhost:3000`.
- Confirm `PUT` is allowed and `Content-Type` is an allowed request header.
- Confirm `ETag` is exposed. Upload data can reach R2 while completion still fails if JavaScript cannot read that header.
- Wait 30 seconds after changing the policy and retry.
- Inspect the failed browser request. An expired presigned URL returns 403 and can appear as an opaque CORS error. Howlix requests a fresh part URL and retries up to three times.

### Upload completes but validation does not start

- Confirm `python -m app.worker` is running against the same `HOWLIX_DATABASE_URL` as FastAPI.
- Confirm `ffprobe -version` works in that PowerShell session.
- Check the persisted asset and processing-job error on the project detail page.
- Confirm the R2 credentials have Object Read & Write access to the configured bucket.

### Object size mismatch

Howlix refuses completion when R2 part sizes or the final `HeadObject` size differ from the declared file size, marks the upload failed, and deletes a mismatched completed object when safe. Start a fresh upload rather than reusing that session.

## 9. Clean up abandoned uploads

Keep the worker running periodically: before claiming validation work it marks expired sessions and calls R2 `AbortMultipartUpload`. The bucket lifecycle rule is the independent fallback for sessions left behind while the worker is offline.

To inspect application records, use the Supabase table editor or SQL editor and filter `upload_sessions` for `initiated` or `uploading` records whose `expires_at` is in the past. Prefer starting the worker to reconcile them; do not manually delete database rows while an R2 multipart upload may still exist.

## 10. Optional real R2 verification

Ordinary tests never write to R2. After configuring a dedicated development bucket, opt in explicitly:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
$env:RUN_R2_INTEGRATION_TESTS="true"
python -m pytest -m integration tests\test_r2_integration.py
Remove-Item Env:RUN_R2_INTEGRATION_TESTS
```

The test uploads a small object under `integration-tests/` and removes it in cleanup. Do not enable this in routine test runs or against an unapproved bucket.
