from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

import httpx
from jose import jwt, JWTError
from fastapi import FastAPI, HTTPException, Path, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from prometheus_fastapi_instrumentator import Instrumentator

from config import (
    get_db, UserTable,
    KEYCLOAK_URL, KEYCLOAK_REALM,
    KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET,
)

TAGS_METADATA = [
    {
        "name": "Health",
        "description": "Service liveness check.",
    },
    {
        "name": "Auth",
        "description": (
            "Obtain a Keycloak access token. "
            "Use the returned `access_token` as `Bearer <token>` in the **Authorize** button above."
        ),
    },
    {
        "name": "Users",
        "description": (
            "User registration and profile management. "
            "Most write operations require a valid Bearer token. "
            "Admin operations additionally require the `admin` realm role."
        ),
    },
]

app = FastAPI(
    title="User Management API",
    version="2.0.0",
    root_path="/users-service",
    description=(
        "REST API for user registration and profile management.\n\n"
        "**Authentication flow:**\n"
        "1. `POST /login` with your username + password\n"
        "2. Copy the `access_token` from the response\n"
        "3. Click **Authorize** (🔒) and paste `Bearer <token>`\n\n"
        f"Token endpoint (direct): `{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token`"
    ),
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PASSWORD_REGEX = re.compile(
    r'^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{15,}$'
)
VALID_GENDERS = {"M", "F", "NB", "O"}

KEYCLOAK_REALM_URL    = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
KEYCLOAK_ADMIN_URL    = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}"
KEYCLOAK_TOKEN_URL    = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/token"
KEYCLOAK_USERINFO_URL = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/userinfo"
KEYCLOAK_CERTS_URL    = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/certs"

# ---------------------------------------------------------------------------
# Keycloak token validation
# ---------------------------------------------------------------------------


def _get_keycloak_public_keys() -> dict:
    """Fetch Keycloak JWKS (public keys) to verify token signatures."""
    try:
        resp = httpx.get(KEYCLOAK_CERTS_URL, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Keycloak: {e}")


def decode_keycloak_token(token: str) -> dict:
    """
    Validate a Keycloak-issued JWT using the realm's public key (RS256).
    Returns the decoded payload.
    """
    jwks = _get_keycloak_public_keys()
    try:
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=KEYCLOAK_CLIENT_ID,
            options={"verify_aud": False},  # audience varies; rely on issuer check
        )
        expected_issuer = KEYCLOAK_REALM_URL
        if payload.get("iss") != expected_issuer:
            raise HTTPException(status_code=401, detail="Token issuer mismatch")
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """Dependency: validates Keycloak token, returns the local user_id from the 'sub' claim."""
    payload = decode_keycloak_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    # 'sub' in Keycloak is the Keycloak UUID; we store a mapping via username
    # For compatibility we return the DB user_id resolved by preferred_username
    return payload  # return full payload; endpoints resolve user_id themselves


def _resolve_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    """Returns (db_user_id, is_admin) from a valid Keycloak token."""
    payload = decode_keycloak_token(credentials.credentials)
    username = payload.get("preferred_username")
    if not username:
        raise HTTPException(status_code=401, detail="Token missing 'preferred_username'")

    user = db.query(UserTable).filter(UserTable.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user not found in local DB")

    realm_roles = payload.get("realm_access", {}).get("roles", [])
    is_admin = "admin" in realm_roles or user.is_admin

    return user.user_id, is_admin


def _require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> int:
    user_id, is_admin = _resolve_user_from_token.__wrapped__(credentials, db)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


# ---------------------------------------------------------------------------
# Keycloak Admin helpers
# ---------------------------------------------------------------------------

def _keycloak_admin_token() -> str:
    """Obtain a service-account token for Keycloak Admin API calls."""
    resp = httpx.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
        },
        timeout=5,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=503, detail=f"Keycloak admin token error: {resp.text}")
    return resp.json()["access_token"]


def _create_keycloak_user(username: str, email: str, password: str, first_name: str = "", last_name: str = "") -> str:
    """
    Create a user in Keycloak realm and return the new Keycloak user ID.
    Called during POST /users registration.
    """
    admin_token = _keycloak_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    payload = {
        "username": username,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "emailVerified": True,
        "enabled": True,
        "requiredActions": [],
        "credentials": [{"type": "password", "value": password, "temporary": False}],
        "realmRoles": ["user"],
    }

    resp = httpx.post(f"{KEYCLOAK_ADMIN_URL}/users", json=payload, headers=headers, timeout=5)

    if resp.status_code == 409:
        raise HTTPException(status_code=409, detail="User already exists in Keycloak")
    if resp.status_code not in (201, 200):
        raise HTTPException(status_code=502, detail=f"Keycloak user creation failed: {resp.text}")

    # Keycloak returns the new user URL in Location header
    location = resp.headers.get("Location", "")
    keycloak_user_id = location.rstrip("/").split("/")[-1]
    return keycloak_user_id


