# Milestone 1 delivery notes

## Objective

Create a credible, lightweight development foundation for Howlix without implementing video processing or AI behavior prematurely.

## User-facing behavior

- `/` presents the product direction, workflow, and clearly labels future analysis/export capabilities as planned.
- `/dashboard` loads projects from the real FastAPI API backed by Supabase Postgres. It never falls back to mock project cards.
- `/dashboard/new` creates a persisted project and offers local MP4, MOV, or WebM selection.
- Selecting a video shows its name and size plus an explicit notice that no upload has occurred.

## API contract

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/health` | Service readiness response |
| `GET` | `/api/v1/projects` | List projects, newest first |
| `POST` | `/api/v1/projects` | Validate and create a draft project |
| `GET` | `/api/v1/projects/{project_id}` | Retrieve one project or return a consistent 404 |

Errors use the following shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request could not be validated.",
    "details": []
  }
}
```

## Deliberate limitations

- The file picker does not upload, inspect, store, or process media.
- Project status remains `draft`; there is no false processing state.
- The application has no authentication and is appropriate only for local single-user development.
- A developer-provided Supabase connection string is required before runtime migrations or startup; it is never committed.
- Automated tests use an isolated temporary SQLite database and never write test records to Supabase.
- FFmpeg and Python 3.11 are documented prerequisites but are not installed automatically.
- No AI or paid service is connected.

## Acceptance checks

Run from PowerShell after completing the setup in the root README:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m pytest
cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

With both development servers running, create a project from `/dashboard/new` and confirm it appears after redirecting to `/dashboard` and after a browser refresh.

