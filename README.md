# Aurivo

Enterprise AI-powered voice fraud & deepfake detection platform, built around
the [AASIST](https://github.com/clovaai/aasist) anti-spoofing model.

**Phase 1** (project structure, auth, design system), **Phase 2** (recording,
upload pipeline, storage), and **Phase 3** (AASIST inference) are done.

## What's here

```
aurivo/
  frontend/     React + TypeScript + Vite + Tailwind, design system + auth pages
  backend/      FastAPI + SQLAlchemy + Alembic + JWT auth
  ml/           Placeholder for the AASIST wrapper (Phase 3)
  docker/       Dockerfiles for backend & frontend
  docker-compose.yml
  .github/workflows/ci.yml
```

## Quickstart (Docker)

```bash
cp .env.example .env
# edit .env, at minimum set a real JWT_SECRET_KEY

docker compose up --build
```

- Backend: http://localhost:8000 (interactive docs at `/docs`)
- Frontend: http://localhost:5173
- Postgres: localhost:5432 (user/pass/db: `aurivo`)
- Redis: localhost:6379 (idle until Phase 3's Celery worker comes online)

Run migrations once Postgres is up:

```bash
docker compose exec backend alembic -c backend/alembic.ini revision --autogenerate -m "init"
docker compose exec backend alembic -c backend/alembic.ini upgrade head
```

(The `-c backend/alembic.ini` is needed because the container's working
directory is `/app`, one level above where `alembic.ini` lives — same reason
`uvicorn backend.main:app` needs to run from `/app` too.)

## Quickstart (without Docker)

**Backend**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd ..
```

Point `DATABASE_URL` at a real Postgres, or use SQLite for quick local
testing (`DATABASE_URL=sqlite:///./backend/dev.db` in `.env` — this is
exactly what the test suite uses, so it's a proven path). Either way, create
the tables before starting the server for the first time:

```bash
alembic -c backend/alembic.ini revision --autogenerate -m "init"
alembic -c backend/alembic.ini upgrade head
uvicorn backend.main:app --reload
```

**All three of those commands must run from the project root** (the folder
*containing* `backend/`), not from inside `backend/` itself — every file
imports things like `from backend.config import ...`, which only resolves
if Python's working directory is the root. Running any of them from inside
`backend/` fails with `ModuleNotFoundError: No module named 'backend'` (for
`uvicorn`) and the server never starts — which looks like a browser
connection error, not a Python error, if you're testing something like
Google OAuth in a different terminal and the callback can't reach a server
that never came up.

If you skip the `alembic upgrade head` step, the server *will* start, but
any request that touches the database (registering, logging in, Google
OAuth's callback) fails with a 500 error because the tables don't exist yet.

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
pytest tests -v
```

Covers register → login → authenticated `/auth/me` → wrong-password
rejection, upload validation/rejection/ownership, Google OAuth login
redirect, the AASIST worker task's DB-update logic (mocking only the
torch-dependent prediction call), and the broker-dispatch-failure fallback
below — all runnable with no external services (no Postgres, Redis, or GPU
needed), 15 tests total.

The whole suite is hermetic: every test file uses its own isolated
in-memory SQLite database and never touches your real `.env`/`DATABASE_URL`
— so it passes the same way whether you run it from the project root or
from inside `backend/`, and whether or not `.env` exists. (An earlier
version of `test_worker_task.py` didn't follow this — it used the real
app-configured database connection, which broke if `.env` wasn't visible
from wherever you ran pytest. Fixed.)

**If uploads 500 with a Redis connection error:** `REDIS_URL` /
`CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` default to the Docker-only
hostname `redis`, which doesn't resolve outside Docker's network — same
issue as `DATABASE_URL`'s `postgres` default. Get Redis running locally
(`docker run -d -p 6379:6379 redis:7-alpine`, or a local install) and point
those three at `localhost` in `.env` instead. Note that even with Redis
unreachable, an upload now succeeds (202) with the investigation marked
`failed` rather than 500ing — see "Deliberately not in Phase 3" below for
why that fallback exists.

**If the Docker backend container fails on startup with `OSError: cannot
load library 'libsndfile.so'`:** an earlier version of `docker/
backend.Dockerfile` installed the Python `soundfile` package (used on every
upload to read WAV/FLAC metadata) without its system-level dependency,
`libsndfile1`. The PyPI wheel doesn't bundle a working binary on every
platform/architecture (this surfaced on arm64 builds, e.g. Docker Desktop
on Apple Silicon). Fixed — both `docker/backend.Dockerfile` and `docker/
worker.Dockerfile` now install `libsndfile1` via apt. Rebuild with `docker
compose up --build` to pick it up.

## Running the AASIST worker (Phase 3)

**Upgrading from before Phase 4? Run the migration again.** Phase 4 added
a new column (`spectrogram_storage_key` on `audio_metadata`). Same two
commands as always:
```bash
docker compose exec backend alembic -c backend/alembic.ini revision --autogenerate -m "add spectrogram column"
docker compose exec backend alembic -c backend/alembic.ini upgrade head
```

Uploads only get analyzed if a Celery worker is actually running:

```bash
# needs Redis running (docker compose up -d redis, or a local install)
pip install -r backend/requirements-worker.txt --extra-index-url https://download.pytorch.org/whl/cpu
python -m celery -A backend.workers.celery_app worker --loglevel=info --pool=solo
```

(Also run from the project root, same reason as everything else above.)
Without a worker running, uploads sit at `status: "processing"` forever —
the frontend polls but nothing will ever pick the job up.

**Use `python -m celery`, not the bare `celery` command — this one is
subtle and easy to get bitten by even with everything else configured
correctly.** The bare `celery` console script only adds the working
directory to Python's import path *temporarily*, just long enough to load
the app passed to `-A` — then explicitly removes it again. That means
`backend.*` imports work fine (they happen during that window), but
`ml.inference.aasist_wrapper` — imported lazily inside the task body, which
runs later at actual task-execution time — fails with `ModuleNotFoundError:
No module named 'ml'`, even when `ml/` is correctly present on disk and
correctly mounted in Docker. This can look exactly like a missing-volume
problem (task registers fine, `ls /app/ml` shows the folder, everything
*looks* right) when the actual cause is which command started Celery.
`python -m celery` keeps the working directory on the path for the whole
process and avoids this. `docker/worker.Dockerfile` already uses this form.

**`--pool=solo` matters, not optional:** Celery's default pool forks worker
processes, and PyTorch's native thread pool is known to deadlock after a
fork — the task just hangs forever with no error, no log line, nothing.
`solo` runs single-process with no forking, which avoids it entirely. This
worker only processes one AASIST inference at a time either way, so nothing
is lost — scale by running more worker containers, not more forked
processes inside one. `docker/worker.Dockerfile` already sets this.

## What's implemented in Phase 3

- [x] Real AASIST integration: `ml/aasist` is the actual upstream repo
      (cloned and read directly to get the scoring convention and expected
      input format right, not guessed), `ml/checkpoints` has the pretrained
      weights (they're bundled in the upstream repo — corrected a wrong
      assumption from Phase 1's README that they needed a manual download)
- [x] `ml/preprocessing/audio.py` — resample to 16kHz, downmix to mono,
      pad/tile to AASIST's fixed 64,600-sample window; tested directly
      against generated audio (non-16kHz input, short clips, stereo)
- [x] `ml/inference/aasist_wrapper.py` — loads the model once per worker
      process, runs a real forward pass, softmaxes the 2 output logits into
      an interpretable prediction/confidence/fraud-score
- [x] Celery worker (`backend/workers/`), split into its own Docker image
      (`docker/worker.Dockerfile`) so the FastAPI web process never needs to
      install torch
- [x] `/investigations/analyze` now enqueues real analysis; Investigation
      status flows `processing` → `complete`/`failed`
- [x] Frontend: the investigation detail page now polls while analysis is
      in flight and renders the real prediction/confidence/fraud score, or
      an honest failure message if the worker isn't running
- [x] Tests: worker task's DB-update logic, missing-row handling, and
      failure-path handling, all verified against a real (SQLite) database
- [x] Upload is resilient to the Celery broker being unreachable: the
      investigation is already committed by the time it's dispatched to
      Celery, so a broker connection failure marks it `failed` and returns
      202, rather than turning an already-successful upload into a 500
- [x] Task result-tracking disabled (`task_ignore_result=True`) — nothing in
      this app calls `.get()` on a task, since the frontend polls the
      Investigation row's status directly. This also means a broker outage
      fails in under a second instead of ~20-60s retrying an unused result
      backend connection.

### Known limitation

The actual PyTorch forward pass has not been run end-to-end in the
environment this was built in — no GPU was available there, and the
CPU-only PyTorch wheel (`download.pytorch.org`) wasn't reachable over that
sandbox's network. Everything up to the forward pass (preprocessing, config
parsing, checkpoint path resolution, the "model not ready" error path) was
tested directly; the forward pass itself needs to be verified on a real
machine. See `ml/README.md` for more detail.

### Update on the known limitation above

The forward pass has since been confirmed working end-to-end on a real
machine (Docker, Apple Silicon) — real predictions come back, not just
plumbing. Worth knowing: predictions currently tend toward extreme 0%/100%
confidence rather than nuanced middle values. That's consistent with
AASIST's known limitation as a raw-waveform model trained on a single 2019
dataset (ASVspoof2019 LA) — it wasn't exposed to modern voice-cloning
techniques or diverse real-world recording conditions during training, and
models tend to be overconfident on data outside what they were trained on
rather than appropriately uncertain. Current research points to
SSL-frontend variants (e.g. wav2vec2/XLSR + AASIST-style backend, often
called "Wav2Vec2-AASIST" in the literature) as meaningfully better at
generalizing to real-world audio — worth considering if prototype accuracy
becomes a priority, though that would be a deviation from the original
PRD's non-goal of not modifying the model architecture.

## What's implemented in Phase 4

- [x] `GET /investigations/{id}/audio` and `GET /investigations/{id}/
      spectrogram` — stream the original audio and a generated spectrogram
      image, both auth + ownership-checked (not a public URL — someone
      guessing an investigation ID can't listen to someone else's
      recording)
- [x] Real spectrogram generation (`ml/preprocessing/spectrogram.py`) — an
      actual STFT via scipy on the original full-duration audio (not the
      resampled/tiled 4-second window AASIST itself sees), rendered via
      matplotlib's headless Agg backend. Verified by visually inspecting a
      generated spectrogram against a known two-tone test signal — the
      expected two horizontal frequency bands show up correctly.
      Generation is a soft failure by design: if it breaks, the
      investigation still completes with a real fraud prediction, just
      without an attached spectrogram
- [x] Real interactive waveform player (`WaveformPlayer.tsx`) — decodes the
      actual audio via the Web Audio API and renders real peak data on a
      canvas (not a decorative animation), with click-to-seek, play/pause,
      and zoom
- [x] Spectrogram viewer (`SpectrogramView.tsx`) — the generated image with
      zoom and an approximate time/frequency hover readout
- [x] Confidence analytics (`ConfidenceGraph.tsx`) — a hand-built SVG donut
      showing the real/AI-generated split and fraud score, matching the
      app's own design system rather than a charting library's defaults
- [x] Tests: real spectrogram generation against a real generated WAV file
      (not mocked), and confirmation that a broken spectrogram doesn't
      block the investigation from completing — 18 tests total, all
      passing

### Deliberately not in Phase 4

Per the PRD's own roadmap, explainability (attention overlays, "suspicious
regions" timeline, LLM-generated summaries) is Phase 6, not Phase 4 — not
built yet, and not the same thing as what's here. What's here is the
report's waveform/spectrogram/confidence visualization; not yet an
explanation of *why* the model decided what it decided.

## What's implemented in Phase 1

- [x] Repo/folder structure matching the PRD
- [x] FastAPI app with CORS, health check, versioned API prefix
- [x] User model + Postgres via SQLAlchemy, Alembic migrations wired up
- [x] JWT auth: register, login, logout (stateless), `/auth/me`
- [x] Docker Compose: Postgres, Redis, backend, frontend
- [x] CI: backend pytest + frontend lint/build
- [x] Frontend design system: Tailwind tokens (cream/gold palette, rounded
      corners, soft shadows), Instrument Sans / Inter / IBM Plex Mono type
      system, Button/Card/Waveform primitives
- [x] Home, Login, Register pages

## What's implemented in Phase 2

- [x] `POST /investigations/analyze` — real upload endpoint: validates file
      type/size, extracts duration/sample rate/channels (via `soundfile` for
      WAV/FLAC, `mutagen` for MP3), stores the file, creates an
      `Investigation` + `AudioMetadata` row (status `awaiting_analysis` —
      honest about no ML worker existing yet)
- [x] `GET /investigations`, `GET /investigations/{id}`, `DELETE
      /investigations/{id}` — real, ownership-scoped (a user can't fetch
      another user's investigation)
- [x] Storage abstraction (`services/storage.py`): local disk by default,
      switches to S3-compatible storage automatically when
      `S3_ACCESS_KEY`/`S3_SECRET_KEY` are set — no AWS/MinIO account needed
      for local dev
- [x] Recording screen: live waveform + timer + pause/resume/cancel/stop,
      built on raw PCM capture (not MediaRecorder — its webm/opus output
      isn't one of the formats the backend accepts) and encoded to real WAV
      client-side
- [x] Upload screen: drag-and-drop WAV/FLAC/MP3, client-side metadata
      preview (duration/sample rate/channels) before submitting
- [x] Investigation detail page — shows stored metadata; if analysis hasn't
      run yet, says so plainly instead of faking a result
- [x] Route guard (`RequireAuth`) on `/record`, `/upload`,
      `/investigations/:id`
- [x] Tests: 10 passing (auth flow + upload validation/rejection/ownership)

## Deliberately not in Phase 2

- ~~OAuth (Google/GitHub) — still just config keys, no provider flow.~~
  **Google OAuth is now implemented — see below.** GitHub OAuth is still
  just config keys.
- Any AASIST inference — `ml/` is still a placeholder; investigations sit at
  `awaiting_analysis` forever until Phase 3's Celery worker exists.
- Chunked/resumable uploads, virus scanning, audio transcoding — the
  upload endpoint accepts a complete file in one request.
- Search/filter/pagination UI — the list endpoint supports `limit`/`offset`,
  but the History screen with search and filters is Phase 5.

See the full PRD for the Phase 3–6 roadmap.

## Google OAuth setup

1. In [Google Cloud Console](https://console.cloud.google.com): create/select
   a project, enable the People API, configure the OAuth consent screen
   (External, scopes `email`/`profile`/`openid`, add yourself as a test user
   while in Testing mode).
2. **Credentials → Create Credentials → OAuth client ID** (Web application):
   - Authorized JavaScript origins: `http://localhost:5173`, `http://localhost:8000`
   - Authorized redirect URI: `http://localhost:8000/api/v1/auth/google/callback`
3. Copy the Client ID/Secret into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   SESSION_SECRET_KEY=<a different random string than JWT_SECRET_KEY>
   ```
4. Restart the backend. The Login page's "Continue with Google" button now
   works end to end: redirect → Google consent → callback → account
   created/linked by email → JWTs issued → frontend `/oauth/callback` stores
   them and lands you on Home.

If someone already has a local password account under the same email,
signing in with Google links to that existing account rather than creating a
duplicate.

### What's implemented (Google OAuth)

- [x] Real `/auth/google/login` + `/auth/google/callback` (Authlib, using
      Google's stable OAuth endpoints directly rather than a live discovery
      fetch on every login — see `auth/oauth.py` for why)
- [x] Account creation on first Google login; linking to an existing
      local-password account with the same email
- [x] Tokens delivered to the frontend via URL fragment (never sent to the
      server or logged), consumed by `/oauth/callback`
- [x] Tested: login route redirects to Google with correct params, without
      needing real credentials or live network access in CI

### Deliberately not included yet

- GitHub OAuth — `auth/oauth.py` has a comment on where it'd slot in, same
  shape as Google minus the ID token (GitHub needs a separate
  `api.github.com/user` call for profile info).
- Account linking UI — linking happens automatically by email match; there's
  no "connect your Google account" flow inside a logged-in session yet.

## Profile icon / login state

Every page now has a shared header (`components/Layout.tsx`) with a profile
icon in the top right: your real Google photo if you signed in with Google,
an initials circle otherwise (or if the image fails to load), and a "Sign
in" link when logged out. Click it for a dropdown with sign-out.

Auth tokens are now persisted to `localStorage` (`hooks/useAuthStore.ts`)
rather than kept in memory only — that was a real bug fix, not just a nice-
to-have: without it, refreshing the page silently logged you out, which
would have made the profile icon meaningless as a way to confirm login
state. (Worth hardening to httpOnly cookies before this goes to production —
localStorage tokens are readable by any XSS that gets into the page.)