def _delete_keycloak_user(username: str) -> None:
    """Remove a user from Keycloak by username."""
    admin_token = _keycloak_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    search = httpx.get(
        f"{KEYCLOAK_ADMIN_URL}/users",
        params={"username": username, "exact": "true"},
        headers=headers,
        timeout=5,
    )
    users = search.json()
    if not users:
        return  # nothing to delete

    kc_id = users[0]["id"]
    httpx.delete(f"{KEYCLOAK_ADMIN_URL}/users/{kc_id}", headers=headers, timeout=5)


def _assign_keycloak_role(username: str, role: str) -> None:
    """Assign (or remove) a realm role to a Keycloak user."""
    admin_token = _keycloak_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    # Find the user
    search = httpx.get(
        f"{KEYCLOAK_ADMIN_URL}/users",
        params={"username": username, "exact": "true"},
        headers=headers,
        timeout=5,
    )
    users = search.json()
    if not users:
        return
    kc_id = users[0]["id"]

    # Find the role representation
    role_resp = httpx.get(f"{KEYCLOAK_ADMIN_URL}/roles/{role}", headers=headers, timeout=5)
    if role_resp.status_code != 200:
        return
    role_rep = role_resp.json()

    # Assign role
    httpx.post(
        f"{KEYCLOAK_ADMIN_URL}/users/{kc_id}/role-mappings/realm",
        json=[role_rep],
        headers=headers,
        timeout=5,
    )


