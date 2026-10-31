# Security model

Howlix Milestone 6 is a limited private-beta security foundation. It reduces obvious unauthorized-access risks but has not received an independent penetration test or production security review.

## Identity and sessions

Supabase Auth owns user credentials, email verification, recovery links, refresh-token rotation, and access-token issuance. Next.js uses `@supabase/ssr` with PKCE and cookies. `proxy.ts` refreshes sessions and redirects anonymous dashboard requests. Server layouts call `getClaims()` before rendering protected pages.

The browser sends the current access token as `Authorization: Bearer <token>` to FastAPI. No request body can select a user. FastAPI derives the UUID only from the verified JWT `sub` claim and requires role `authenticated`.

The default verifier uses the project's asymmetric JWKS and restricts algorithms to RS256/ES256. It validates signature, issuer, audience, expiry, and subject. Projects still using legacy HS256 should set `SUPABASE_JWT_VERIFICATION_MODE=auth-server`; the backend asks Supabase Auth to validate the token, then independently validates issuer, audience, expiry, and subject. The legacy JWT secret is never stored in Howlix.

Official references: [Supabase SSR](https://supabase.com/docs/guides/auth/server-side), [Supabase JWT verification](https://supabase.com/docs/guides/auth/jwts), and [JWT signing keys](https://supabase.com/docs/guides/auth/signing-keys).

## Authorization boundary

Every private entity carries `owner_id`: projects, media assets, upload sessions, processing jobs, transcripts, moment runs, moment candidates, and clip exports. Every API object lookup combines object ID with the authenticated owner ID. A cross-user object lookup returns 404 to avoid confirming that the identifier exists.

Signed multipart, preview, and download URLs are generated only after owner authorization. R2 keys remain server-generated and the bucket remains private. Signed URLs are short-lived bearer credentials; users should not share them.

Workers do not accept browser identity. They claim PostgreSQL jobs that already carry a non-null owner and verify that job, asset, transcript, analysis, moment, and export owners agree before processing. Ownerless legacy jobs are not claimed.

## Legacy data

Migration `20261031_0006` intentionally leaves existing development rows with `owner_id = NULL`. They are preserved but quarantined from authenticated API and worker access. The operator must name the correct Supabase user and each project explicitly:

```powershell
cd backend
python -m scripts.claim_legacy_projects --user-id "USER-UUID" --project-id "PROJECT-UUID"
python -m scripts.claim_legacy_projects --user-id "USER-UUID" --project-id "PROJECT-UUID" --apply
```

The first command is a rollback-only dry run. The claim propagates ownership through related records and recalculates stored-byte usage. It does not reconstruct historical monthly transcription or analysis usage.

## Quotas

FastAPI enforces configurable per-user project count, upload size, source duration, monthly transcription seconds, monthly AI analyses, active renders, and reserved storage bytes. Monthly and storage counters are PostgreSQL rows, updated in the same transaction as the operation they authorize. Upload bytes are reserved at initiation and released on abort, expiry, bad completed-object size, or rejected invalid media. Completed export bytes are added after media validation and before the export transaction commits.

These controls limit accidental or beta-user cost. They are not a billing ledger and do not replace provider-level spending limits and alerts.

## Secrets

- Browser-safe: Supabase URL, Supabase publishable key, FastAPI public URL.
- Backend-only: Postgres URI, R2 credentials, Groq key, any Supabase secret/service-role key.
- Howlix does not require or accept a service-role key in frontend code.
- Full transcript text and bearer tokens should not be logged.

## Remaining risks

- The application still relies on direct SQLAlchemy credentials with broad access to the dedicated `howlix` schema; database RLS is not the primary authorization layer.
- In-process request throttling is per backend instance. Durable quotas remain authoritative, but distributed abuse throttling is still required for multiple API replicas.
- JWT key revocation can be delayed by JWKS caching; keep access-token lifetimes short and follow Supabase rotation guidance.
- Email deliverability, compromised-account response, audit trails, malware scanning, CSP tuning, dependency remediation, backups, and incident procedures need deployment review.
- Private beta should remain behind an identity-aware edge allowlist despite application authentication.
