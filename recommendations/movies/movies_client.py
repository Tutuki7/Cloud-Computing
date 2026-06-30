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

@dataclass(frozen=True)
class GenreResult:
    genre_id: int
    name: str
   
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
    
    def _map_to_result(self, movie: movies_pb2.Movie) -> MovieResult:
        return MovieResult(
            movie_id=movie.movie_id,
            movie_title=movie.movie_title,
            description=movie.description,
            imdb_url=movie.imdb_url,
            release_year=movie.release_year,
            runtime=movie.runtime,
            parental_rating=movie.parental_rating,
            poster_url=movie.poster_url,
            genres=list(movie.genres),
            avg_rating=movie.avg_rating
        )

    async def get_movie(self, movie_id: int) -> movies_pb2.Movie:
        stub = self._require_stub()
        req = movies_pb2.GetMovieRequest(movie_id=movie_id)
        resp = await stub.GetMovie(req)
        return resp.movie

    async def validate_movie(self, movie_id: int) -> bool:
        stub = self._require_stub()
        req = movies_pb2.ValidateMovieRequest(movie_id=movie_id)
        resp = await stub.ValidateMovie(req)
        return resp.exists

    async def validate_genre(self, genre_id: int) -> tuple[bool, str]:
        stub = self._require_stub()
        resp = await stub.ValidateGenre(movies_pb2.ValidateGenreRequest(genre_id=genre_id))
        return resp.exists, resp.name
    
    async def get_genres(self) -> list[GenreResult]:
        stub = self._require_stub()
        req = movies_pb2.GetGenresRequest()
        resp = await stub.GetGenres(req)
        return [GenreResult(genre_id=g.genre_id, name=g.name) for g in resp.genres]
    
    async def get_movies_batch(self, movie_ids: list[int]) -> list[MovieResult]:
        stub = self._require_stub()
        req = movies_pb2.GetMoviesBatchRequest(movie_ids=movie_ids)
        resp = await stub.GetMoviesBatch(req)
        return [self._map_to_result(m) for m in resp.movies]
    
    async def search_movies(
        self, 
        title: str = "", 
        genre: str = "", 
        release_year: int = 0, 
        limit: int = 10, 
        offset: int = 0
    ) -> list[MovieResult]:

        stub = self._require_stub()
        req = movies_pb2.SearchMoviesRequest(
            title=title,
            genre=genre,
            release_year=release_year,
            limit=limit,
            offset=offset
        )
    
        resp = await stub.SearchMovies(req)
        return [self._map_to_result(m) for m in resp.movies]
            
        