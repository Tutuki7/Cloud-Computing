from __future__ import annotations

from typing import List
from fastapi import FastAPI, HTTPException, Path, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from config import (
    get_db, UserPreferenceTable, UserReferenceMovieTable,
    review_client, movie_client, user_client, vertex_client, MODEL
)
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from ratings.rating_client import ReviewGrpcClient
import json

import os
import httpx
from jose import jwt, JWTError

from fastapi.concurrency import run_in_threadpool
from users.users_client import UserGrpcClient
from movies.movies_client import MovieGrpcClient
from prometheus_fastapi_instrumentator import Instrumentator
import grpc

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
    await review_client.start()
    print("Review gRPC client started")
    yield
    await user_client.close()
    await movie_client.close()
    await review_client.close()
    print("Review gRPC client closed")  

def get_review_client():
    return review_client

def get_user_client():
    return user_client

def get_movie_client():
    return movie_client

app = FastAPI(
    root_path=os.getenv("ROOT_PATH", ""),
    title="Recommendation System API",
    version="1.0.0",
    description="REST API for recommendations and user preferences.",
    lifespan=lifespan
)

# Models
class UserPreference(BaseModel):
    user_id: int = Field(unique=True, notnull=True, description="ID of the user")
    genre_id: int = Field(notnull=True, description="ID of the genre")
    preference_type: str = Field(default="like", description="Type of preference, e.g., 'like', 'dislike', 'neutral'")

class CreateUserPreference(BaseModel):
    genre_id: int = Field(notnull=True, description="ID of the genre")
    preference_type: str = Field(default="like", description="Type of preference, e.g., 'like', 'dislike', 'neutral'")

class ReferenceMovie(BaseModel):
    movie_id: int = Field(notnull=True, description="ID of the reference movie")
    user_id: int = Field(unique=True, notnull=True, description="ID of the user")

class Recommendation(BaseModel):
    movie_id: int = Field(notnull=True, description="ID of the recommended movie")
    title: str = Field(notnull=True, description="Title of the recommended movie")

class ExplainedRecommendation(BaseModel):
    movie_id: int = Field(notnull=True, description="ID of the recommended movie")
    title: str = Field(notnull=True, description="Title of the recommended movie")
    explaination: str = Field(notnull=True, description="Explaination of the recommendation given")

