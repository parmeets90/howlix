from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol
import uuid

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import Settings, get_settings


bearer_scheme = HTTPBearer(auto_error=False)
ALLOWED_ASYMMETRIC_ALGORITHMS = ("RS256", "ES256")


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    email: str | None
    role: str


class AuthTokenVerifier(Protocol):
    def verify(self, token: str) -> AuthenticatedUser: ...


class SupabaseJWTVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwks_client = (
            PyJWKClient(settings.supabase_jwks_url, cache_jwk_set=True, lifespan=600)
            if settings.supabase_jwks_url
            else None
        )

    def _claims_to_user(self, claims: dict) -> AuthenticatedUser:
        try:
            user_id = uuid.UUID(str(claims["sub"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Access token subject is invalid.") from exc
        role = str(claims.get("role", ""))
        if role != "authenticated":
            raise HTTPException(status_code=401, detail="Access token role is not authenticated.")
        email = claims.get("email")
        return AuthenticatedUser(user_id, str(email) if email else None, role)

    def _verify_with_jwks(self, token: str) -> dict:
        if self._jwks_client is None or not self.settings.supabase_jwt_issuer:
            raise HTTPException(status_code=503, detail="Supabase JWT verification is not configured.")
        header = jwt.get_unverified_header(token)
        if header.get("alg") not in ALLOWED_ASYMMETRIC_ALGORITHMS:
            raise HTTPException(status_code=401, detail="Access token algorithm is not allowed.")
        signing_key = self._jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=list(ALLOWED_ASYMMETRIC_ALGORITHMS),
            audience=self.settings.supabase_jwt_audience,
            issuer=self.settings.supabase_jwt_issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )

    def _verify_with_auth_server(self, token: str) -> dict:
        if not self.settings.supabase_url or not self.settings.supabase_publishable_key:
            raise HTTPException(status_code=503, detail="Supabase Auth verification is not configured.")
        response = httpx.get(
            f"{self.settings.supabase_url}/auth/v1/user",
            headers={
                "apikey": self.settings.supabase_publishable_key.get_secret_value(),
                "Authorization": f"Bearer {token}",
            },
            timeout=self.settings.auth_http_timeout_seconds,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=401, detail="Access token is invalid or expired.")
        return jwt.decode(
            token,
            options={"verify_signature": False, "require": ["exp", "iss", "aud", "sub"]},
            audience=self.settings.supabase_jwt_audience,
            issuer=self.settings.supabase_jwt_issuer,
        )

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            claims = (
                self._verify_with_jwks(token)
                if self.settings.supabase_jwt_verification_mode == "jwks"
                else self._verify_with_auth_server(token)
            )
            return self._claims_to_user(claims)
        except HTTPException:
            raise
        except (jwt.PyJWTError, httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access token is invalid or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc


@lru_cache
def get_auth_verifier() -> AuthTokenVerifier:
    return SupabaseJWTVerifier(get_settings())


def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    verifier: AuthTokenVerifier = Depends(get_auth_verifier),
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verifier.verify(credentials.credentials)
