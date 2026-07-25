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

CMD ["celery", "-A", "backend.workers.celery_app", "worker", "--loglevel=info"]