# Routes
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/users/{user_id}/preferences", response_model=UserPreference)
async def create_user_preference(
    user_id: int = Path(description="ID of the user"),
    preference: CreateUserPreference = None,
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        
        genre_exists, _ = await movie_client.validate_genre(preference.genre_id)

        if not genre_exists:
            raise HTTPException(status_code=404, detail="Genre does not exist")
        
        existing_preference = (
            db.query(UserPreferenceTable)
            .filter(
                UserPreferenceTable.user_id == user_id,
                UserPreferenceTable.genre_id == preference.genre_id
            ).first()
        )

        if existing_preference:
            raise HTTPException(status_code=400, detail="User preference already exists")
        
        new_preference = UserPreferenceTable(
            user_id=user_id,
            genre_id=preference.genre_id,
            preference_type=preference.preference_type
        )
        
        db.add(new_preference)
        db.commit()
        db.refresh(new_preference)
        return new_preference
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating user preference: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating user preference: {e}")

@app.get("/users/{user_id}/preferences", response_model=List[UserPreference])
async def get_user_preferences(
    user_id: int = Path(description="ID of the user"),
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        preferences = db.query(UserPreferenceTable).filter(UserPreferenceTable.user_id == user_id).all()
        if not preferences:
            raise HTTPException(status_code=404, detail="User preferences not found")
        return preferences
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving user preferences: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving user preferences: {e}")

@app.delete("/users/{user_id}/preferences/{genre_id}")
async def delete_user_preference(
    user_id: int = Path(description="ID of the user"),
    genre_id: int = Path(description="ID of the genre"),
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")

        preference = db.query(UserPreferenceTable).filter(
            UserPreferenceTable.user_id == user_id,
            UserPreferenceTable.genre_id == genre_id
        ).first()

        if not preference:
            raise HTTPException(status_code=404, detail="User preference not found")

        db.delete(preference)
        db.commit()
        return {"message": "User preference deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting user preference: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting user preference: {e}")
    
@app.post("/users/{user_id}/reference-movies", response_model=ReferenceMovie)
async def add_reference_movie(
    user_id: int = Path(description="ID of the user"),
    movie_id: int = Query(description="ID of the reference movie"),
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        movie_exists = await movie_client.validate_movie(movie_id)

        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        if not movie_exists:
            raise HTTPException(status_code=404, detail="Movie does not exist")
        
        # latter to validate movie with movie service (grpc calls)
        existing_reference = (
            db.query(UserReferenceMovieTable)
            .filter(
                UserReferenceMovieTable.user_id == user_id,
                UserReferenceMovieTable.movie_id == movie_id
            ).first()
        )

        if existing_reference:
            raise HTTPException(status_code=400, detail="Reference movie already exists for this user")
        
        new_reference = UserReferenceMovieTable(
            user_id=user_id,
            movie_id=movie_id
        )
        
        db.add(new_reference)
        db.commit()
        db.refresh(new_reference)
        return new_reference
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error adding reference movie: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding reference movie: {e}")   
    
@app.get("/users/{user_id}/reference-movies", response_model=List[ReferenceMovie])
async def get_reference_movies(
    user_id: int = Path(description="ID of the user"),
    user_client: UserGrpcClient = Depends(get_user_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = user_exists = await user_client.validate_user(user_id)
        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        reference_movies = db.query(UserReferenceMovieTable).filter(UserReferenceMovieTable.user_id == user_id).all()
        if not reference_movies:
            raise HTTPException(status_code=404, detail="Reference movies not found for this user")
        return reference_movies
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving reference movies: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving reference movies: {e}")

@app.delete("/users/{user_id}/reference-movies/{movie_id}")
async def delete_reference_movie(
    user_id: int = Path(description="ID of the user"),
    movie_id: int = Path(description="ID of the reference movie"),
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    db: Session = Depends(get_db),
    token: dict = Depends(require_auth),
):
    try:
        user_exists = await user_client.validate_user(user_id)
        movie_exists = await movie_client.validate_movie(movie_id)

        if not user_exists:
            raise HTTPException(status_code=404, detail="User does not exist")
        if not movie_exists:
            raise HTTPException(status_code=404, detail="Movie does not exist")

        reference_movie = db.query(UserReferenceMovieTable).filter(
            UserReferenceMovieTable.user_id == user_id,
            UserReferenceMovieTable.movie_id == movie_id
        ).first()

        if not reference_movie:
            raise HTTPException(status_code=404, detail="Reference movie not found for this user")

        db.delete(reference_movie)
        db.commit()
        return {"message": "Reference movie deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting reference movie: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting reference movie")

@app.get("/recommendations/{user_id}/explained", response_model=List[ExplainedRecommendation])
async def get_recommendations_explained(
    user_id: int,
    db: Session = Depends(get_db),
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    review_client: ReviewGrpcClient = Depends(get_review_client),
    token: dict = Depends(require_auth),
):
    user_exists = await user_client.validate_user(user_id)
    if not user_exists:
        raise HTTPException(status_code=404, detail="User does not exist")

    recommendations, liked_genres, disliked_genres, ref_movies = await generate_recommendations(user_id, db, review_client, movie_client)

    if not recommendations:
        raise HTTPException(status_code=404, detail="No recommendations to explain")

    context = f"The user likes these genres: {', '.join(liked_genres)}. " if liked_genres else ""
    context += f"The user dislikes these genres: {', '.join(disliked_genres)}. " if disliked_genres else ""
    context += f"They previously enjoyed: {', '.join(ref_movies)}." if ref_movies else ""

    rec_movies = ", ".join([m.title for m in recommendations])
    prompt = f"""
    You are a movie recommendation assistant. 
    User Context: {context}
    Recommended Movies: {rec_movies}
    
    Task: Provide a single, conversational sentence for each recommended movie explaining why it 
    matches their specific taste in genres or reference movies. Return as a simple list of explanations.
    Format strictly as a valid JSON array of strings: ["Explanation 1", "Explanation 2"]
    Do not use double quotes around movie titles inside your explanations, use single quotes.
    Write them like this example, e.g.: 'Once Upon a Time' is a great watch not \"Once Upon a Time\" is a great watch.
    """

    try:
        response = await run_in_threadpool(vertex_client.models.generate_content, model=MODEL, contents=prompt)

        clean_text = response.text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]

        explanations = json.loads(clean_text.strip())

    except Exception as e:
        print(f"Error generating explaination for recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating explaination for recommendations")

    result = []
    for i, rec in enumerate(recommendations):
        explanation_text = explanations[i] if i < len(explanations) else "Recommended based on your preferences."
        explanation_rec = ExplainedRecommendation(movie_id=rec.movie_id,title=rec.title,explaination=explanation_text)
        result.append(explanation_rec)

    return result

@app.get("/recommendations/{user_id}", response_model=List[Recommendation])
async def get_recommendations(
    user_id: int,
    db: Session = Depends(get_db),
    user_client: UserGrpcClient = Depends(get_user_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
    review_client: ReviewGrpcClient = Depends(get_review_client),
    token: dict = Depends(require_auth),
):
    user_exists = await user_client.validate_user(user_id)
    if not user_exists:
        raise HTTPException(status_code=404, detail="User does not exist")
    
    recommendations, _, _, _ = await generate_recommendations(user_id, db, review_client, movie_client)

    return recommendations

# helper functions
async def generate_recommendations(
    user_id: int,
    db: Session = Depends(get_db),
    review: ReviewGrpcClient = Depends(get_review_client),
    movie_client: MovieGrpcClient = Depends(get_movie_client),
):
    try:
        ratings = await review.get_user_ratings(user_id)
    except Exception as e:
        print(f"Warning: could not fetch ratings: {e}")
        ratings = []

    # positive ratings only be considered to calculate the score of a recommendation
    ratings = [rating for rating in ratings if rating.rating >= 3.0]
    rated_movie_ids = [rating.movie_id for rating in ratings]

    try:
        rated_movies = await movie_client.get_movies_batch(rated_movie_ids) if rated_movie_ids else []
    except Exception as e:
        print(f"Warning: could not fetch rated movies: {e}")
        rated_movies = []

    rated_lookup = {m.movie_id: m for m in rated_movies}
    
    ref_movies = db.query(UserReferenceMovieTable).filter(UserReferenceMovieTable.user_id == user_id).all()
    ref_movie_ids = [ref_movie.movie_id for ref_movie in ref_movies]

    try:
        ref_movies = await movie_client.get_movies_batch(ref_movie_ids) if ref_movie_ids else []
    except Exception as e:
        print(f"Warning: could not fetch ref movies: {e}")
        ref_movies = []

    ref_movies_titles = [m.movie_title for m in ref_movies]

    user_prefs = db.query(UserPreferenceTable).filter(UserPreferenceTable.user_id == user_id).all()
    genre_pref = {}
    liked_genres = []
    disliked_genres = []

    # positive rating value is added to score 
    for r in ratings:
        movie = rated_lookup.get(r.movie_id)
        if movie:
            for genre in movie.genres:
                genre_pref[genre] = genre_pref.get(genre, 0) + float(r.rating)

    try:
        genres = await movie_client.get_genres()
        pref_genres = {g.genre_id: g.name for g in genres}
    except Exception as e:
        print(f"Warning: could not fetch genre prefs: {e}")
        pref_genres = {}

    for p in user_prefs:
        genre = pref_genres.get(p.genre_id)
        if not genre:
            continue
        if p.preference_type == "like":
            genre_pref[genre] = genre_pref.get(genre, 0) + 2.0
            if genre not in liked_genres:
                liked_genres.append(genre)
        elif p.preference_type == "dislike":
            genre_pref[genre] = genre_pref.get(genre, 0) - 3.0
            if genre not in disliked_genres:
                disliked_genres.append(genre)
    
    for m in ref_movies:
        if m.movie_id in ref_movie_ids:
            for genre in m.genres:
                genre_pref[genre] = genre_pref.get(genre, 0) + 1.5
    
    if not genre_pref: # no data for recommendations return top rated movies
        fallback = await get_top_rated_movies(movie_client)
        return fallback, [], [], []
    
    try:
        all_candidates = await movie_client.search_movies(limit=1000)
    except Exception as e:
        print(f"Warning: could not fetch candidates, falling back: {e}")
        fallback = await get_top_rated_movies(movie_client)
        return fallback, [], [], []

    exclude_ids = set(rated_movie_ids + ref_movie_ids)

    scored_movies = []
    for m in all_candidates:
        if m.movie_id in exclude_ids:
            continue
        if m.avg_rating < 3.0:
            continue
        score = sum(genre_pref.get(genre_name, 0.0) for genre_name in m.genres)
        scored_movies.append((score, m))

    # returns top 5 scored_movies
    scored_movies.sort(key=lambda x: x[0], reverse=True)
    top = [item for item in scored_movies if item[0] > 0][:5]
    recomendations = []

    for score, m in top:
        recomendation = Recommendation(movie_id= m.movie_id, title= m.movie_title)
        recomendations.append(recomendation)
    
    return recomendations, liked_genres, disliked_genres, ref_movies_titles

async def get_top_rated_movies(movie_client):
    recomendations = []
    try:
        top_movies = await movie_client.search_movies(limit=5)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Movie Recommendations failed:{e}")
   
    for m in top_movies:
        print(f'{m.movie_title} - {m.avg_rating}') # later remove print after
        recomendation = Recommendation(movie_id= m.movie_id, title= m.movie_title)
        recomendations.append(recomendation)

    return recomendations

Instrumentator().instrument(app).expose(app)
