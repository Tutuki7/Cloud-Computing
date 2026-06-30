import asyncio
import os

import grpc
import httpx
from dotenv import load_dotenv

from . import recommendation_pb2, recommendation_pb2_grpc

load_dotenv()
REST_URL = os.getenv("REST_URL") 
GRPC_PORT = int(os.getenv("GRPC_PORT"))   


class RecommendationService(recommendation_pb2_grpc.RecommendationServiceServicer):
    def __init__(self):
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient()
        self._client = httpx.AsyncClient(timeout=40.0)

    async def CreateUserPreference(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/preferences"
        payload = {
            "genre_id": request.genre_id,
            "preference_type": request.preference_type or "like",
        }

        async with self._lock:
            resp = await self._client.post(url, json=payload)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to create user preference: {resp.text}")
            return recommendation_pb2.UserPreferenceResponse()

        r = resp.json()
        out = recommendation_pb2.UserPreferenceResponse()
        msg = out.preference
        msg.user_id = r["user_id"]
        msg.genre_id = r["genre_id"]
        msg.preference_type = r["preference_type"]
        return out

    async def GetUserPreferences(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/preferences"

        async with self._lock:
            resp = await self._client.get(url)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to fetch user preferences: {resp.text}")
            return recommendation_pb2.GetUserPreferencesResponse()

        rows = resp.json()
        out = recommendation_pb2.GetUserPreferencesResponse()

        for r in rows:
            msg = out.preferences.add()
            msg.user_id = r["user_id"]
            msg.genre_id = r["genre_id"]
            msg.preference_type = r["preference_type"]

        return out

    async def DeleteUserPreference(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/preferences/{request.genre_id}"

        async with self._lock:
            resp = await self._client.delete(url)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to delete user preference: {resp.text}")
            return recommendation_pb2.DeleteUserPreferenceResponse(success=False)

        return recommendation_pb2.DeleteUserPreferenceResponse(success=True)

    async def AddReferenceMovie(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/reference-movies"
        params = {"movie_id": request.movie_id}

        async with self._lock:
            resp = await self._client.post(url, params=params)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to add reference movie: {resp.text}")
            return recommendation_pb2.ReferenceMovieResponse()

        r = resp.json()
        out = recommendation_pb2.ReferenceMovieResponse()
        msg = out.reference_movie
        msg.user_id = r["user_id"]
        msg.movie_id = r["movie_id"]
        return out

    async def GetReferenceMovies(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/reference-movies"

        async with self._lock:
            resp = await self._client.get(url)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to fetch reference movies: {resp.text}")
            return recommendation_pb2.GetReferenceMoviesResponse()

        rows = resp.json()
        out = recommendation_pb2.GetReferenceMoviesResponse()

        for r in rows:
            msg = out.reference_movies.add()
            msg.user_id = r["user_id"]
            msg.movie_id = r["movie_id"]

        return out

    async def DeleteReferenceMovie(self, request, context):
        url = f"{REST_URL}/users/{request.user_id}/reference-movies/{request.movie_id}"

        async with self._lock:
            resp = await self._client.delete(url)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to delete reference movie: {resp.text}")
            return recommendation_pb2.DeleteReferenceMovieResponse(success=False)

        return recommendation_pb2.DeleteReferenceMovieResponse(success=True)

    async def GetRecommendations(self, request, context):
        url = f"{REST_URL}/recommendations/{request.user_id}"

        async with self._lock:
            resp = await self._client.get(url)

        if resp.status_code != 200:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to fetch recommendations: {resp.text}")
            return recommendation_pb2.GetRecommendationsResponse()

        rows = resp.json()
        out = recommendation_pb2.GetRecommendationsResponse()

        for r in rows:
            msg = out.recommendations.add()
            msg.movie_id = r["movie_id"]
            msg.title = r["title"]

        return out

async def serve(host="0.0.0.0", port=GRPC_PORT):
    server = grpc.aio.server(options=[
        ("grpc.keepalive_time_ms", 30_000),
        ("grpc.keepalive_timeout_ms", 10_000),
    ])
    recommendation_pb2_grpc.add_RecommendationServiceServicer_to_server(
        RecommendationService(), server
    )
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"Recommendation gRPC server running on {host}:{port}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
