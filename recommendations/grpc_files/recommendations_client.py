from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
import grpc
from . import recommendation_pb2
from . import recommendation_pb2_grpc
from dotenv import load_dotenv
import os

load_dotenv()
GRPC_URL = os.getenv("GRPC_URL")

@dataclass(frozen=True)
class UserPreferenceResult:
    user_id: int
    genre_id: int
    preference_type: str

@dataclass(frozen=True)
class ReferenceMovieResult:
    user_id: int
    movie_id: int

@dataclass(frozen=True)
class RecommendationResult:
    movie_id: int
    title: str

class RecommendationGrpcClient:
    def __init__(self, target: str = GRPC_URL) -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[recommendation_pb2_grpc.RecommendationServiceStub] = None

    async def start(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = recommendation_pb2_grpc.RecommendationServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        self._channel = None
        self._stub = None

    def _require_stub(self) -> recommendation_pb2_grpc.RecommendationServiceStub:
        if self._stub is None:
            raise RuntimeError("RecommendationGrpcClient not started. Call await client.start().")
        return self._stub

    async def create_user_preference(self, user_id: int, genre_id: int, preference_type: str):
        stub = self._require_stub()
        req = recommendation_pb2.CreateUserPreferenceRequest(
            user_id=user_id,
            genre_id=genre_id,
            preference_type=preference_type,
        )
        resp = await stub.CreateUserPreference(req)

        prefence = resp.preference
        return UserPreferenceResult(
            user_id=prefence.user_id,
            genre_id=prefence.genre_id,
            preference_type=prefence.preference_type,
        )

    async def get_user_preferences(self, user_id: int) -> List[UserPreferenceResult]:
        stub = self._require_stub()
        req = recommendation_pb2.GetUserPreferencesRequest(user_id=user_id)
        resp = await stub.GetUserPreferences(req)

        results = []
        for preference in resp.preferences:
            results.append(
                UserPreferenceResult(
                    user_id=preference.user_id,
                    genre_id=preference.genre_id,
                    preference_type=preference.preference_type,
                )
            )
        return results

    async def delete_user_preference(self, user_id: int, genre_id: int) -> bool:
        stub = self._require_stub()
        req = recommendation_pb2.DeleteUserPreferenceRequest(
            user_id=user_id,
            genre_id=genre_id,
        )
        resp = await stub.DeleteUserPreference(req)
        return resp.success
    
    async def add_reference_movie(self, user_id: int, movie_id: int):
        stub = self._require_stub()
        req = recommendation_pb2.AddReferenceMovieRequest(
            user_id=user_id,
            movie_id=movie_id,
        )
        resp = await stub.AddReferenceMovie(req)
        r = resp.reference_movie
        return ReferenceMovieResult(
            user_id=r.user_id,
            movie_id=r.movie_id,
        )

    async def get_reference_movies(self, user_id: int) -> List[ReferenceMovieResult]:
        stub = self._require_stub()
        req = recommendation_pb2.GetReferenceMoviesRequest(user_id=user_id)
        resp = await stub.GetReferenceMovies(req)

        results = []
        for reference in resp.reference_movies:
            results.append(
                ReferenceMovieResult(
                    user_id=reference.user_id,
                    movie_id=reference.movie_id,
                )
            )
        return results

    async def delete_reference_movie(self, user_id: int, movie_id: int) -> bool:
        stub = self._require_stub()
        req = recommendation_pb2.DeleteReferenceMovieRequest(
            user_id=user_id,
            movie_id=movie_id,
        )
        resp = await stub.DeleteReferenceMovie(req)
        return resp.success
    
    async def get_recommendations(self, user_id: int) -> List[RecommendationResult]:
        stub = self._require_stub()
        req = recommendation_pb2.GetRecommendationsRequest(user_id=user_id)
        resp = await stub.GetRecommendations(req)

        results = []
        for recommendation in resp.recommendations:
            results.append(
                RecommendationResult(
                    movie_id=recommendation.movie_id,
                    title=recommendation.title,
                )
            )
        return results

