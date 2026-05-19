# Deployment Walkthrough

Step-by-step guide to deploying CoreTex to **Railway** (backend + Redis +
worker) and **Vercel** (frontend). Every step you must perform yourself is
called out as `→ You:` so it's unambiguous what's manual vs automatic.

---

## Prerequisites

* A GitHub repository containing this codebase (push it before deploying).
* A free **Railway** account → <https://railway.app>
* A free **Vercel** account → <https://vercel.com>
* `gh` and `git` installed (optional but faster).

---

## Part 1 — Backend on Railway

Railway deploys two services from the same repo (API + RQ worker) and
attaches a managed Redis instance.

### 1.1 Push the repo

```bash
git init
git add .
git commit -m "Initial CoreTex deploy"
git branch -M main
git remote add origin https://github.com/<you>/coretex.git
git push -u origin main
```

→ **You:** create the GitHub repo via the web UI first if you haven't.

### 1.2 Create the Railway project

→ **You:** in the Railway dashboard, **New Project → Deploy from GitHub repo**,
pick your `coretex` repo. Railway auto-detects the `Dockerfile` and starts
building. This first build pulls ~1.5 GB of TeX Live — give it ~8 minutes.

When the build succeeds, Railway names the service something like
`coretex-production`. Open it.

### 1.3 Add a Redis plugin

→ **You:** in the project canvas: **New → Database → Add Redis**. Wait for it
to provision (≈30 s). Railway auto-injects `REDIS_URL` into your other
services, but our config uses `REDIS_HOST` / `REDIS_PORT`. Open the Redis
service's **Variables** tab, copy the **private network** hostname and port,
then go to the API service and add them as environment variables:

| Variable                | Value                                         |
| ----------------------- | --------------------------------------------- |
| `REDIS_HOST`            | `redis.railway.internal` (or whatever it shows) |
| `REDIS_PORT`            | `6379`                                        |
| `ENVIRONMENT`           | `production`                                  |
| `MAX_FILE_SIZE_MB`      | `20`                                          |
| `RATE_LIMIT_PER_MINUTE` | `10`                                          |
| `TEMP_URL_TTL_SECONDS`  | `300`                                         |

### 1.4 Create the worker service

The API and the worker are the same Docker image with different commands.

→ **You:** **New → GitHub Repo → same repo**, then on the new service:

* **Settings → Deploy → Custom Start Command** →
  `python -m app.queue.worker`
* **Variables** → copy the same `REDIS_HOST`, `REDIS_PORT`, etc. as above.

### 1.5 Expose the API publicly

→ **You:** on the API service: **Settings → Networking → Generate Domain**.
Railway gives you something like `https://coretex-production.up.railway.app`.

### 1.6 Smoke-test

```bash
curl https://<your-domain>/
# {"status":"ok","service":"word-to-latex"}
```

Upload a test file:

```bash
curl -X POST https://<your-domain>/convert?template=article \
  -F "file=@tests/golden/01_plain_text.docx"
# {"job_id":"...","status":"queued","message":"Conversion started"}
```

Poll `GET /status/{job_id}` until `"status": "finished"`.

---

## Part 2 — Frontend on Vercel

### 2.1 Connect the repo

→ **You:** Vercel dashboard → **Add New Project → Import** the same GitHub
repo. Set the **Root Directory** to `frontend/`. Vercel auto-detects Vite
from `frontend/vercel.json`.

### 2.2 Configure the API URL

→ **You:** in the Vercel project's **Settings → Environment Variables**:

| Variable          | Value                                                       |
| ----------------- | ----------------------------------------------------------- |
| `VITE_API_BASE`   | `https://<your-railway-domain>` (full URL, no trailing slash) |

### 2.3 Configure CORS

The backend currently allows `*` for development. → **You:** edit
`app/main.py` to lock CORS down to your Vercel domain before going public:

```python
origins = ["https://<your-vercel-domain>.vercel.app"]
```

Commit and push; Railway auto-redeploys.

### 2.4 First deploy

Push to `main` → Vercel builds and deploys automatically. Open the preview
URL it provides, drop a `.docx`, and confirm the full round-trip works.

---

## Part 3 — Continuous integration

The included workflow at `.github/workflows/ci.yml` runs on every PR:

* `backend` job: installs Pandoc, runs `ruff` + `pytest`.
* `frontend` job: `tsc --noEmit`, `eslint`, `vitest run`, `vite build`.

→ **You:** no action required — it activates as soon as your repo is on
GitHub. To require these checks before merge, in GitHub:
**Settings → Branches → Add rule for `main` → Require status checks**.

---

## Troubleshooting

| Symptom                                          | Fix                                                                                                  |
| ------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| `pdflatex: command not found` warnings in logs   | TeX Live wasn't installed in the image. Confirm `INSTALL_TEXLIVE` build-arg is `1` (default).         |
| Overleaf button gives 404                        | The 5-minute Redis TTL expired. Re-convert to regenerate the temp URL.                               |
| `RateLimitExceeded` from `/convert`              | Bump `RATE_LIMIT_PER_MINUTE`; default is 10/min/IP.                                                  |
| Worker fills memory on large `.docx`             | Confirm `MAX_FILE_SIZE_MB=20` is set; raise Railway plan if you need bigger uploads.                 |
| Frontend POSTs hit CORS in production            | Either set `VITE_API_BASE` correctly (Vercel) and add the Vercel origin to `origins` in `main.py`.   |
| Equation conversions all fail                    | Pandoc missing on the worker. Confirm `pandoc` is installed in the Dockerfile.                       |

