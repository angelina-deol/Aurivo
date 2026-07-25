FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-worker.txt ./
# CPU-only PyTorch — see requirements-worker.txt for why the extra index is
# needed to avoid pulling multi-GB CUDA packages with no GPU to use them.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-worker.txt \
       --extra-index-url https://download.pytorch.org/whl/cpu

COPY backend ./backend
COPY ml ./ml

# --pool=solo: Celery's default "prefork" pool forks worker processes, and
# PyTorch's native thread pool (OpenMP/MKL) is known to deadlock after a
# fork() — the classic symptom is a task that just hangs forever with no
# error. solo runs everything in a single process with no forking, which
# sidesteps the whole problem. This worker only ever processes one AASIST
# inference at a time regardless of pool type, so there's no concurrency
# lost by avoiding prefork here — scale by running more worker containers
# instead, not more processes within one.
# Run via `python -m celery`, not the bare `celery` console script.
#
# The bare `celery` command only adds the working directory to Python's
# import path *temporarily*, just long enough to load the app passed to
# -A — then explicitly removes it again (see Celery's
# celery.utils.imports.import_from_cwd). That means `backend.*` imports
# work fine (they happen during that window, while Celery loads
# backend.workers.celery_app), but a lazy `from ml.inference... import
# predict` inside a task body — which runs later, at actual task-execution
# time — fails with ModuleNotFoundError even though ml/ is correctly
# present at /app/ml. `python -m celery` instead adds the working directory
# permanently for the whole process, avoiding this entirely. Verified by
# reproducing both behaviors directly before pinning this down.
CMD ["python", "-m", "celery", "-A", "backend.workers.celery_app", "worker", "--loglevel=info", "--pool=solo"]
