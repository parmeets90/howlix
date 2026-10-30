# Milestone 4 — AI moment discovery

Milestone 4 turns a completed timestamped transcript into a reviewed shortlist of 20–90 second clip recommendations. It does not render, crop, caption, or export video.

## Processing flow

1. `POST /api/v1/media/{asset_id}/discover-moments` verifies that the asset is ready and its transcript is complete.
2. One reproducible `moment_analysis_runs` row and one idempotent `moment_discovery` processing job are created.
3. The existing leased worker generates transcript windows in deterministic Python. It favors sentence endings and pauses, clamps every window to the source duration, and sends no video bytes to the analyzer.
4. Candidate excerpts are evaluated in bounded batches through the provider-neutral `MomentAnalyzer` interface.
5. Pydantic validates the structured response. Python calculates normalized weighted scores, refines boundaries against real word timestamps, removes temporal/text/topic duplicates, and rejects candidates below the configured threshold.
6. Recommendations are replaced atomically on a retry, so a crash cannot create duplicates.
7. The UI shows persisted job stages and lets a reviewer preview, edit title/boundaries, reset to AI boundaries, approve, or reject.

No minimum recommendation count is forced. A successful run may contain zero recommendations when the transcript is too short or lacks sufficiently strong standalone material.

## Providers and structured output

`GroqMomentAnalyzer` uses the existing backend-only `GROQ_API_KEY`. `GROQ_MOMENT_MODEL` is separate from the Whisper transcription model and defaults to `openai/gpt-oss-20b`.

Groq's supported structured-output models can change. The adapter uses strict JSON Schema only for the allowlist verified against [Groq Structured Outputs](https://console.groq.com/docs/structured-outputs). Other configured models use JSON Object Mode. Both paths are parsed and validated with the same Pydantic schema; invalid responses receive bounded retries and then fail clearly.

`DeterministicFixtureAnalyzer` is used by ordinary tests and offline evaluation. Future analyzers implement the same interface without changing worker business logic.

## Configuration

The important defaults are:

```dotenv
MOMENT_ANALYSIS_PROVIDER=groq
GROQ_MOMENT_MODEL=openai/gpt-oss-20b
MOMENT_MIN_DURATION_SECONDS=20
MOMENT_MAX_DURATION_SECONDS=90
MOMENT_TARGET_DURATION_SECONDS=55
MOMENT_MAX_CANDIDATES=24
MOMENT_MAX_RECOMMENDATIONS=10
MOMENT_MIN_EDITORIAL_SCORE=55
MOMENT_MAX_INPUT_CHARS=80000
MOMENT_BATCH_SIZE=12
MOMENT_MAX_API_REQUESTS=3
MOMENT_MAX_OUTPUT_TOKENS=6000
MOMENT_API_MAX_RETRIES=3
MOMENT_ANALYSIS_VERSION=1.0
MOMENT_PROMPT_VERSION=m4-v1
```

The batch, character, output-token, candidate, recommendation, and request limits bound cost. Provider token usage is stored when Groq returns it. Full transcripts are not logged by default.

## Database revision

Revision `20261030_0004` adds:

- `moment_analysis_runs`: asset/transcript identity, status, provider/model, prompt/analysis versions, settings, usage, errors, and completion time.
- `moment_candidates`: AI and editable boundaries, rank, title, hook, topic/category, deterministic score breakdown, explanation, uncertainty, context flag, and review status.

The migration is additive and preserves all Milestone 1–3 data. The processing-job type remains stored as a string, so `moment_discovery` needs no destructive enum migration.

## API

- `POST /api/v1/media/{asset_id}/discover-moments`
- `GET /api/v1/media/{asset_id}/moment-analysis`
- `GET /api/v1/media/{asset_id}/moments?review_status=pending|approved|rejected`
- `GET /api/v1/moments/{moment_id}`
- `PATCH /api/v1/moments/{moment_id}`
- `POST /api/v1/moments/{moment_id}/review`

Clients may edit only the suggested title and clip boundaries. Boundaries must satisfy configured duration limits, remain inside the video, and overlap transcript speech. AI scores and rationale are server-owned.

## Limitations

- Analysis is transcript-only. Visual quality is always unassessed.
- Speaker diarization is unavailable, so speaker changes cannot yet guide boundaries.
- Recommendations require human editorial review and do not predict virality.
- The local worker remains sequential for the target 8 GB laptop.
- Authentication is still absent; do not expose the application publicly without an access gate.

