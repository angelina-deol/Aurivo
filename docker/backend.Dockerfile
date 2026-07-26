FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
# --retries/--timeout: PyPI downloads can hit transient read-timeouts on
# slower connections (uvloop, psycopg2's build deps, etc. are multi-MB
# wheels) — retry instead of failing the whole build on one hiccup.
RUN pip install --no-cache-dir --retries 5 --timeout 120 -r requirements.txt

COPY backend ./backend

# Run as a dedicated non-root user, matching docker/worker.Dockerfile.
# mkdir + chown /app/uploads *before* USER, so the named volume mount
# inherits correct ownership the first time it initializes (Docker seeds a
# fresh named volume from the image's existing directory content).
RUN groupadd -r aurivo && useradd -r -g aurivo -d /app aurivo \
    && mkdir -p /app/uploads \
    && chown -R aurivo:aurivo /app
USER aurivo

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
