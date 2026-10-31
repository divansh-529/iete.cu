# 09 — Going Live (free tier + GoDaddy domain)

This puts the portal on your own domain at no monthly cost, following [08-free-tier-hosting.md](08-free-tier-hosting.md).
Replace `yourdomain.in` with the domain you bought. The guide uses **`portal.yourdomain.in`** for the portal and keeps the bare domain free for a public forum website later. You can use the bare domain instead if you prefer.

```
visitor ──https──▶ portal.yourdomain.in  (Cloudflare Pages: the React app)
                        │  /api/*  forwarded by frontend/functions/api/[[path]].js
                        ▼  with a shared secret + the visitor's IP
                   iete-api.onrender.com  (Render: FastAPI, Docker)
                        │
                        ▼
                   Neon Postgres
```

The browser only ever sees `portal.yourdomain.in`, so login cookies work normally. The Render URL refuses anything that does not come through the portal, except `/api/health`.

You need four free accounts: **GitHub**, **Neon**, **Render** and **Cloudflare**. Sign up for the last three with GitHub, so they can see your repository.

---

## 1. Put the code on GitHub

Create an empty **private** repository on github.com (for example `iete-portal`), then from the project folder:

```powershell
git checkout -b main
git add .
git commit -m "Initial portal"
git remote add origin https://github.com/<you>/iete-portal.git
git push -u origin main
```

`.gitignore` already keeps `.env`, `.venv` and `node_modules` out of the repository.

## 2. Database: Neon

1. On neon.tech, create a project named `iete` with **Postgres 17**, in the region closest to India.
2. On the dashboard, choose **Connect**, turn **Connection pooling off**, and copy the connection string (`postgresql://…neon.tech/neondb?sslmode=require`). The app accepts it exactly as copied.

   Use the direct (non-pooled) string. The pooled one breaks the database driver's prepared statements.
3. From your own computer, create the tables and the first accounts in the new database:

```powershell
cd backend
$env:IETE_DATABASE_URL = "postgresql://...paste the Neon string..."
.venv\Scripts\alembic upgrade head
.venv\Scripts\python -m app.cli create-superadmin --email chair@yourdomain.in --name "Full Name"
.venv\Scripts\python -m app.cli seed-roles
.venv\Scripts\python -m app.cli seed-org
Remove-Item Env:IETE_DATABASE_URL     # back to your local database
```

## 3. Generate the shared secret

```powershell
backend\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Keep this value private. It is used in two places below. Never commit it.

## 4. Backend: Render

1. Go to **New → Web Service**, choose your GitHub repository, and fill in:
   - **Root Directory:** `backend`
   - **Language:** Docker (Render picks up `backend/Dockerfile`)
   - **Region:** Singapore
   - **Instance type:** Free
   - **Health Check Path** (under Advanced): `/api/health`
2. Add these **Environment Variables**:

   | Key | Value |
   |---|---|
   | `IETE_DATABASE_URL` | the Neon connection string |
   | `IETE_COOKIE_SECURE` | `true` |
   | `IETE_FRONTEND_BASE_URL` | `https://portal.yourdomain.in` (used in invite links) |
   | `IETE_PROXY_SECRET` | the secret from step 3 |

3. Choose **Create Web Service**. When it shows *Live*, open `https://<service-name>.onrender.com/api/health`. It should return `{"status":"ok"}`. Note this URL for step 6.

## 5. Move the domain's DNS to Cloudflare

This step is free. GoDaddy stays your registrar and you keep paying the yearly renewal there. Cloudflare only answers DNS.

1. On dash.cloudflare.com, choose **Add a domain**, enter `yourdomain.in`, and pick the **Free** plan.
2. Cloudflare copies your existing GoDaddy DNS records. If you use GoDaddy or another provider for **email**, check that the MX records are in the list before continuing.
3. Cloudflare shows two nameservers, such as `xxx.ns.cloudflare.com`. In GoDaddy, go to **My Products → your domain → DNS → Nameservers → Change Nameservers → "I'll use my own nameservers"**, enter both, and save.
4. Wait until Cloudflare marks the domain **Active**. This usually takes under an hour and can take up to 24 hours.

## 6. Frontend: Cloudflare Pages

1. Go to **Workers & Pages → Create → Pages → Connect to Git** and choose the repository:
   - **Framework preset:** None
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Root directory:** `frontend`
2. Under **Environment variables (Production)**, add:

   | Variable | Value |
   |---|---|
   | `BACKEND_URL` | `https://<service-name>.onrender.com` |
   | `PROXY_SECRET` | the secret from step 3. Choose **Encrypt**. |
   | `NODE_VERSION` | `24` |

3. Choose **Save and Deploy**. The site appears at `https://<project>.pages.dev`. Logging in there should already work.
4. Open the project's **Custom domains** tab, choose **Set up a custom domain**, and enter `portal.yourdomain.in`. Cloudflare creates the DNS record and the HTTPS certificate.

## 7. Keep the backend awake (optional, recommended)

Render's free plan sleeps after 15 idle minutes, and the next visitor waits up to a minute. `.github/workflows/keepalive.yml` pings the health check every 10 minutes. To turn it on, open GitHub **Settings → Secrets and variables → Actions → Variables** and add:

`BACKEND_HEALTH_URL` = `https://<service-name>.onrender.com/api/health`

One always-on service fits inside Render's 750 free hours a month. GitHub pauses scheduled workflows after 60 days with no commits, so re-enable it from the Actions tab if that happens.

## 8. Check it

- `https://portal.yourdomain.in` shows the sign-in page with the padlock.
- Sign in as the Chairperson.
- `https://<service-name>.onrender.com/api/auth/me` returns 403. This is correct, because the backend is only reachable through the portal.

## Updating

Push to `main`. Cloudflare Pages rebuilds the site, and Render rebuilds the backend and runs any new migrations on start.

## Before real data goes in

- **Backups:** the nightly encrypted `pg_dump` from [08 §Backups](08-free-tier-hosting.md#backups-blueprint-15) is not built yet. Until it is, Neon's built-in point-in-time restore (a short window on the free plan) is the only safety net.
- **Free limits** (check current terms): Neon about 0.5 GB storage, Pages Functions 100,000 requests a day, Render 750 hours a month. All are far above what the forum needs today.
