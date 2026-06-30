from __future__ import annotations

import asyncio
import datetime
import logging
import os

import asyncpg
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from grpc_files import watchlists_pb2 as pb
from grpc_files import watchlists_pb2_grpc as pb_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DB_DSN = os.getenv("DB_URL") or (
    f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)
GRPC_PORT = os.getenv("GRPC_PORT")

def _dt_to_ts(dt) -> Timestamp:
    ts = Timestamp()
    if dt:
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        ts.FromDatetime(dt)
    return ts

def _ts_to_dt(ts) -> datetime.datetime:
    """Converts Protobuf Timestamp to a Python datetime. Falls back to current UTC time if missing."""
    if not ts or (ts.seconds == 0 and ts.nanos == 0):
        return datetime.datetime.now(datetime.timezone.utc)
    return ts.ToDatetime(tzinfo=datetime.timezone.utc)


def _row_to_watchlist(row) -> pb.Watchlist:
    # Assuming your pb.Watchlist has created_at/updated_at fields; we populate them here if they exist in the DB.
    wl = pb.Watchlist(
        watchlist_id=row["watchlist_id"],
        user_id=str(row["user_id"]),
        title=row["title"],
    )
    if "created_at" in row and row["created_at"]:
        wl.created_at.CopyFrom(_dt_to_ts(row["created_at"]))
    if "updated_at" in row and row["updated_at"]:
        wl.updated_at.CopyFrom(_dt_to_ts(row["updated_at"]))
    return wl


def _row_to_wl_movie(row) -> pb.WatchlistMovie:
    wm = pb.WatchlistMovie(
        watchlist_id=row["watchlist_id"],
        movie_id=str(row["movie_id"]),
    )
    if "added_at" in row and row["added_at"]:
        wm.added_at.CopyFrom(_dt_to_ts(row["added_at"]))
    return wm


class WatchlistServicer(pb_grpc.WatchlistServiceServicer):

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ListWatchlists(self, request, context):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM watchlists ORDER BY watchlist_id")
        return pb.ListWatchlistsResponse(watchlists=[_row_to_watchlist(r) for r in rows])

    async def GetWatchlist(self, request, context):
        async with self._pool.acquire() as conn:
            wl_row = await conn.fetchrow(
                "SELECT * FROM watchlists WHERE watchlist_id = $1", request.watchlist_id
            )
            if wl_row is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Watchlist {request.watchlist_id} not found")
                return pb.GetWatchlistResponse()
            movie_rows = await conn.fetch(
                "SELECT * FROM watchlist_movies WHERE watchlist_id = $1", request.watchlist_id
            )
        return pb.GetWatchlistResponse(
            watchlist=_row_to_watchlist(wl_row),
            movies=[_row_to_wl_movie(r) for r in movie_rows],
        )

    async def CreateWatchlist(self, request, context):
        if not request.title:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "title is required")
            return pb.CreateWatchlistResponse()
            
        created_dt = _ts_to_dt(request.created_at)
        updated_dt = _ts_to_dt(request.updated_at)
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO watchlists (user_id, title, created_at, updated_at) VALUES ($1, $2, $3, $4) RETURNING *",
                int(request.user_id), request.title, created_dt, updated_dt
            )
        log.info("Created watchlist %d for user %s", row["watchlist_id"], request.user_id)
        return pb.CreateWatchlistResponse(watchlist=_row_to_watchlist(row))

    async def UpdateWatchlist(self, request, context):
        if not request.title:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "title is required for update")
            return pb.UpdateWatchlistResponse()
            
        updated_dt = _ts_to_dt(request.updated_at)
        
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE watchlists SET title=$1, updated_at=$2 WHERE watchlist_id=$3 RETURNING *",
                request.title, updated_dt, request.watchlist_id,
            )
        if row is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Watchlist {request.watchlist_id} not found")
            return pb.UpdateWatchlistResponse()
        return pb.UpdateWatchlistResponse(watchlist=_row_to_watchlist(row))

    async def DeleteWatchlist(self, request, context):
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM watchlists WHERE watchlist_id = $1", request.watchlist_id
            )
        if result == "DELETE 0":
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Watchlist {request.watchlist_id} not found")
            return pb.DeleteWatchlistResponse()
        return pb.DeleteWatchlistResponse(deleted=True)

    async def GetUserWatchlists(self, request, context):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM watchlists WHERE user_id = $1 ORDER BY watchlist_id",
                int(request.user_id),
            )
        return pb.GetUserWatchlistsResponse(watchlists=[_row_to_watchlist(r) for r in rows])

    async def AddMovieToWatchlist(self, request, context):
        async with self._pool.acquire() as conn:
            wl = await conn.fetchrow(
                "SELECT watchlist_id FROM watchlists WHERE watchlist_id = $1", request.watchlist_id
            )
            if wl is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Watchlist {request.watchlist_id} not found")
                return pb.AddMovieToWatchlistResponse()
                
            added_dt = _ts_to_dt(request.added_at)
            
            try:
                row = await conn.fetchrow(
                    "INSERT INTO watchlist_movies (watchlist_id, movie_id, added_at) VALUES ($1, $2, $3) RETURNING *",
                    request.watchlist_id, int(request.movie_id), added_dt
                )
            except asyncpg.UniqueViolationError:
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "Movie already in watchlist")
                return pb.AddMovieToWatchlistResponse()
        log.info("Added movie %s to watchlist %d", request.movie_id, request.watchlist_id)
        return pb.AddMovieToWatchlistResponse(entry=_row_to_wl_movie(row))

    async def RemoveMovieFromWatchlist(self, request, context):
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM watchlist_movies WHERE watchlist_id=$1 AND movie_id=$2",
                request.watchlist_id, int(request.movie_id),
            )
        if result == "DELETE 0":
            await context.abort(grpc.StatusCode.NOT_FOUND, "Movie not found in watchlist")
            return pb.RemoveMovieFromWatchlistResponse()
        return pb.RemoveMovieFromWatchlistResponse(deleted=True)


async def serve():
    pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10, ssl=False)
    log.info("Connected to PostgreSQL")
    server = grpc.aio.server()
    pb_grpc.add_WatchlistServiceServicer_to_server(WatchlistServicer(pool), server)
    address = f'[::]:{GRPC_PORT}'
    server.add_insecure_port(address)
    log.info(f"WatchlistService listening on 0.0.0.0:{GRPC_PORT}")
    await server.start()
    await server.wait_for_termination()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(serve())