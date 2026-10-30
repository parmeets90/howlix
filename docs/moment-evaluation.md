# Moment discovery evaluation

The offline corpus at `backend/evaluation/fixtures/moment_evaluation.json` contains synthetic, version-controlled transcripts. It includes strong and weak hooks, incomplete stories, multiple useful moments, repeated topics, long pauses, English, Hindi/Punjabi, a very short transcript, and silence/no-usable-moment input.

Run it from `backend`:

```powershell
.\.venv\Scripts\python.exe evaluation\run_moment_evaluation.py
```

The runner uses `DeterministicFixtureAnalyzer`; it makes no network request and measures:

- Boundary validity against source duration
- 20–90 second duration compliance
- Remaining duplicate rate after temporal/text deduplication
- Deterministic ranking stability
- Selected topic diversity
- Temporal agreement with human-labeled good windows

The dataset is intentionally small and guards behavior rather than claiming production recommendation quality. Expand it only with synthetic or permission-cleared transcripts and version any label changes.

Ordinary pytest tests mock Groq. A paid live check exists separately and runs only when explicitly enabled:

```powershell
$env:RUN_MOMENT_GROQ_INTEGRATION_TESTS="true"
.\.venv\Scripts\python.exe -m pytest -m integration tests\test_moment_groq_integration.py
```

Human review remains the authoritative quality signal. Offline agreement metrics and editorial scores are not measurements of real social-platform performance.