---

## Cost expectations

* Railway free tier: ~$5 of usage credit/month. The API + worker + Redis
  comfortably fit, but the TeX Live image is large — watch your build
  minutes. Consider `INSTALL_TEXLIVE=0` if you don't need compile checks in
  production (the API still works without it).
* Vercel free tier: unlimited static deploys for the frontend.

---

## Part 5 — Enabling user accounts + history (optional)

CoreTex works fully stateless without any of this. Turn it on if you want
users to be able to sign up, log in, and re-download past conversions.

### 5.1 Add a Postgres database on Railway

1. Project canvas → **+ Create → Database → Add PostgreSQL**
2. Wait ~30 s for it to provision
3. Open the Postgres tile → **Variables tab** → copy `DATABASE_URL`

### 5.2 Wire env vars on the API + worker services

On **both** `coretex-api` and the worker service, **Variables** tab → add:

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` *(autocomplete-suggested)* |
| `JWT_SECRET` | a random hex string — generate with `openssl rand -hex 32` |
| `JWT_EXPIRES_HOURS` | `168` *(7 days; tune to taste)* |
| `FRONTEND_URL` | your Vercel URL, e.g. `https://core-tex.vercel.app` |
| `OAUTH_REDIRECT_BASE` | your Railway URL, e.g. `https://coretex-production.up.railway.app` |

Tables are created automatically on first boot (`Base.metadata.create_all`).

→ **You:** restart both services or push any commit to trigger a redeploy.
Visit `/` on the API — you should now see `"features": { "auth": true, "history": true, ... }` in the JSON response.

### 5.3 (Optional) Add Google sign-in

→ **You:** in [Google Cloud Console](https://console.cloud.google.com/apis/credentials):

1. **Create project** → name it CoreTex
2. **APIs & Services → OAuth consent screen** → External → fill app name + support email
3. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorised redirect URIs:
     - `http://localhost:8000/auth/google/callback` (dev)
     - `https://<your-railway-domain>/auth/google/callback` (prod)
4. Copy the **Client ID** and **Client secret**
5. Railway → API service → Variables:
   - `GOOGLE_OAUTH_CLIENT_ID` = (paste client ID)
   - `GOOGLE_OAUTH_CLIENT_SECRET` = (paste client secret)
6. Redeploy. The Google button appears on `/login` automatically.

### 5.4 (Optional) Add GitHub sign-in

→ **You:** in [GitHub Developer settings](https://github.com/settings/developers):

1. **OAuth Apps → New OAuth App**
2. Application name: CoreTex
3. Homepage URL: your Vercel URL
4. Authorization callback URL: `https://<your-railway-domain>/auth/github/callback`
5. Register → click **Generate a new client secret**
6. Railway → API service → Variables:
   - `GITHUB_OAUTH_CLIENT_ID` = (paste client ID)
   - `GITHUB_OAUTH_CLIENT_SECRET` = (paste client secret)
7. Redeploy. The GitHub button appears on `/login`.

> ⚠️ GitHub requires a verified primary email or the callback redirects to `?error=github_email_required`. Most users have one; tell them to check **Settings → Emails** if they hit this.

---

## Scaling constraints (known v1 limits)

The v1 deployment is sized for "a few hundred conversions a day on a hobby
project". These limits are deliberate trade-offs to fit on the Railway
free tier — they're not bugs, but you'll want to address them before
serving real production traffic.

### Single RQ worker → head-of-line blocking
A heavy conversion (150 equations + 20 MB images) can occupy the worker
for 5–15 seconds. With one worker, the next user's job waits in queue.

**Fix at scale**: upgrade Railway plan, deploy multiple worker replicas
(set Replicas > 1 on the worker service), and increase Redis memory.

### Figures stored in Redis (cap: ~50 MB)
The worker stages converted figures in Redis with a 5-minute TTL. This
is fast and free but Redis is RAM-resident — uploading 100 MB of figures
will fill the 50 MB Redis tier and start evicting other jobs' figures.

**Fix at scale**: write figures to S3 / Cloudflare R2 instead. The
worker uploads, the API generates pre-signed URLs for the Overleaf
snip_uri. ~30 lines of code change, swaps `redis_conn.setex(figures…)`
for an S3 client.

### Upload memory duplication
A 20 MB upload transiently consumes ~80–100 MB across the API + RQ
serialisation + worker boot. Fine for 5–10 concurrent uploads, painful
beyond that on Railway's 1 GB memory cap per service.

**Fix at scale**: stream uploads directly to S3 (presigned PUT), pass
only the S3 key through RQ. The worker reads from S3 instead of
receiving the bytes through the job payload.

### TeX Live image size
The Docker image with `texlive-latex-extra` weighs ~1.5 GB. Railway
caches layers, so subsequent builds are fast, but cold starts after
inactivity can take 30 seconds.

**Fix at scale**: pre-warm the worker with a min-replicas setting, or
use a smaller TeX Live subset if your templates don't need extras.

---

Done. You now have a publicly accessible CoreTex deployment.
