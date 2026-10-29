# Milestone 2.5 — Live integration checkpoint

Verified on October 29, 2026 against the dedicated Howlix Supabase schema and private `howlix-media` Cloudflare R2 bucket.

- Alembic revision `20261029_0002` was current before Milestone 3 work began.
- Disposable writes across projects, media assets, upload sessions, and processing jobs persisted and were cleaned up.
- Real multipart create, signed PUT, ListParts, completion, HeadObject, private signed GET, localhost CORS, and deletion passed.
- A disposable MP4 uploaded through the actual browser interface, reached `ready`, and produced FFprobe metadata: 3.000 seconds, 640×360, H.264/AAC, 24 fps.
- The project page displayed the metadata and the private preview loaded and played without browser console errors.
- The disposable Supabase rows, R2 object, local fixture, and browser artifacts were removed.

No CRM table, bucket, object, or credential was modified by this checkpoint.
