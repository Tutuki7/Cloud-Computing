from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
import grpc
import os
from dotenv import load_dotenv
from . import movies_pb2, movies_pb2_grpc

load_dotenv()
MOVIE_GRPC_URL = os.getenv("MOVIE_GRPC_URL")

@dataclass(frozen=True)
class MovieResult:
    movie_id: int
    movie_title: str
    description: str
    imdb_url: str
    release_year: int
    runtime: int
    parental_rating: str
    poster_url: str
    genres: list[str]
    avg_rating: float
   
class MovieGrpcClient:
    def __init__(self, target: str = MOVIE_GRPC_URL) -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[movies_pb2_grpc.MovieServiceStub] = None

    async def start(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = movies_pb2_grpc.MovieServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        self._channel = None
        self._stub = None

    def _require_stub(self) -> movies_pb2_grpc.MovieServiceStub:
        if self._stub is None:
            raise RuntimeError("MovieGrpcClient not started. Call await client.start().")
        return self._stub

    async def get_movie(self, movie_id: int) -> movies_pb2.Movie:
        stub = self._require_stub()
        req = movies_pb2.GetMovieRequest(movie_id=movie_id)
        resp = await stub.GetMovie(req)
        return resp.movie

    async def update_avg_rating(self, movie_id: int, avg_rating: float) -> bool:
        stub = self._require_stub()
        req = movies_pb2.UpdateAvgRatingRequest(movie_id=movie_id, avg_rating=avg_rating)
        resp = await stub.UpdateAvgRating(req)
        return resp.success

    async def validate_movie(self, movie_id: int) -> bool:
        stub = self._require_stub()
        req = movies_pb2.ValidateMovieRequest(movie_id=movie_id)
        resp = await stub.ValidateMovie(req)
        return resp.exists