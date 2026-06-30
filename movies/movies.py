from __future__ import annotations

from typing import List, Optional

import httpx
from jose import jwt, JWTError
from fastapi import FastAPI, HTTPException, Path, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from prometheus_fastapi_instrumentator import Instrumentator

from config import (
    get_db, MovieTable, GenreTable, MovieGenreTable, MovieCastTable,
    KEYCLOAK_URL, KEYCLOAK_REALM,
)

TAGS_METADATA = [
    {
        "name": "Health",
        "description": "Service liveness check.",
    },
    {
        "name": "Movies",
        "description": (
            "Movie catalog — listing, search, create, update and soft-delete. "
            "Read operations are public. Write operations require an **admin** Bearer token."
        ),
    },
    {
        "name": "Genres",
        "description": "List all available genres. Public endpoint.",
    },
    {
        "name": "Cast",
        "description": (
            "Cast members for a movie. "
            "Reading is public; adding/removing requires an **admin** Bearer token."
        ),
    },
]

app = FastAPI(
    title="Movie Catalog API",
    version="2.0.0",
    root_path="/movies-service",
    description=(
        "REST API for movie catalog management, search, and retrieval.\n\n"
        "**Authentication flow (admin operations):**\n"
        "1. Obtain a token from the users-service `POST /login` or directly from Keycloak\n"
        "2. Click **Authorize** (🔒) and paste `Bearer <token>`\n\n"
        f"Token endpoint: `{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token`"
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

security = HTTPBearer(auto_error=False)

KEYCLOAK_REALM_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
KEYCLOAK_CERTS_URL = f"{KEYCLOAK_REALM_URL}/protocol/openid-connect/certs"

# ---------------------------------------------------------------------------
# Keycloak token validation
# ---------------------------------------------------------------------------

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
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        if payload.get("iss") != KEYCLOAK_REALM_URL:
            raise HTTPException(status_code=401, detail="Token issuer mismatch")
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


def require_admin(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Dependency: valida token Keycloak e exige role 'admin'."""
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=403, detail="Not authenticated")
    payload = decode_keycloak_token(credentials.credentials)
    realm_roles = payload.get("realm_access", {}).get("roles", [])
    if "admin" not in realm_roles:
        raise HTTPException(status_code=403, detail="Admin access required")
    return payload.get("preferred_username")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_movie_genres(movie_id: int, db: Session) -> List[str]:
    genres = db.query(GenreTable.name)\
        .join(MovieGenreTable, GenreTable.genre_id == MovieGenreTable.genre_id)\
        .filter(MovieGenreTable.movie_id == movie_id)\
        .all()
    return [g[0] for g in genres]

def get_movie_cast(movie_id: int, db: Session) -> List[dict]:
    cast = db.query(MovieCastTable)\
        .filter(MovieCastTable.movie_id == movie_id)\
        .all()
    return [{"cast_id": c.cast_id, "cast_name": c.cast_name, "role": c.role} for c in cast]

def build_movie_response(movie: MovieTable, db: Session) -> "MovieResponse":
    return MovieResponse(
        movie_id=movie.movie_id,
        movie_title=movie.movie_title,
        description=movie.description,
        imdb_url=movie.imdb_url,
        release_year=movie.release_year,
        runtime=movie.runtime,
        parental_rating=movie.parental_rating,
        poster_url=movie.poster_url,
        genres=get_movie_genres(movie.movie_id, db),
        cast=get_movie_cast(movie.movie_id, db),
        is_deleted=movie.is_deleted
    )

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CastMemberCreate(BaseModel):
    cast_name: str = Field(description="Name of the cast member")
    role: Optional[str] = Field(default=None, description="Role of the cast member")

class CastMemberResponse(BaseModel):
    cast_id: int
    cast_name: str
    role: Optional[str]

    class Config:
        from_attributes = True

class MovieCreate(BaseModel):
    movie_title: str = Field(description="Movie title")
    description: Optional[str] = Field(default=None, description="Movie description/synopsis")
    imdb_url: Optional[str] = Field(default=None, description="IMDb URL")
    release_year: int = Field(description="Release year (>= 1874)")
    runtime: Optional[int] = Field(default=None, description="Runtime in minutes")
    parental_rating: Optional[str] = Field(default=None, description="Parental rating (e.g., PG-13)")
    poster_url: Optional[str] = Field(default=None, description="Poster URL")
    genres: Optional[List[str]] = Field(default=None, description="List of genre names")

    @field_validator("release_year")
    @classmethod
    def validate_release_year(cls, v):
        if v < 1874:
            raise ValueError("Release year must be >= 1874")
        return v

    @field_validator("runtime")
    @classmethod
    def validate_runtime(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Runtime must be greater than 0")
        return v


class MovieUpdate(BaseModel):
    movie_title: Optional[str] = Field(default=None, description="New movie title")
    description: Optional[str] = Field(default=None, description="Movie description")
    imdb_url: Optional[str] = Field(default=None, description="IMDb URL")
    release_year: Optional[int] = Field(default=None, description="Release year")
    runtime: Optional[int] = Field(default=None, description="Runtime in minutes")
    parental_rating: Optional[str] = Field(default=None, description="Parental rating")
    poster_url: Optional[str] = Field(default=None, description="Poster URL")
    genres: Optional[List[str]] = Field(default=None, description="List of genre names")

    @field_validator("release_year")
    @classmethod
    def validate_release_year(cls, v):
        if v is not None and v < 1874:
            raise ValueError("Release year must be >= 1874")
        return v

    @field_validator("runtime")
    @classmethod
    def validate_runtime(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Runtime must be greater than 0")
        return v


class MovieResponse(BaseModel):
    movie_id: int
    movie_title: str
    description: Optional[str]
    imdb_url: Optional[str]
    release_year: int
    runtime: Optional[int]
    parental_rating: Optional[str]
    poster_url: Optional[str]
    genres: List[str] = []
    cast: List[CastMemberResponse] = []
    is_deleted: bool = False

    class Config:
        from_attributes = True

class GenreResponse(BaseModel):
    genre_id: int
    name: str

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Routes — Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# Routes — Movies
# ---------------------------------------------------------------------------

@app.get("/movies", response_model=List[MovieResponse], tags=["Movies"])
def list_movies(
    genre: Optional[str] = Query(default=None, description="Filter by genre name (partial match, case-insensitive)"),
    release_year: Optional[int] = Query(default=None, description="Filter by exact release year"),
    title: Optional[str] = Query(default=None, description="Filter by title (partial match, case-insensitive)"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results per page (1–100)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    List movies with optional filters and pagination.

    Only returns non-deleted movies. Filters can be combined.

    - **title**: partial, case-insensitive match
    - **genre**: partial, case-insensitive match on genre name
    - **release_year**: exact match
    - **limit** / **offset**: pagination (max 100 per page)
    """
    try:
        query = db.query(MovieTable).filter(MovieTable.is_deleted.is_(False))

        if title:
            query = query.filter(MovieTable.movie_title.ilike(f"%{title}%"))
        if release_year is not None:
            query = query.filter(MovieTable.release_year == release_year)
        if genre:
            query = query.join(MovieGenreTable, MovieTable.movie_id == MovieGenreTable.movie_id)\
                         .join(GenreTable, MovieGenreTable.genre_id == GenreTable.genre_id)\
                         .filter(GenreTable.name.ilike(f"%{genre}%"))

        movies = query.offset(offset).limit(limit).all()
        return [build_movie_response(m, db) for m in movies]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing movies: {e}")


@app.post(
    "/movies",
    response_model=MovieResponse,
    status_code=201,
    tags=["Movies"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Admin role required"},
    },
)
def create_movie(
    movie: MovieCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Create a new movie entry in the catalog.

    **Requires admin Keycloak token.**
    Genres must already exist in the database (see `GET /genres`).
    """
    try:
        new_movie = MovieTable(
            movie_title=movie.movie_title,
            description=movie.description,
            imdb_url=movie.imdb_url,
            release_year=movie.release_year,
            runtime=movie.runtime,
            parental_rating=movie.parental_rating,
            poster_url=movie.poster_url,
            is_deleted=False,
        )
        db.add(new_movie)
        db.flush()

        if movie.genres:
            for genre_name in movie.genres:
                genre = db.query(GenreTable).filter(GenreTable.name == genre_name).first()
                if genre:
                    db.add(MovieGenreTable(movie_id=new_movie.movie_id, genre_id=genre.genre_id))

        db.commit()
        db.refresh(new_movie)
        return build_movie_response(new_movie, db)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating movie: {e}")


@app.get("/movies/{movie_id}", response_model=MovieResponse, tags=["Movies"])
def get_movie(
    movie_id: int = Path(description="ID of the movie"),
    db: Session = Depends(get_db)
):
    """Get a movie by ID."""
    try:
        movie = db.query(MovieTable).filter(
            MovieTable.movie_id == movie_id,
            MovieTable.is_deleted.is_(False)
        ).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        return build_movie_response(movie, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving movie: {e}")


@app.put(
    "/movies/{movie_id}",
    response_model=MovieResponse,
    tags=["Movies"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Movie not found"},
    },
)
def update_movie(
    movie_id: int = Path(description="ID of the movie to update"),
    updates: MovieUpdate = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Update an existing movie.

    **Requires admin Keycloak token.**
    All fields are optional — only the provided fields are updated.
    If `genres` is provided, it **replaces** the existing genre list entirely.
    """
    try:
        movie = db.query(MovieTable).filter(
            MovieTable.movie_id == movie_id,
            MovieTable.is_deleted.is_(False)
        ).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")

        if updates.movie_title is not None:
            movie.movie_title = updates.movie_title
        if updates.description is not None:
            movie.description = updates.description
        if updates.imdb_url is not None:
            movie.imdb_url = updates.imdb_url
        if updates.release_year is not None:
            movie.release_year = updates.release_year
        if updates.runtime is not None:
            movie.runtime = updates.runtime
        if updates.parental_rating is not None:
            movie.parental_rating = updates.parental_rating
        if updates.poster_url is not None:
            movie.poster_url = updates.poster_url

        if updates.genres is not None:
            db.query(MovieGenreTable).filter(MovieGenreTable.movie_id == movie_id).delete()
            for genre_name in updates.genres:
                genre = db.query(GenreTable).filter(GenreTable.name == genre_name).first()
                if genre:
                    db.add(MovieGenreTable(movie_id=movie_id, genre_id=genre.genre_id))

        db.commit()
        db.refresh(movie)
        return build_movie_response(movie, db)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating movie: {e}")


@app.delete(
    "/movies/{movie_id}",
    status_code=204,
    tags=["Movies"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Movie not found"},
    },
)
def delete_movie(
    movie_id: int = Path(description="ID of the movie to delete"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Soft-delete a movie.

    **Requires admin Keycloak token.**
    The movie is **not** physically removed — `is_deleted` is set to `true`
    and the movie is hidden from all listing/search results.
    """
    try:
        movie = db.query(MovieTable).filter(MovieTable.movie_id == movie_id).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")
        movie.is_deleted = True
        db.commit()
        return
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting movie: {e}")


# ---------------------------------------------------------------------------
# Routes — Genres
# ---------------------------------------------------------------------------

@app.get("/genres", response_model=List[GenreResponse], tags=["Genres"])
def list_genres(db: Session = Depends(get_db)):
    """List all available genres."""
    try:
        return db.query(GenreTable).order_by(GenreTable.name).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing genres: {e}")


# ---------------------------------------------------------------------------
# Routes — Cast
# ---------------------------------------------------------------------------

@app.get("/movies/{movie_id}/cast", response_model=List[CastMemberResponse], tags=["Cast"])
def get_cast(
    movie_id: int = Path(description="ID of the movie"),
    db: Session = Depends(get_db)
):
    """Get the cast of a movie."""
    try:
        movie = db.query(MovieTable).filter(
            MovieTable.movie_id == movie_id,
            MovieTable.is_deleted.is_(False)
        ).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")

        return db.query(MovieCastTable).filter(MovieCastTable.movie_id == movie_id).all()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving cast: {e}")


@app.post(
    "/movies/{movie_id}/cast",
    response_model=CastMemberResponse,
    status_code=201,
    tags=["Cast"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Movie not found"},
    },
)
def add_cast_member(
    movie_id: int = Path(description="ID of the movie"),
    cast_member: CastMemberCreate = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Add a cast member to a movie.

    **Requires admin Keycloak token.**
    """
    try:
        movie = db.query(MovieTable).filter(
            MovieTable.movie_id == movie_id,
            MovieTable.is_deleted.is_(False)
        ).first()
        if not movie:
            raise HTTPException(status_code=404, detail="Movie not found")

        new_cast = MovieCastTable(
            movie_id=movie_id,
            cast_name=cast_member.cast_name,
            role=cast_member.role
        )
        db.add(new_cast)
        db.commit()
        db.refresh(new_cast)
        return new_cast
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error adding cast member: {e}")


@app.delete(
    "/movies/{movie_id}/cast/{cast_id}",
    status_code=204,
    tags=["Cast"],
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        403: {"description": "Admin role required"},
        404: {"description": "Cast member not found"},
    },
)
def remove_cast_member(
    movie_id: int = Path(description="ID of the movie"),
    cast_id: int = Path(description="ID of the cast member to remove"),
    db: Session = Depends(get_db),
    _: str = Depends(require_admin),
):
    """
    Remove a cast member from a movie.

    **Requires admin Keycloak token.**
    """
    try:
        cast = db.query(MovieCastTable).filter(
            MovieCastTable.cast_id == cast_id,
            MovieCastTable.movie_id == movie_id
        ).first()
        if not cast:
            raise HTTPException(status_code=404, detail="Cast member not found")

        db.delete(cast)
        db.commit()
        return
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error removing cast member: {e}")

Instrumentator().instrument(app).expose(app)
