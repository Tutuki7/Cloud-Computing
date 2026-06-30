from __future__ import annotations

import os

from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Path, Query, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from config import get_db, RatingTable, user_client, movie_client, ReviewSentiment, Topic, RatingTopic, publish_review
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy import func
from contextlib import asynccontextmanager
from users.users_client import UserGrpcClient
from movies.movies_client import MovieGrpcClient
import httpx
from jose import jwt, JWTError

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
    await movie_client.start()
    print("Review gRPC client started")
    yield
    await user_client.close()
    await movie_client.close()
    print("Review gRPC client closed")

def get_user_client():
    return user_client

def get_movie_client():
    return movie_client

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", ""),
    title="Review System API",
    version="1.0.0",
    description="An API for managing movie ratings, allowing users to submit ratings and retrieve them based on various criteria.",
    lifespan=lifespan
)

# Models
class Rating(BaseModel):
    rating_id: int = Field(unique=True, notnull=True, description="Unique identifier for the rating")
    user_id: int = Field(unique=True, notnull=True, description="Unique identifier for the user who provided the rating")
    movie_id: int = Field(unique=True, notnull=True, description="Unique identifier for the movie being rated")
    rating: float = Field(notnull=True, ge=1.0, le=5.0, description="Rating value between 1 and 5")
    review: Optional[str] = Field(None, description="Optional text review accompanying the rating")
    created_at: datetime = Field(default_factory=datetime.now(), description="Timestamp of when the rating was provided")
    updated_at: datetime = Field(default_factory=datetime.now(), description="Timestamp of the last update to the rating")
    tag: Optional[str] = Field(None, description="Optional list of tags associated with the rating")

    class Config:
        from_attributes = True

class RatingCreate(BaseModel):
    user_id: int = Field(unique=True, notnull=True, description="Unique identifier for the user who provided the rating")
    movie_id: int = Field(unique=True, notnull=True, description="Unique identifier for the movie being rated")
    rating: float = Field(notnull=True, ge=0.0, le=5.0, description="Rating value between 1 and 5")
    review: Optional[str] = Field(None, description="Optional text review accompanying the rating")
    tag: Optional[str] = Field(None, description="Optional tag associated with the rating")

class UpdateRating(BaseModel):
    rating: Optional[float] = Field(None, ge=0.0, le=5.0, description="Updated rating value between 1 and 5")
    review: Optional[str] = Field(None, description="Updated text review accompanying the rating")
    tag: Optional[str] = Field(None, description="Updated tag associated with the rating")

class MovieRating(BaseModel):
    user_id: int = Field(unique=True, notnull=True, description="Unique identifier for the user who provided the rating")
    rating: float = Field(notnull=True, ge=1.0, le=5.0, description="Rating value between 1 and 5")
    review: Optional[str] = Field(None, description="Optional text review accompanying the rating")
    tag: Optional[str] = Field(None, description="Optional tag associated with the rating")

class RatingSummary(BaseModel):
    movie_id: int = Field(unique=True, notnull=True, description="Unique identifier for the movie")
    total_reviews: int = Field(description="Amount of reviews of a movie")
    sentiment_breakdown: Dict[str, int] = Field(description="Breakdown of sentiments (e.g., {'positive': 10, 'negative': 2})")
    top_topics: List[str] = Field(description="List of the most frequently mentioned topics (up to 5)")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _update_movie_avg(movie_id: int, db: Session, movie_client: MovieGrpcClient):
    """Recalculates avg_rating for a movie from local ratings and pushes it to movies-service via gRPC."""
    avg = db.query(func.round(func.avg(RatingTable.rating), 2))\
            .filter(RatingTable.movie_id == movie_id, RatingTable.is_quarantined == False)\
            .scalar() or 0.0
    await movie_client.update_avg_rating(movie_id, float(avg))


