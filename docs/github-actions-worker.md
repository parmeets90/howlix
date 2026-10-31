# GitHub Actions on-demand worker

This private-beta architecture replaces an always-on Windows worker with an
ephemeral GitHub-hosted Ubuntu runner for each authorized queued job. It keeps
Vercel, the Render Free API, Supabase PostgreSQL, and private Cloudflare R2 in
their existing roles.

```text
Browser -> Vercel -> authenticated Render API
                         |
                         +-- transaction: create processing_jobs row in Supabase
                         +-- workflow_dispatch(job UUID) -> GitHub Actions
                                                               |
                                                               +-- atomic claim + lease
                                                               +-- R2 download/upload
                                                               +-- Groq / FFmpeg
                                                               +-- persisted status
```

The browser never receives a GitHub token. GitHub Actions does not poll and no
runner remains online between jobs.

## Actual job architecture

All background work uses `processing_jobs` and one lease-backed worker router:

| Job type | Created by | Work performed |
| --- | --- | --- |
| `validate_media` | Multipart completion or successful YouTube import | Private R2 download, FFprobe validation, media metadata persistence |
| `youtube_import` | Authorized URL import endpoint | yt-dlp download with existing URL/size/time restrictions, FFprobe, private R2 upload; then creates `validate_media` |
| `transcribe_media` | Transcription request | R2 download, FFmpeg audio chunks, Groq/faster-whisper transcription, word/segment persistence |
| `moment_discovery` | Moment discovery request | Deterministic candidates, Groq editorial evaluation, scoring/ranking persistence |
| `clip_render` | Approved moment export request | R2 download, crop/framing, ASS captions, FFmpeg render/validation, private R2 export upload |

Claims use a PostgreSQL row lock, owner checks, job state, attempt limits, and a
renewed lease. A second GitHub runner or the legacy local worker cannot claim a
job with a live lease. Clip rendering retains its existing single-active-render
guard. The Actions workflow adds a global concurrency group and the database
dispatcher applies a configurable private-beta cap.

`python -m app.worker` remains the local polling mode. The Actions command is:

```bash
python -m app.worker --job-id "00000000-0000-0000-0000-000000000000"
```

It only claims that UUID, verifies its owner and asset ownership, processes its
bounded retries, and exits. Exit status `0` means succeeded/cancelled, `1`
means processing reached a failed state, and `2` means missing, ineligible, or
already claimed. The UUID does not become a command or file path.

## Database migration

Migration `20261031_0008` adds dispatch state, attempt count, sanitized error,
request time, and dispatch time to `processing_jobs`. It is additive and does
not reset jobs or media. Apply it manually before enabling dispatch:

```powershell
Set-Location backend
.\.venv\Scripts\Activate.ps1
alembic current
alembic upgrade 20261031_0008
alembic current
```

Do not run migrations automatically in Render startup or GitHub Actions.

## GitHub repository configuration

The workflow is `.github/workflows/howlix-worker.yml`. It accepts only a job
UUID through `workflow_dispatch`, checks out trusted `main`, uses pinned
official checkout/setup-python commits, grants only `contents: read` and
`actions: write`, and never runs for pull requests. The `actions: write`
permission lets a YouTube import dispatch its follow-up validation job using
the ephemeral `GITHUB_TOKEN`.

Add these **Actions repository secrets** in
**Settings > Secrets and variables > Actions**:

| Secret | Placeholder |
| --- | --- |
| `HOWLIX_DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@SUPABASE_POOLER:5432/postgres?sslmode=require` |
| `R2_ACCOUNT_ID` | `cloudflare-account-id` |
| `R2_ACCESS_KEY_ID` | `bucket-scoped-r2-access-key-id` |
| `R2_SECRET_ACCESS_KEY` | `bucket-scoped-r2-secret` |
| `R2_BUCKET_NAME` | `howlix-media` |
| `GROQ_API_KEY` | `gsk_placeholder` |

Use the same Supabase schema and private R2 bucket as Render. Use bucket-scoped
R2 credentials. Supabase Auth keys are not required by the worker because it
never authenticates browser requests. Do not add `.env`, a Supabase service
role key, browser cookies, or production secrets to workflow YAML.

Protect `main`, restrict Actions changes to reviewed trusted commits, and do
not expose production secrets to fork pull requests. There is no
`pull_request_target` trigger.

## Render environment configuration

Keep all current Render variables and add:

