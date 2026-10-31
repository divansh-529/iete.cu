# 08 — Free-Tier Hosting, Storage & Backups

> Free-tier terms change often. **Check each provider's current limits before deploying.** The figures below are indicative only. Blueprint §17.1 notes that no production site can be guaranteed to stay free forever, so this design keeps every provider swappable.

## Recommended setup

| Part | Recommended | Alternatives | Why |
|---|---|---|---|
| Frontend (static SPA) | **Cloudflare Pages** | Vercel, Netlify, GitHub Pages | Free static hosting with no bandwidth meter and a free `*.pages.dev` subdomain |
| Backend (FastAPI) | **Render** web service (free) | Koyeb, Fly.io, a university VM | Simple Docker or Python deploys. Free instances **sleep when idle**, so the first request takes a few seconds. |
| PostgreSQL | **Neon** (free) | Supabase Postgres | Managed Postgres with branching for staging. Watch the storage cap. |
| File storage | **Cloudflare R2** | Supabase Storage, Backblaze B2 | About 10 GB free with **no egress fees**, and S3-compatible, so the code is the same as for MinIO locally |
| Email (optional, later) | Brevo or Resend free tier | — | Not needed at launch because notifications are in-app only |
| CI / backups / cron | **GitHub Actions** | — | Free for public repos and generous for private ones |
| Domain | `*.pages.dev` + `*.onrender.com` | A custom domain (≈ ₹800–1,200/year) | A custom domain is the one likely cost |

### Cookies across domains
The SPA and the API run on different hosts on the free tiers. The options are:
1. **Recommended:** proxy `/api/*` through Cloudflare Pages Functions, or a `_redirects` rule, to the backend, so the browser sees a single origin and `SameSite=Lax` cookies work normally.
2. Alternatively, put both on subdomains of one custom domain (`app.example.org` and `api.example.org`).

Avoid `SameSite=None` third-party cookies, because browsers increasingly block them.

## Keeping within quotas
- **Files are the biggest risk.** Compress images on the client before upload (e.g. resize to 2,000 px longest edge), cap file sizes in settings, and show storage used on the admin dashboard.
- **Database:** keep files out of Postgres (metadata only). Prune `login_attempts` and read notifications older than 90 days with a nightly job.
- **Cold starts:** this is acceptable for an internal tool. During a busy event registration, a scheduled GitHub Action can ping `/api/health` every 10 minutes to keep the backend awake. Check the provider's terms before doing this.

## Backups (blueprint §15)
1. A **nightly GitHub Action** runs `pg_dump --format=custom`, encrypts the dump with `age` using a public key stored in repo secrets, and uploads it to a **separate** R2 bucket with a 30-day lifecycle rule.
2. **Files:** R2 object versioning, or a weekly `rclone sync` to a second bucket or provider.
3. **Restore drill:** at least once a semester, restore the latest dump into a Neon branch and run the smoke tests. Record the result in `backups_log`.
4. The private key for decrypting backups is held by the Chairperson and one technical lead, offline.

## Migration path (if limits are exceeded or prices change)
- The backend is a standard Docker image, so it can run on any container host or a ₹300–500/month VPS.
- Postgres is standard, so `pg_dump` and restore move it to any provider.
- Storage uses the S3 API, so switching provider means changing the endpoint and keys.
- Nothing in the code depends on a single vendor. Every endpoint and credential comes from environment variables.
