# Aurivo

Enterprise AI-powered voice fraud & deepfake detection platform, built around
the [AASIST](https://github.com/clovaai/aasist) anti-spoofing model.

**Phase 1** (project structure, auth, design system) and **Phase 2**
(recording, upload pipeline, storage) are done. No ML inference yet — that
lands in Phase 3 once `ml/aasist` is in place (see `ml/README.md`).

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
rejection, running against an in-memory SQLite DB so it needs no services
running.

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
