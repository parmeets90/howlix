# Supabase database setup

Howlix uses Supabase as managed Postgres. It connects through SQLAlchemy and psycopg from the FastAPI backend; the browser does not receive a Supabase database password or direct database access.

## Create the connection

1. Create or open a Supabase project.
2. In the project dashboard, click **Connect**.
3. For typical Windows development, choose **Session pooler**. It works over IPv4 and supports persistent backend sessions.
4. Copy the complete URI rather than constructing the pooler hostname yourself.
5. Replace the password placeholder. URL-encode reserved password characters.
6. Add `sslmode=require` if the copied URI does not already include it.

From the repository root:

```powershell
Copy-Item .env.example .env
notepad .env
```

The value should follow this shape, using the exact username and host supplied by Supabase:

```dotenv
HOWLIX_DATABASE_URL=postgresql+psycopg://postgres.PROJECT_REF:URL_ENCODED_PASSWORD@POOLER_HOST:5432/postgres?sslmode=require
```

Do not use the example placeholders literally. Do not add this URI to `frontend/.env.local`, a `NEXT_PUBLIC_*` variable, source code, screenshots, or Git.

## Apply and inspect migrations

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m alembic current
```

Alembic creates the `projects` table and its native UUID primary key. Future schema changes must be expressed as new migrations; do not edit an already-applied migration after team or production use begins.

## Connection choice

- **Session pooler, port 5432:** recommended for this laptop and the persistent FastAPI development server, especially on IPv4-only networks.
- **Direct connection, port 5432:** appropriate for persistent deployments that have IPv6 or Supabase's IPv4 add-on.
- **Transaction pooler, port 6543:** intended for serverless or highly autoscaled runtimes and needs different pooling/prepared-statement handling. It is not the Milestone 1 default.

For stronger server verification later, download the Supabase CA certificate and move from `sslmode=require` to `sslmode=verify-full` with `sslrootcert` configured.
