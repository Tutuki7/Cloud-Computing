from __future__ import annotations

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "grpc"))

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import grpc
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from grpc_files.badge_client import BadgeGrpcClient
from users.users_client import UserGrpcClient
import httpx
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from prometheus_fastapi_instrumentator import Instrumentator

# ---------------------------------------------------------------------------
# Keycloak auth
# ---------------------------------------------------------------------------

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "cc2526")
KEYCLOAK_REALM_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
KEYCLOAK_CERTS_URL = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/certs"

security = HTTPBearer()


def _get_keycloak_public_keys() -> dict:
    try:
        resp = httpx.get(KEYCLOAK_CERTS_URL, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Keycloak: {e}")


def decode_keycloak_token(token: str) -> dict:
    jwks = _get_keycloak_public_keys()
    try:
        payload = jwt.decode(token, jwks, algorithms=["RS256"], options={"verify_aud": False})
        if payload.get("iss") != KEYCLOAK_REALM_URL:
            raise HTTPException(status_code=401, detail="Token issuer mismatch")
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_keycloak_token(credentials.credentials)
    roles = payload.get("realm_access", {}).get("roles", [])
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# gRPC clients
# ─────────────────────────────────────────────────────────────────────────────

GRPC_ADDRESS = os.getenv("BADGE_GRPC_URL")
USER_GRPC_URL = os.getenv("USER_GRPC_URL")

grpc_client = BadgeGrpcClient(GRPC_ADDRESS)
user_client = UserGrpcClient(target=USER_GRPC_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await grpc_client.start()
    await user_client.start()
    yield
    await grpc_client.close()
    await user_client.close()


def get_user_client() -> UserGrpcClient:
    return user_client


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class BadgeOut(BaseModel):
    badge_id: int
    title: str
    milestone: int
    description: Optional[str] = None


class BadgeCreate(BaseModel):
    title: str = Field(..., min_length=1, examples=["First Review"])
    milestone: int = Field(..., ge=1, examples=[10])
    description: Optional[str] = Field(None, examples=["Awarded after 10 reviews"])


class BadgeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1)
    milestone: Optional[int] = Field(None, ge=1)
    description: Optional[str] = None


class UserBadgeOut(BaseModel):
    badge_id: int
    user_id: str
    awarded_at: Optional[datetime] = None
    badge: BadgeOut


class AwardBadgeBody(BaseModel):
    badge_id: int = Field(..., ge=1, description="ID of the badge to award")


# ─────────────────────────────────────────────────────────────────────────────
# gRPC error → HTTP exception
# ─────────────────────────────────────────────────────────────────────────────

_GRPC_TO_HTTP = {
    grpc.StatusCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    grpc.StatusCode.INVALID_ARGUMENT: status.HTTP_422_UNPROCESSABLE_ENTITY,
    grpc.StatusCode.ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    grpc.StatusCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
}


def _raise(exc: grpc.RpcError) -> None:
    code = _GRPC_TO_HTTP.get(exc.code(), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=code, detail=exc.details())


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

badges_router = APIRouter(prefix="/badges", tags=["Badges"])
users_router = APIRouter(prefix="/users", tags=["Badges"])


@badges_router.get("", response_model=List[BadgeOut], summary="List all badge definitions")
async def list_badges():
    try:
        return await grpc_client.list_badges()
    except grpc.RpcError as e:
        _raise(e)


@badges_router.post("", response_model=BadgeOut, status_code=201, summary="Create a badge definition")
async def create_badge(body: BadgeCreate, token: dict = Depends(require_admin)):
    try:
        return await grpc_client.create_badge(
            title=body.title,
            milestone=body.milestone,
            description=body.description or "",
        )
    except grpc.RpcError as e:
        _raise(e)


@badges_router.get("/{badge_id}", response_model=BadgeOut, summary="Get a badge definition")
async def get_badge(badge_id: int = Path(..., ge=1)):
    try:
        return await grpc_client.get_badge(badge_id)
    except grpc.RpcError as e:
        _raise(e)


@badges_router.put("/{badge_id}", response_model=BadgeOut, summary="Update a badge definition")
async def update_badge(body: BadgeUpdate, badge_id: int = Path(..., ge=1), token: dict = Depends(require_admin)):
    try:
        return await grpc_client.update_badge(
            badge_id=badge_id,
            title=body.title or "",
            milestone=body.milestone or 0,
            description=body.description or "",
        )
    except grpc.RpcError as e:
        _raise(e)


@badges_router.delete("/{badge_id}", status_code=204, summary="Delete a badge definition")
async def delete_badge(badge_id: int = Path(..., ge=1), token: dict = Depends(require_admin)):
    try:
        await grpc_client.delete_badge(badge_id)
    except grpc.RpcError as e:
        _raise(e)


@users_router.get("/{user_id}/badges", response_model=List[UserBadgeOut], summary="List badges awarded to a user")
async def get_user_badges(
    user_id: str = Path(..., min_length=1),
    user_client: UserGrpcClient = Depends(get_user_client),
):
    try:
        user_exists = await user_client.validate_user(int(user_id))
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        return await grpc_client.get_user_badges(user_id)
    except HTTPException:
        raise
    except grpc.RpcError as e:
        _raise(e)


@users_router.post("/{user_id}/badges", response_model=UserBadgeOut, status_code=201, summary="Award a badge to a user")
async def award_badge(
    body: AwardBadgeBody,
    user_id: str = Path(..., min_length=1),
    user_client: UserGrpcClient = Depends(get_user_client),
    token: dict = Depends(require_admin),
):
    try:
        user_exists = await user_client.validate_user(int(user_id))
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        return await grpc_client.award_badge(user_id=user_id, badge_id=body.badge_id)
    except HTTPException:
        raise
    except grpc.RpcError as e:
        _raise(e)


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", ""),
    title="Badges Service",
    version="1.0.0",
    description="REST API backed by the BadgeService gRPC server.",
    lifespan=lifespan,
)


@app.get("/health", tags=["System"], summary="Health Check")
async def health_check():
    return {
        "status": "ok",
        "service": "badges",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


app.include_router(badges_router)
app.include_router(users_router)

Instrumentator().instrument(app).expose(app)
