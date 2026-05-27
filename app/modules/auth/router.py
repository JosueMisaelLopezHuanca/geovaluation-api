import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/v2/auth", tags=["Auth"])

ADMIN_USER = os.getenv("CATASTRO_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("CATASTRO_ADMIN_PASSWORD", "change-this-local-password")
AUTH_SECRET = os.getenv("CATASTRO_AUTH_SECRET", "catastro-dev-secret-change-me")
TOKEN_TTL_MINUTES = int(os.getenv("CATASTRO_AUTH_TTL_MINUTES", "240"))


class LoginRequest(BaseModel):
    user: str = Field(min_length=4, max_length=80)
    password: str = Field(min_length=4, max_length=200)


class AuthSession(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: str
    role: str
    expires_at: datetime


def _json_b64(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_json_b64(value: str) -> dict:
    padding = "=" * (-len(value) % 4)
    raw = base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
    return json.loads(raw.decode("utf-8"))


def _signature(payload: str) -> str:
    return hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).hexdigest()


def _issue_admin_session() -> AuthSession:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)
    payload = _json_b64(
        {
            "sub": ADMIN_USER,
            "role": "Administrador",
            "exp": int(expires_at.timestamp()),
        }
    )
    token = f"{payload}.{_signature(payload)}"
    return AuthSession(
        access_token=token,
        user=ADMIN_USER,
        role="Administrador",
        expires_at=expires_at,
    )


def _verify_token(token: str) -> AuthSession:
    try:
        payload, signature = token.split(".", 1)
        expected_signature = _signature(payload)
        if not secrets.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")
        data = _decode_json_b64(payload)
        expires_at = datetime.fromtimestamp(int(data["exp"]), timezone.utc)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido.",
        ) from exc

    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesion expirada.",
        )

    return AuthSession(
        access_token=token,
        user=str(data.get("sub") or ADMIN_USER),
        role=str(data.get("role") or "Administrador"),
        expires_at=expires_at,
    )


@router.post("/login", response_model=AuthSession)
async def login(payload: LoginRequest):
    valid_user = secrets.compare_digest(payload.user.strip().lower(), ADMIN_USER.lower())
    valid_password = secrets.compare_digest(payload.password, ADMIN_PASSWORD)
    if not valid_user or not valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales invalidas.",
        )

    return _issue_admin_session()


@router.get("/me", response_model=AuthSession)
async def get_current_session(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autenticado.",
        )

    return _verify_token(authorization.split(" ", 1)[1].strip())
