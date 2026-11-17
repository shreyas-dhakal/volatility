"""Session-token verification at the API boundary, independent of Next.js."""

import httpx
from clerk_backend_api.security import AuthenticateRequestOptions, authenticate_request
from fastapi import HTTPException

from galvanise.config import settings


def verified_subject(request):
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(401, "Sign in required")
    if (
        not settings.clerk_issuer
        or not settings.clerk_authorized_parties
        or not (settings.clerk_jwt_key or settings.clerk_secret_key)
    ):
        raise HTTPException(503, "Clerk server configuration is missing")
    try:
        # Explicit header-only request prevents the SDK from falling back to cookies.
        state = authenticate_request(
            httpx.Request(
                "GET", str(request.url), headers={"authorization": authorization}
            ),
            AuthenticateRequestOptions(
                secret_key=settings.clerk_secret_key or None,
                jwt_key=settings.clerk_jwt_key or None,
                authorized_parties=settings.clerk_authorized_parties,
                audience=settings.clerk_audience or None,
                accepts_token=["session_token"],
                clock_skew_in_ms=0,
            ),
        )
        claims = state.payload or {}
        subject = claims.get("sub")
        if (
            not state.is_signed_in
            or claims.get("iss") != settings.clerk_issuer
            or not isinstance(subject, str)
            or not subject.startswith("user_")
            or not isinstance(claims.get("sid"), str)
            or not claims["sid"]
            or not all(
                isinstance(claims.get(k), (int, float)) for k in ("exp", "iat", "nbf")
            )
        ):
            raise ValueError()
        return subject
    except Exception:  # noqa: BLE001 -- sanitize SDK errors at the identity boundary
        raise HTTPException(401, "Sign in required") from None