| Variable | Placeholder/value |
| --- | --- |
| `GITHUB_ACTIONS_DISPATCH_ENABLED` | Start with `false`; change to `true` only after migration, secrets, and approval |
| `GITHUB_ACTIONS_TOKEN` | `github-fine-grained-token-placeholder` |
| `GITHUB_REPOSITORY` | `parmeets90/howlix` |
| `GITHUB_WORKER_WORKFLOW` | `howlix-worker.yml` |
| `GITHUB_WORKER_REF` | `main` |
| `GITHUB_DISPATCH_TIMEOUT_SECONDS` | `10` |
| `GITHUB_DISPATCH_MAX_ATTEMPTS` | `3` |
| `GITHUB_RUNNER_STARTUP_TIMEOUT_SECONDS` | `600` |
| `GITHUB_ACTIONS_MAX_ACTIVE_JOBS` | `1` or `2` for private beta |

Use a fine-grained personal access token limited to repository
`parmeets90/howlix` with repository **Actions: write** permission. Do not grant
organization administration, account, package, or unrelated repository access.
Store it only in Render. GitHub's workflow uses its short-lived built-in token,
not the Render token.

## Dispatch and recovery behavior

After a successful API transaction, Render dispatches the persisted UUID. A
204 response records `starting_runner`; an atomic claim records `processing`.
Processor stages continue to supply real progress. Terminal state remains
`succeeded`, `failed`, or `cancelled`.

Transient GitHub API failures receive bounded retries. The response body is not
stored or logged. A failed dispatch records `dispatch_failed` and a sanitized
HTTP/error class. A capacity-limited request records `waiting_runner_capacity`.
An authenticated owner may recover an eligible job with:

```text
POST /api/v1/jobs/{job_id}/dispatch
Authorization: Bearer <Supabase access token>
```

Cross-user UUIDs return not-found. Successful recent dispatches are idempotent;
after the configured startup timeout, the same persisted job can be dispatched
again. PostgreSQL claiming still prevents duplicate execution if the first
runner eventually starts. Dispatch attempts, processing attempts, workflow
timeout, and job-specific API/subprocess limits are all bounded.

## UI states

Existing job responses now include `dispatch_status`, `dispatch_attempts`, and
`dispatch_error_message`. Persisted progress stages map naturally to:

- `queued` / `waiting_runner_capacity`: **Queued**
- `starting_runner`: **Starting runner**
- `processing` and processor-specific stages: **Processing**
- terminal job/resource states: **Completed** or **Failed**

These are database states, not simulated percentages.

## Safe activation sequence

1. Review and merge the workflow from a trusted branch.
2. Add the six GitHub Actions secrets.
3. Apply migration `20261031_0008` manually.
4. Add the Render token and non-secret dispatch settings while leaving dispatch
   disabled.
5. Deploy Render and verify normal authenticated API behavior.
6. With explicit approval, set `GITHUB_ACTIONS_DISPATCH_ENABLED=true`.
7. Create one small authorized validation/transcription job. Inspect the Actions
   run, persisted status, R2 object behavior, and logs for secret leakage.
8. Test a small approved render and inspect the downloaded MP4.
9. Stop the local worker only after the live test succeeds.

The local worker may remain available during rollout; leases prevent concurrent
processing, though a redundant Actions run can still consume billed minutes.

## Billing and operational limits

GitHub-hosted runners are ephemeral. Private repositories receive included
Actions minutes and storage according to the account's current GitHub plan;
usage beyond included allowances can be blocked or billed depending on account
spending settings. Ubuntu uses the standard Linux billing multiplier, but
FFmpeg and downloads can consume substantial wall time. Check **Settings >
Billing and licensing > Usage** before activation and set a spending limit or
budget appropriate for a zero/low-cost private beta.

The workflow has a 45-minute timeout, global concurrency of one, no schedule,
and no permanent runner. GitHub Actions can be delayed, cancelled, rate-limited,
or unavailable and is not guaranteed 24/7 SaaS compute. Large videos can exceed
runner disk, network, or time limits even when Howlix quotas allow them. Keep
private-beta file/duration quotas conservative.

Official references:

- [Workflow dispatch REST endpoint and token permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [GitHub-hosted runners](https://docs.github.com/en/actions/concepts/runners/github-hosted-runners)
- [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [Events triggered by `GITHUB_TOKEN`](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/automatic-token-authentication)

Do not claim end-to-end success until an API-created production job has started
an Actions run, completed against Supabase/R2, and produced an inspected result.
