import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import grpc

from config import get_db, MovieTable, GenreTable, MovieGenreTable
from sqlalchemy.orm import Session

import movies_pb2
import movies_pb2_grpc


class MovieService(movies_pb2_grpc.MovieServiceServicer):
    def __init__(self):
        self._lock = asyncio.Lock()

    async def GetMovie(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            movie = db.query(MovieTable).filter(
                MovieTable.movie_id == request.movie_id,
                MovieTable.is_deleted == False
            ).first()

            if not movie:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("Movie not found")
                return movies_pb2.GetMovieResponse()

            movie_genres = db.query(GenreTable.name)\
                .join(MovieGenreTable, GenreTable.genre_id == MovieGenreTable.genre_id)\
                .filter(MovieGenreTable.movie_id == movie.movie_id)\
                .all()

        return movies_pb2.GetMovieResponse(
            movie=movies_pb2.Movie(
                movie_id=movie.movie_id,
                movie_title=movie.movie_title,
                description=movie.description or "",
                imdb_url=movie.imdb_url or "",
                release_year=movie.release_year,
                runtime=movie.runtime or 0,
                parental_rating=movie.parental_rating or "",
                poster_url=movie.poster_url or "",
                genres=[g[0] for g in movie_genres],
                avg_rating=movie.avg_rating or 0.0
            )
        )

    async def ValidateMovie(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            exists = db.query(MovieTable).filter(
                MovieTable.movie_id == request.movie_id,
                MovieTable.is_deleted == False
            ).first() is not None

        return movies_pb2.ValidateMovieResponse(exists=exists)

    async def SearchMovies(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            query = db.query(MovieTable).filter(MovieTable.is_deleted == False)

            if request.title:
                query = query.filter(MovieTable.movie_title.ilike(f"%{request.title}%"))

            if request.release_year > 0:
                query = query.filter(MovieTable.release_year == request.release_year)

            if request.genre:
                query = query.join(MovieGenreTable, MovieTable.movie_id == MovieGenreTable.movie_id)\
                             .join(GenreTable, MovieGenreTable.genre_id == GenreTable.genre_id)\
                             .filter(GenreTable.name.ilike(f"%{request.genre}%"))

            limit = request.limit if request.limit > 0 else 20
            offset = request.offset if request.offset >= 0 else 0

            movies = query.order_by(MovieTable.avg_rating.desc().nullslast()).offset(offset).limit(limit).all()

            result_movies = []
            for movie in movies:
                movie_genres = db.query(GenreTable.name)\
                    .join(MovieGenreTable, GenreTable.genre_id == MovieGenreTable.genre_id)\
                    .filter(MovieGenreTable.movie_id == movie.movie_id)\
                    .all()

                result_movies.append(movies_pb2.Movie(
                    movie_id=movie.movie_id,
                    movie_title=movie.movie_title,
                    description=movie.description or "",
                    imdb_url=movie.imdb_url or "",
                    release_year=movie.release_year,
                    runtime=movie.runtime or 0,
                    parental_rating=movie.parental_rating or "",
                    poster_url=movie.poster_url or "",
                    genres=[g[0] for g in movie_genres],
                    avg_rating=movie.avg_rating or 0.0
                ))

        return movies_pb2.SearchMoviesResponse(movies=result_movies)

    async def GetMoviesBatch(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            movies = db.query(MovieTable).filter(
                MovieTable.movie_id.in_(request.movie_ids),
                MovieTable.is_deleted == False,
            ).order_by(MovieTable.avg_rating.desc().nullslast()).all()

            result_movies = []
            for movie in movies:
                movie_genres = db.query(GenreTable.name)\
                    .join(MovieGenreTable, GenreTable.genre_id == MovieGenreTable.genre_id)\
                    .filter(MovieGenreTable.movie_id == movie.movie_id)\
                    .all()

                result_movies.append(movies_pb2.Movie(
                    movie_id=movie.movie_id,
                    movie_title=movie.movie_title,
                    description=movie.description or "",
                    imdb_url=movie.imdb_url or "",
                    release_year=movie.release_year,
                    runtime=movie.runtime or 0,
                    parental_rating=movie.parental_rating or "",
                    poster_url=movie.poster_url or "",
                    genres=[g[0] for g in movie_genres],
                    avg_rating=movie.avg_rating or 0.0
                ))

        return movies_pb2.GetMoviesBatchResponse(movies=result_movies)

    async def GetGenres(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            genres = db.query(GenreTable).order_by(GenreTable.name).all()

            result_genres = []
            for genre in genres:
                result_genres.append(
                    movies_pb2.Genre(genre_id=genre.genre_id, name=genre.name)
                )

        return movies_pb2.GetGenresResponse(genres=result_genres)
    
    async def ValidateGenre(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            genre = db.query(GenreTable).filter(
                GenreTable.genre_id == request.genre_id,
            ).first()
            
            if not genre:
                return movies_pb2.ValidateGenreResponse(exists=False, name="")
            
            return movies_pb2.ValidateGenreResponse(exists=True, name=genre.name)

    async def UpdateAvgRating(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            try:
                movie = db.query(MovieTable).filter(
                    MovieTable.movie_id == request.movie_id,
                    MovieTable.is_deleted == False
                ).first()

                if not movie:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Movie not found")
                    return movies_pb2.UpdateAvgRatingResponse(success=False)

                movie.avg_rating = request.avg_rating
                db.commit()
                return movies_pb2.UpdateAvgRatingResponse(success=True)
            except Exception as e:
                db.rollback()
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                return movies_pb2.UpdateAvgRatingResponse(success=False)
            finally:
                db.close()

async def serve(host="0.0.0.0", port=50054):
    server = grpc.aio.server()
    movies_pb2_grpc.add_MovieServiceServicer_to_server(MovieService(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"Movie gRPC server running on {host}:{port}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())