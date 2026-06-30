from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from grpc_files import watchlists_pb2 as pb
from grpc_files import watchlists_pb2_grpc as pb_grpc


def _ts_to_dt(ts) -> Optional[datetime]:
    if ts is None or (ts.seconds == 0 and ts.nanos == 0):
        return None
    return ts.ToDatetime(tzinfo=timezone.utc)

def _now_ts() -> Timestamp:
    """Helper to generate a Protobuf Timestamp for the current UTC time."""
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts

def _wl_to_dict(wl: pb.Watchlist) -> dict:
    return {
        "watchlist_id": wl.watchlist_id,
        "user_id": wl.user_id,
        "title": wl.title,
        "created_at": _ts_to_dt(wl.created_at),
        "updated_at": _ts_to_dt(wl.updated_at),
    }


def _wl_movie_to_dict(m: pb.WatchlistMovie) -> dict:
    return {
        "watchlist_id": m.watchlist_id,
        "movie_id": int(m.movie_id),
        "added_at": _ts_to_dt(m.added_at),
    }


class WatchlistGrpcClient:
    def __init__(self, address: str = "watchlist-service:50053") -> None:
        self._address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: pb_grpc.WatchlistServiceStub | None = None

    async def start(self) -> None:
        self._channel = grpc.aio.insecure_channel(self._address)
        self._stub = pb_grpc.WatchlistServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()

    async def list_watchlists(self) -> List[dict]:
        resp = await self._stub.ListWatchlists(pb.ListWatchlistsRequest())
        return [_wl_to_dict(w) for w in resp.watchlists]

    async def get_watchlist(self, watchlist_id: int) -> dict:
        resp = await self._stub.GetWatchlist(pb.GetWatchlistRequest(watchlist_id=watchlist_id))
        return {**_wl_to_dict(resp.watchlist), "movies": [_wl_movie_to_dict(m) for m in resp.movies]}

    async def create_watchlist(self, user_id: str, title: str) -> dict:
        # Pass created_at and updated_at from the client
        now = _now_ts()
        resp = await self._stub.CreateWatchlist(
            pb.CreateWatchlistRequest(
                user_id=user_id, 
                title=title, 
                created_at=now, 
                updated_at=now
            )
        )
        return _wl_to_dict(resp.watchlist)

    async def update_watchlist(self, watchlist_id: int, title: str) -> dict:
        # Pass updated_at from the client
        resp = await self._stub.UpdateWatchlist(
            pb.UpdateWatchlistRequest(
                watchlist_id=watchlist_id, 
                title=title, 
                updated_at=_now_ts()
            )
        )
        return _wl_to_dict(resp.watchlist)

    async def delete_watchlist(self, watchlist_id: int) -> bool:
        resp = await self._stub.DeleteWatchlist(pb.DeleteWatchlistRequest(watchlist_id=watchlist_id))
        return resp.deleted

    async def get_user_watchlists(self, user_id: str) -> List[dict]:
        resp = await self._stub.GetUserWatchlists(pb.GetUserWatchlistsRequest(user_id=user_id))
        return [_wl_to_dict(w) for w in resp.watchlists]

    async def add_movie(self, watchlist_id: int, movie_id: int) -> dict:
        # Pass added_at from the client
        resp = await self._stub.AddMovieToWatchlist(
            pb.AddMovieToWatchlistRequest(
                watchlist_id=watchlist_id, 
                movie_id=str(movie_id),
                added_at=_now_ts()
            )
        )
        return _wl_movie_to_dict(resp.entry)

    async def remove_movie(self, watchlist_id: int, movie_id: int) -> bool:
        resp = await self._stub.RemoveMovieFromWatchlist(
            pb.RemoveMovieFromWatchlistRequest(watchlist_id=watchlist_id, movie_id=str(movie_id))
        )
        return resp.deleted