def _remove_keycloak_role(username: str, role: str) -> None:
    """Remove a realm role from a Keycloak user."""
    admin_token = _keycloak_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

    search = httpx.get(
        f"{KEYCLOAK_ADMIN_URL}/users",
        params={"username": username, "exact": "true"},
        headers=headers,
        timeout=5,
    )
    users = search.json()
    if not users:
        return
    kc_id = users[0]["id"]

    role_resp = httpx.get(f"{KEYCLOAK_ADMIN_URL}/roles/{role}", headers=headers, timeout=5)
    if role_resp.status_code != 200:
        return
    role_rep = role_resp.json()

    httpx.delete(
        f"{KEYCLOAK_ADMIN_URL}/users/{kc_id}/role-mappings/realm",
        json=[role_rep],
        headers=headers,
        timeout=5,
    )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    username: str = Field(description="Unique username")
    email: str = Field(description="User email address")
    password: str = Field(description="Password (min 15 chars, 1 uppercase, 1 number, 1 special)")
    firstName: str = Field(description="First name")
    lastName: str = Field(description="Last name")
    gender: Optional[str] = Field(default=None, description="Gender: M, F, NB or O")
    age: Optional[int] = Field(default=None, description="Age (optional)")
    termsAccepted: bool = Field(description="Must be true to register")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
            raise ValueError("Invalid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not PASSWORD_REGEX.match(v):
            raise ValueError(
                "Password must be at least 15 characters and contain at least "
                "one uppercase letter, one number, and one special character."
            )
        return v

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        if v is not None and v not in VALID_GENDERS:
            raise ValueError(f"Gender must be one of: {', '.join(VALID_GENDERS)}")
        return v

    @field_validator("termsAccepted")
    @classmethod
    def validate_terms(cls, v):
        if not v:
            raise ValueError("You must accept the terms and conditions to register.")
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = Field(default=None, description="New username")
    gender: Optional[str] = Field(default=None, description="Gender: M, F, NB or O")
    age: Optional[int] = Field(default=None, description="Age")

    @field_validator("gender")
    @classmethod
    def validate_gender(cls, v):
        if v is not None and v not in VALID_GENDERS:
            raise ValueError(f"Gender must be one of: {', '.join(VALID_GENDERS)}")
        return v


class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    gender: Optional[str]
    age: Optional[int]
    is_admin: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


@app.post("/login", response_model=TokenResponse, tags=["Auth"])
def login(credentials: LoginRequest):
    """Obtain a Keycloak access token with username and password."""
    resp = httpx.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "client_secret": KEYCLOAK_CLIENT_SECRET,
            "username": credentials.username,
            "password": credentials.password,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    data = resp.json()
    return TokenResponse(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        token_type=data["token_type"],
        expires_in=data["expires_in"],
    )


# ---------------------------------------------------------------------------
# Routes — Users
# ---------------------------------------------------------------------------

@app.get("/users", response_model=List[UserResponse], tags=["Users"])
def list_users(
    username: Optional[str] = None,
    gender: Optional[str] = None,
    age_min: Optional[int] = None,
    age_max: Optional[int] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    List users with optional filters and pagination.

    - **username**: partial match (case-insensitive)
    - **gender**: exact match — one of `M`, `F`, `NB`, `O`
    - **age_min** / **age_max**: inclusive age range
    - **limit**: max results (default 20)
    - **offset**: pagination offset (default 0)
    """
    try:
        query = db.query(UserTable)
        if username:
            query = query.filter(UserTable.username.ilike(f"%{username}%"))
        if gender:
            if gender not in VALID_GENDERS:
                raise HTTPException(status_code=400, detail=f"Gender must be one of: {', '.join(VALID_GENDERS)}")
            query = query.filter(UserTable.gender == gender)
        if age_min is not None:
            query = query.filter(UserTable.age >= age_min)
        if age_max is not None:
            query = query.filter(UserTable.age <= age_max)
        return query.offset(offset).limit(limit).all()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing users: {e}")


@app.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    tags=["Users"],
    responses={
        409: {"description": "Username or email already exists"},
        422: {"description": "Validation error (password too weak, invalid gender, etc.)"},
    },
)
def register_user(user: UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user.

    Creates the user profile in the local database **and** registers the identity in
    Keycloak so the user can immediately authenticate.

    **Password rules:** minimum 15 characters, at least one uppercase letter,
    one digit and one special character.

    **Gender values:** `M` (Male), `F` (Female), `NB` (Non-binary), `O` (Other).
    """
    try:
        if db.query(UserTable).filter(UserTable.email == user.email).first():
            raise HTTPException(status_code=409, detail="Email already registered")
        if db.query(UserTable).filter(UserTable.username == user.username).first():
            raise HTTPException(status_code=409, detail="Username already taken")

        # 1. Create identity in Keycloak
        _create_keycloak_user(user.username, user.email, user.password, user.firstName, user.lastName)

        # 2. Store profile in local DB (password field kept as placeholder — auth is in Keycloak)
        new_user = UserTable(
            username=user.username,
            email=user.email,
            password="managed-by-keycloak",
            gender=user.gender,
            age=user.age,
            is_admin=False,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering user: {e}")


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(user_id: int = Path(description="ID of the user"), db: Session = Depends(get_db)):
    """Get a user by ID."""
    try:
        user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user: {e}")


@app.put(
    "/users/{user_id}",
    response_model=UserResponse,
    tags=["Users"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Cannot update another user's profile"},
        404: {"description": "User not found"},
    },
)
def update_user(
    user_id: int = Path(description="ID of the user to update"),
    updates: UserUpdate = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Update a user's own profile.

    Requires a valid Keycloak Bearer token. A user can only update their own profile.
    Updatable fields: `username`, `gender`, `age`.
    """
    payload = decode_keycloak_token(credentials.credentials)
    username = payload.get("preferred_username")

    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username != username:
        raise HTTPException(status_code=403, detail="Cannot update another user's profile")

    try:
        if updates.username and updates.username != user.username:
            if db.query(UserTable).filter(UserTable.username == updates.username).first():
                raise HTTPException(status_code=409, detail="Username already taken")
            user.username = updates.username
        if updates.gender is not None:
            user.gender = updates.gender
        if updates.age is not None:
            user.age = updates.age
        user.updated_at = datetime.now()
        db.commit()
        db.refresh(user)
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating user: {e}")


@app.delete(
    "/users/{user_id}",
    status_code=204,
    tags=["Users"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Cannot delete another user's account"},
        404: {"description": "User not found"},
    },
)
def delete_user(
    user_id: int = Path(description="ID of the user to delete"),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Delete a user account.

    Requires a valid Keycloak Bearer token. A user can only delete their own account.
    The identity is also removed from Keycloak.
    """
    payload = decode_keycloak_token(credentials.credentials)
    username = payload.get("preferred_username")

    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.username != username:
        raise HTTPException(status_code=403, detail="Cannot delete another user's account")

    try:
        _delete_keycloak_user(user.username)
        db.delete(user)
        db.commit()
        return
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {e}")


@app.patch(
    "/users/{user_id}/admin",
    response_model=UserResponse,
    tags=["Users"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Caller does not have the admin role"},
        404: {"description": "User not found"},
    },
)
def set_admin(
    user_id: int = Path(description="ID of the user"),
    is_admin: bool = True,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Promote or revoke admin privileges.

    **Requires an admin Keycloak token.**
    - `is_admin=true` → assigns the `admin` realm role in Keycloak and sets `is_admin=true` in the DB
    - `is_admin=false` → removes the `admin` realm role and sets `is_admin=false` in the DB
    """
    payload = decode_keycloak_token(credentials.credentials)
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    if "admin" not in realm_roles:
        raise HTTPException(status_code=403, detail="Admin access required")

    user = db.query(UserTable).filter(UserTable.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Sync role in Keycloak
    if is_admin:
        _assign_keycloak_role(user.username, "admin")
    else:
        _remove_keycloak_role(user.username, "admin")

    user.is_admin = is_admin
    user.updated_at = datetime.now()
    db.commit()
    db.refresh(user)
    return user

Instrumentator().instrument(app).expose(app)
