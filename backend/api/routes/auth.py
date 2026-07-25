from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.auth.oauth import oauth
from backend.auth.security import create_access_token, create_refresh_token, hash_password, verify_password
from backend.config import get_settings
from backend.database.models.user import User
from backend.database.session import get_db
from backend.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        auth_provider="local",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    subject = str(user.id)
    return TokenResponse(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: User = Depends(get_current_user)):
    # Stateless JWT logout: the client discards its tokens. A production
    # deployment would add the token's jti to a Redis denylist here.
    return None


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        # Covers state mismatch, user denying consent, expired flow, etc.
        return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/login?error=oauth_failed")

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/login?error=oauth_no_email")

    email = userinfo["email"]
    google_sub = userinfo["sub"]
    full_name = userinfo.get("name")
    avatar_url = userinfo.get("picture")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            auth_provider="google",
            provider_id=google_sub,
            is_verified=bool(userinfo.get("email_verified")),
        )
        db.add(user)
    else:
        # Keep the avatar in sync with Google on every login (their photo
        # can change), and link a matching local-password account rather
        # than creating a duplicate.
        user.avatar_url = avatar_url or user.avatar_url
        if user.auth_provider == "local":
            user.provider_id = user.provider_id or google_sub

    db.commit()
    db.refresh(user)

    if not user.is_active:
        return RedirectResponse(f"{settings.FRONTEND_BASE_URL}/login?error=account_disabled")

    subject = str(user.id)
    access_token = create_access_token(subject)
    refresh_token = create_refresh_token(subject)

    # Tokens go in the URL fragment, not query params: fragments never get
    # sent to the server on the next request and don't show up in server
    # access logs or the Referer header the way query params can.
    return RedirectResponse(
        f"{settings.FRONTEND_BASE_URL}/oauth/callback"
        f"#access_token={access_token}&refresh_token={refresh_token}"
    )
