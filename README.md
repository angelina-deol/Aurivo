# Aurivo

Enterprise AI-powered voice fraud & deepfake detection platform, built around
the [AASIST](https://github.com/clovaai/aasist) anti-spoofing model.

This is the **Phase 1** scaffold: project structure, authentication, and the
frontend design system foundation. No ML inference yet — that lands in
Phase 3 once `ml/aasist` is in place (see `ml/README.md`).

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
docker compose exec backend alembic revision --autogenerate -m "init"
docker compose exec backend alembic upgrade head
```

## Quickstart (without Docker)

**Backend**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# point DATABASE_URL at a local Postgres, or use sqlite for quick manual testing
uvicorn backend.main:app --reload
```

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

## Deliberately not in Phase 1

- OAuth (Google/GitHub) — config keys exist in `config.py`/`.env.example`
  but the actual provider flows aren't wired up yet.
- Any AASIST inference — `ml/` is a placeholder, `/investigations/*` routes
  return `501` on purpose.
- Celery worker container — no jobs to run yet; adding it now would just be
  dead weight.

See the full PRD for the Phase 2–6 roadmap.
