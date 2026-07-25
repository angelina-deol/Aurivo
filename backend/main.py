from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.api.routes import auth, health, investigations
from backend.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    description="Enterprise AI-powered voice fraud & deepfake detection platform.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Required by Authlib's Starlette OAuth client: it stashes the OAuth
# state/nonce here between the /google/login redirect and /google/callback.
# Uses a distinct secret from JWT_SECRET_KEY (see config.py).
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(investigations.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "status": "running", "docs": "/docs"}
