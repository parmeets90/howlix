# Milestone 6 - secure private beta foundation

Milestone 6 adds authenticated identity and per-user authorization without changing the media pipeline.

## Supabase Auth setup

1. Enable email/password authentication and **Confirm email** in Supabase Auth.
2. Set the Site URL to `http://localhost:3000` for local work or the private production hostname.
3. Allow these redirects:
   - `http://localhost:3000/auth/callback`
   - `https://howlix.wolvesgang.digital/auth/callback`
4. For token-hash email templates, set the confirmation URL to `{{ .SiteURL }}/auth/confirm?token_hash={{ .TokenHash }}&type=email`.
5. Configure an SMTP provider before inviting beta users; the default development mail service is not a production delivery guarantee.
6. Prefer an asymmetric RS256 or ES256 signing key and wait for JWKS caches before rotation.
7. Copy only the project URL and publishable key to `NEXT_PUBLIC_*`; never expose a secret/service-role key.

Required local values:

```dotenv
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWT_ISSUER=https://PROJECT_REF.supabase.co/auth/v1
SUPABASE_JWKS_URL=https://PROJECT_REF.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_JWT_VERIFICATION_MODE=jwks
NEXT_PUBLIC_SUPABASE_URL=https://PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_your_key
```

## User flows

- `/auth/signup`: email/password registration and verification notice.
- `/auth/login`: verified-user login with cookie-backed SSR session.
- `/auth/forgot-password`: non-enumerating recovery request.
- `/auth/update-password`: recovery-session password update.
- `/dashboard/account`: authenticated identity, usage, and quota display.
- Logout clears the Supabase session and returns to login.

## API and ownership

All `/api/v1` application endpoints require a verified bearer token except `/health`. Object IDs are always combined with `owner_id`; clients never submit or override ownership. Private URLs are signed only after authorization. Tests use two distinct UUIDs to prove user B cannot retrieve user A's project/media or complete, cancel, or download user A's work.

## Migration and existing records

Revision `20261031_0006` adds owner columns and durable usage tables. It has been applied without modifying or deleting existing media records. Existing rows remain unowned until an operator explicitly claims named projects. See [security-model.md](security-model.md) for the dry-run and apply commands.

## Local startup

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd "D:\Claude Code Projects\howlix\backend"
.\.venv\Scripts\Activate.ps1
python -m app.worker
```

```powershell
cd "D:\Claude Code Projects\howlix\frontend"
npm run dev
```

Visit `http://localhost:3000/auth/signup`, verify the message through configured Supabase email delivery, then sign in.

## Private-beta acceptance limits

This milestone is suitable for a deliberately small, allowlisted beta after configuration and deployment review. It is not authorization to publish the application unrestricted. Billing, teams, administrator impersonation, social login, enterprise SSO, and public signup controls are out of scope.
