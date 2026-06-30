from __future__ import annotations

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "grpc"))

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

import grpc
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, status
from pydantic import BaseModel, Field

from grpc_files.watchlist_client import WatchlistGrpcClient
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


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return decode_keycloak_token(credentials.credentials)

# ─────────────────────────────────────────────────────────────────────────────
# gRPC clients
# ─────────────────────────────────────────────────────────────────────────────

GRPC_ADDRESS = os.getenv("WATCHLIST_GRPC_URL")
USER_GRPC_URL = os.getenv("USER_GRPC_URL")

grpc_client = WatchlistGrpcClient(GRPC_ADDRESS)
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

class WatchlistMovieOut(BaseModel):
    watchlist_id: int
    movie_id: int
    added_at: Optional[datetime] = None


class WatchlistOut(BaseModel):
    watchlist_id: int
    user_id: str
    title: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WatchlistDetailOut(WatchlistOut):
    movies: List[WatchlistMovieOut] = []


class WatchlistCreate(BaseModel):
    user_id: str = Field(..., min_length=1, examples=["42"])
    title: str = Field(..., min_length=1, examples=["My Favourites"])


class WatchlistUpdate(BaseModel):
    title: str = Field(..., min_length=1, examples=["Updated Title"])


class AddMovieBody(BaseModel):
    movie_id: int = Field(..., ge=1, description="ID of the movie to add")


# ─────────────────────────────────────────────────────────────────────────────
# gRPC error → HTTP exception
# ─────────────────────────────────────────────────────────────────────────────

_GRPC_TO_HTTP = {
    grpc.StatusCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    grpc.StatusCode.INVALID_ARGUMENT: status.HTTP_422_UNPROCESSABLE_ENTITY,
    grpc.StatusCode.ALREADY_EXISTS: status.HTTP_409_CONFLICT,
}


def _raise(exc: grpc.RpcError) -> None:
    code = _GRPC_TO_HTTP.get(exc.code(), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise HTTPException(status_code=code, detail=exc.details())


# ─────────────────────────────────────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────────────────────────────────────

watchlists_router = APIRouter(prefix="/watchlists", tags=["Watchlist"])
users_router = APIRouter(prefix="/users", tags=["Watchlist"])


@watchlists_router.get("", response_model=List[WatchlistOut], summary="List all watchlists")
async def list_watchlists():
    try:
        return await grpc_client.list_watchlists()
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.post("", response_model=WatchlistOut, status_code=201, summary="Create a watchlist")
async def create_watchlist(
    body: WatchlistCreate,
    user_client: UserGrpcClient = Depends(get_user_client),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(int(body.user_id))
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        return await grpc_client.create_watchlist(user_id=body.user_id, title=body.title)
    except HTTPException:
        raise
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.get("/{watchlist_id}", response_model=WatchlistDetailOut, summary="Get a watchlist with its movies")
async def get_watchlist(watchlist_id: int = Path(..., ge=1)):
    try:
        return await grpc_client.get_watchlist(watchlist_id)
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.put("/{watchlist_id}", response_model=WatchlistOut, summary="Update a watchlist title")
async def update_watchlist(body: WatchlistUpdate, watchlist_id: int = Path(..., ge=1), token: dict = Depends(require_auth)):
    try:
        return await grpc_client.update_watchlist(watchlist_id=watchlist_id, title=body.title)
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.delete("/{watchlist_id}", status_code=204, summary="Delete a watchlist")
async def delete_watchlist(watchlist_id: int = Path(..., ge=1), token: dict = Depends(require_auth)):
    try:
        await grpc_client.delete_watchlist(watchlist_id)
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.post(
    "/{watchlist_id}/movies",
    response_model=WatchlistMovieOut,
    status_code=201,
    summary="Add a movie to a watchlist",
)
async def add_movie(body: AddMovieBody, watchlist_id: int = Path(..., ge=1), token: dict = Depends(require_auth)):
    try:
        return await grpc_client.add_movie(watchlist_id=watchlist_id, movie_id=body.movie_id)
    except grpc.RpcError as e:
        _raise(e)


@watchlists_router.delete(
    "/{watchlist_id}/movies/{movie_id}",
    status_code=204,
    summary="Remove a movie from a watchlist",
)
async def remove_movie(watchlist_id: int = Path(..., ge=1), movie_id: int = Path(..., ge=1), token: dict = Depends(require_auth)):
    try:
        await grpc_client.remove_movie(watchlist_id=watchlist_id, movie_id=movie_id)
    except grpc.RpcError as e:
        _raise(e)


@users_router.get("/{user_id}/watchlist", response_model=List[WatchlistOut], summary="List watchlists for a user")
async def get_user_watchlists(
    user_id: str = Path(..., min_length=1),
    user_client: UserGrpcClient = Depends(get_user_client),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(int(user_id))
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        return await grpc_client.get_user_watchlists(user_id)
    except HTTPException:
        raise
    except grpc.RpcError as e:
        _raise(e)


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", ""),
    title="Watchlists Service",
    version="1.0.0",    
    description="REST API backed by the WatchlistService gRPC server.",
    lifespan=lifespan,
)

# ─────────────────────────────────────────────────────────────────────────────
# System Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Health Check")
async def health_check():
    return {
        "status": "ok",
        "service": "watchlists",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

app.include_router(watchlists_router)
app.include_router(users_router)

Instrumentator().instrument(app).expose(app)
