from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

import os
import httpx
from jose import jwt, JWTError

from fastapi import FastAPI, HTTPException, Path, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from config import get_db, SubscriptionTable, user_client
from contextlib import asynccontextmanager
from users.users_client import UserGrpcClient

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

# grpc comunication
@asynccontextmanager
async def lifespan(app: FastAPI):
    await user_client.start()
    print("Review gRPC client started")
    yield
    await user_client.close()
    print("Review gRPC client closed")  

def get_user_client():
    return user_client

app = FastAPI(
    title="Subscriptions API",
    version="1.0.0",
    description="REST API for user subscriptions.",
    root_path="/subscriptions-service",
    lifespan=lifespan
)

class Subscription(BaseModel):
    subscription_id: int
    user_id: int
    type: str
    status: str
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateSubscription(BaseModel):
    type: Literal["free", "premium"]
    status: Literal["active", "pending", "cancelled", "expired"]
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str):
        allowed = {"free", "premium"}
        if v not in allowed:
            raise ValueError(f"type must be one of: {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str):
        allowed = {"active", "pending", "cancelled", "expired"}
        if v not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v


class UpdateSubscription(BaseModel):
    type: Optional[Literal["free", "premium"]] = None
    status: Optional[Literal["active", "pending", "cancelled", "expired"]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: Optional[str]):
        if v is None:
            return v
        allowed = {"free", "premium"}
        if v not in allowed:
            raise ValueError(f"type must be one of: {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]):
        if v is None:
            return v
        allowed = {"active", "pending", "cancelled", "expired"}
        if v not in allowed:
            raise ValueError(f"status must be one of: {allowed}")
        return v


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/users/{user_id}/subscription", response_model=Subscription)
async def create_subscription(
    user_id: int = Path(description="ID of the user"),
    subscription: CreateSubscription = None,
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        existing_subscription = (
            db.query(SubscriptionTable)
            .filter(SubscriptionTable.user_id == user_id)
            .first()
        )
        if existing_subscription:
            raise HTTPException(status_code=400, detail="User already has a subscription")

        if subscription.type != "free":
            if subscription.start_date is None or subscription.end_date is None:
                raise HTTPException(
                    status_code=400,
                    detail="Paid subscriptions must have start_date and end_date"
                )

        if subscription.start_date and subscription.end_date:
            if subscription.end_date < subscription.start_date:
                raise HTTPException(
                    status_code=400,
                    detail="end_date cannot be earlier than start_date"
                )

        new_subscription = SubscriptionTable(
            user_id=user_id,
            type=subscription.type,
            status=subscription.status,
            start_date=subscription.start_date,
            end_date=subscription.end_date
        )

        db.add(new_subscription)
        db.commit()
        db.refresh(new_subscription)
        return new_subscription

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating subscription: {e}")


@app.get("/users/{user_id}/subscription", response_model=Subscription)
async def get_subscription(
    user_id: int = Path(description="ID of the user"),
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        subscription = (
            db.query(SubscriptionTable)
            .filter(SubscriptionTable.user_id == user_id)
            .first()
        )

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        return subscription

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving subscription: {e}")


@app.put("/users/{user_id}/subscription", response_model=Subscription)
def update_subscription(
    user_id: int = Path(description="ID of the user"),
    subscription_data: UpdateSubscription = None,
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        subscription = (
            db.query(SubscriptionTable)
            .filter(SubscriptionTable.user_id == user_id)
            .first()
        )

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if subscription_data.type is not None:
            subscription.type = subscription_data.type
        if subscription_data.status is not None:
            subscription.status = subscription_data.status
        if subscription_data.start_date is not None:
            subscription.start_date = subscription_data.start_date
        if subscription_data.end_date is not None:
            subscription.end_date = subscription_data.end_date

        if subscription.type != "free":
            if subscription.start_date is None or subscription.end_date is None:
                raise HTTPException(
                    status_code=400,
                    detail="Paid subscriptions must have start_date and end_date"
                )

        if subscription.start_date and subscription.end_date:
            if subscription.end_date < subscription.start_date:
                raise HTTPException(
                    status_code=400,
                    detail="end_date cannot be earlier than start_date"
                )

        db.commit()
        db.refresh(subscription)
        return subscription

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating subscription: {e}")


@app.delete("/users/{user_id}/subscription")
async def delete_subscription(
    user_id: int = Path(description="ID of the user"),
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        subscription = (
            db.query(SubscriptionTable)
            .filter(SubscriptionTable.user_id == user_id)
            .first()
        )

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        db.delete(subscription)
        db.commit()
        return {"message": "Subscription deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting subscription: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting subscription: {e}")
    
Instrumentator().instrument(app).expose(app)