# Routes
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/ratings", response_model=Rating, status_code=201)
async def create_rating(
    rating_create: RatingCreate,
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        query = db.query(RatingTable)
        rating_exists = (query
                        .filter(RatingTable.user_id == rating_create.user_id, 
                                RatingTable.movie_id == rating_create.movie_id,
                                RatingTable.is_quarantined == False)         
                        .first())
        
        if rating_exists:
            update_rating = rating_create.model_dump(exclude_unset=True)

            if not update_rating:
                raise HTTPException(status_code=422, detail="No fields provided for update")

            for field, value in update_rating.items():
                setattr(rating_exists, field, value)
            
            rating_exists.updated_at = datetime.now()
            
            db.commit()
            db.refresh(rating_exists)
            await _update_movie_avg(rating_exists.movie_id, db, movie_client)

            if rating_exists.review:
                try:
                    publish_review(rating_exists.rating_id, rating_exists.review)
                except Exception as e:
                    print(f"Failed to publish to Pub/Sub: {e}")

            return rating_exists

        user_exists = await user_client.validate_user(rating_create.user_id)
        movie_exists = await movie_client.validate_movie(rating_create.movie_id)

        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        if not movie_exists:
            raise HTTPException(status_code=404, detail="Movie does not exist")
        
        new_rating = RatingTable(
            user_id=rating_create.user_id,
            movie_id=rating_create.movie_id,
            rating=rating_create.rating,
            review=rating_create.review,
            tag=rating_create.tag
        )

        db.add(new_rating)
        db.commit()
        db.refresh(new_rating)
        await _update_movie_avg(new_rating.movie_id, db, movie_client)

        if new_rating.review:
            try:
                publish_review(new_rating.rating_id, new_rating.review)
            except Exception as e:
                print(f"Failed to publish to Pub/Sub: {e}")

        return new_rating
    except HTTPException:
        raise 
    except Exception as e:
        print(f"Error creating rating: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating rating")

@app.get("/ratings", response_model=List[Rating])
async def get_ratings(
    user_id: Optional[int] = Query(None, description="Filter ratings by user ID"),
    movie_id: Optional[int] = Query(None, description="Filter ratings by movie ID"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a minimum rating value"),
    max_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a maximum rating value"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(RatingTable).filter(RatingTable.is_quarantined == False)
        if user_id is not None:
            query = query.filter(RatingTable.user_id == user_id)
        if movie_id is not None:
            query = query.filter(RatingTable.movie_id == movie_id)
        if min_rating is not None:
            query = query.filter(RatingTable.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(RatingTable.rating <= max_rating)
        
        ratings = query.offset(skip).limit(limit).all()
        if not ratings:
            raise HTTPException(status_code=404, detail="No ratings match criteria")

        return ratings
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving ratings: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving ratings")

@app.get("/ratings/{rating_id}", response_model=Rating)
def get_rating(rating_id: int = Path(notnull=True, description="The ID of the rating to retrieve"), db: Session = Depends(get_db)):
    try:
        rating = db.query(RatingTable).filter(RatingTable.rating_id == rating_id, RatingTable.is_quarantined == False).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")
        return rating
    except HTTPException:
        raise 
    except Exception as e:
        print(f"Error retrieving rating: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving rating")
    
@app.put("/ratings/{rating_id}")
async def update_rating(
    rating_id: int = Path(description="The ID of the rating to update"),
    rating_update: UpdateRating = None,
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        rating = db.query(RatingTable).filter(RatingTable.rating_id == rating_id, RatingTable.is_quarantined == False).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")

        # Ownership check: admins can update any rating; regular users only their own
        roles = token.get("realm_access", {}).get("roles", [])
        if "admin" not in roles:
            # preferred_username in token; ownership enforced via user_id in JWT's "user_id" claim if present
            token_user_id = token.get("user_id")
            if token_user_id is not None and int(token_user_id) != rating.user_id:
                raise HTTPException(status_code=403, detail="Cannot update another user's rating")
        update_rating = rating_update.model_dump(exclude_unset=True)
        if not update_rating:
            raise HTTPException(status_code=422, detail="No fields provided for update")

        for field, value in update_rating.items():
            setattr(rating, field, value)
        
        rating.updated_at = datetime.now()
        
        db.commit()
        db.refresh(rating)
        await _update_movie_avg(rating.movie_id, db, movie_client)


        if rating.review:
            try:
                publish_review(rating.rating_id, rating.review)
            except Exception as e:
                print(f"Failed to publish to Pub/Sub: {e}")

        return {"status_code": 200, "detail": "Rating updated successfully"}
    except HTTPException:
        raise 
    except Exception as e:
        print(f"Error updating rating: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating rating")

@app.delete("/ratings/{rating_id}")
async def delete_rating(
    rating_id: int = Path(description="The ID of the rating to delete"),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        rating = db.query(RatingTable).filter(RatingTable.rating_id == rating_id, RatingTable.is_quarantined == False).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")

        # Ownership check: admins can delete any rating; regular users only their own
        roles = token.get("realm_access", {}).get("roles", [])
        if "admin" not in roles:
            token_user_id = token.get("user_id")
            if token_user_id is not None and int(token_user_id) != rating.user_id:
                raise HTTPException(status_code=403, detail="Cannot delete another user's rating")

        movie_id = rating.movie_id  # guardar antes de apagar
        db.query(RatingTopic).filter(RatingTopic.rating_id == rating_id).delete()
        db.query(ReviewSentiment).filter(ReviewSentiment.rating_id == rating_id).delete()

        db.delete(rating)
        db.commit()
        await _update_movie_avg(movie_id, db, movie_client)

        return {"status_code": 200, "detail": "Rating deleted successfully"}
    except HTTPException:
        raise 
    except Exception as e:
        print(f"Error deleting rating: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting rating")   

@app.post("/movies/{movie_id}/ratings", response_model=Rating, status_code=201)
async def create_movie_rating(
    movie_id: int = Path(description="The ID of the movie being rated"),
    rating_create: MovieRating = None,
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        rating_data = RatingCreate(
            user_id=rating_create.user_id,
            movie_id=movie_id,
            rating=rating_create.rating,
            review=rating_create.review,
            tag=rating_create.tag
        )

        # create_rating já chama _update_movie_avg internamente
        return await create_rating(rating_data, user_client, movie_client, db)

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating movie rating: {e}")
        raise HTTPException(status_code=500, detail="Error creating movie rating")   

@app.get("/movies/{movie_id}/ratings", response_model=List[Rating])
async def get_movie_ratings(
    movie_id: int = Path(description="The ID of the movie to retrieve ratings for"),
    user_id: Optional[int] = Query(None, description="Filter ratings by user ID"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a minimum rating value"),
    max_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a maximum rating value"),
    tag: Optional[str] = Query(None, description="Filter ratings by tag"),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    try:
        movie_exists = await movie_client.validate_movie(movie_id)
        if not movie_exists:
            raise HTTPException(status_code=404, detail="Movie does not exist")
        
        query = db.query(RatingTable).filter(RatingTable.is_quarantined == False, RatingTable.movie_id == movie_id)

        if user_id is not None:
            query = query.filter(RatingTable.user_id == user_id)
        if min_rating is not None:
            query = query.filter(RatingTable.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(RatingTable.rating <= max_rating)
        if tag is not None:
            query = query.filter(RatingTable.tag == tag)
        
        ratings = query.offset(skip).limit(limit).all()
        if not ratings:
            raise HTTPException(status_code=404, detail="No ratings found for the specified criteria")

        return ratings
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving ratings: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving ratings")

@app.get("/users/{user_id}/ratings", response_model=List[Rating])
async def get_user_ratings(
    user_id: int = Path(description="The ID of the user to retrieve ratings for"),
    movie_id: Optional[int] = Query(None, description="Filter ratings by movie ID"),
    min_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a minimum rating value"),
    max_rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Filter ratings with a maximum rating value"),
    user_client: UserGrpcClient = Depends(get_user_client),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    try:
        user_exists = await user_client.validate_user(user_id)
        query = db.query(RatingTable).filter(RatingTable.user_id == user_id, RatingTable.is_quarantined == False)

        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        if movie_id is not None:
            query = query.filter(RatingTable.movie_id == movie_id)
        if min_rating is not None:
            query = query.filter(RatingTable.rating >= min_rating)
        if max_rating is not None:
            query = query.filter(RatingTable.rating <= max_rating)
        
        ratings = query.offset(skip).limit(limit).all()
        if not ratings:
            raise HTTPException(status_code=404, detail="No ratings found for the specified criteria")

        return query.all()
    except HTTPException:
        raise
    except Exception as e:          
        print(f"Error retrieving ratings: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving ratings:")

@app.get("/movies/{movie_id}/review-summary")
async def get_review_summary(
    movie_id: int = Path(description="The ID of the movie to retrieve review summary"),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db)
):
    try:
        movie_exists = await movie_client.validate_movie(movie_id)
        if not movie_exists:
            raise HTTPException(status_code=404, detail="Movie does not exist")

        ratings_exist = db.query(RatingTable.rating_id).filter(RatingTable.movie_id == movie_id).first()
        if not ratings_exist:
            raise HTTPException(status_code=404, detail="No analyzed reviews exist for this movie")

        # group sentiments
        sentiments = (
            db.query(ReviewSentiment.sentiment_label, func.count().label("count"))
            .join(RatingTable, RatingTable.rating_id == ReviewSentiment.rating_id)
            .filter(RatingTable.movie_id == movie_id)
            .group_by(ReviewSentiment.sentiment_label)
            .all()
        )

        total_reviews = sum(s.count for s in sentiments)
        if not total_reviews:
            raise HTTPException(status_code=404, detail="No analyzed reviews exist for this movie")

        topics = (
            db.query(Topic.name)
            .join(RatingTopic, RatingTopic.topic_id == Topic.topic_id)
            .join(RatingTable, RatingTable.rating_id == RatingTopic.rating_id)
            .filter(RatingTable.movie_id == movie_id)
            .group_by(Topic.name)
            .order_by(func.count().desc())
            .limit(5)
            .all()
        )

        top_topics = [t.name for t in topics]
        sentiment_breakdown = {s.sentiment_label: s.count for s in sentiments}

        movie_summary = RatingSummary(
            movie_id = movie_id,
            total_reviews = total_reviews,
            sentiment_breakdown = sentiment_breakdown,
            top_topics = top_topics
        )

        return movie_summary
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving summary")

Instrumentator().instrument(app).expose(app)

