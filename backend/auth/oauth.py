"""
OAuth client registry using Authlib's Starlette integration.

Authlib handles the OAuth2/OIDC dance (state, nonce, PKCE where applicable,
token exchange) — we just register providers and call `authorize_redirect` /
`authorize_access_token` from the route handlers in api/routes/auth.py.

Google's endpoints are hardcoded here rather than resolved via its
`.well-known/openid-configuration` discovery document. Using the discovery
URL means every single login redirect makes a live network call to Google
before it can even redirect the user — extra latency, and one more thing
that can go down. These endpoints are Google's long-stable, documented OIDC
values and don't need to be re-fetched:
https://developers.google.com/identity/openid-connect/openid-connect#discovery
"""
from authlib.integrations.starlette_client import OAuth

from backend.config import get_settings

settings = get_settings()

oauth = OAuth()

oauth.register(
    name="google",
    authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
    access_token_url="https://oauth2.googleapis.com/token",
    userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
    jwks_uri="https://www.googleapis.com/oauth2/v3/certs",
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    client_kwargs={"scope": "openid email profile"},
)

# GitHub's config would follow the same shape once GITHUB_CLIENT_ID/SECRET
# are set — GitHub isn't OIDC, so it needs its own userinfo fetch (via
# https://api.github.com/user) rather than an ID token, but the
# authorize_redirect / authorize_access_token calls in auth.py look the same.
