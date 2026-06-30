from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List
import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from . import rating_pb2, rating_pb2_grpc
from dotenv import load_dotenv
import os

load_dotenv()
GRPC_URL = os.getenv("GRPC_URL")

def _to_ts(dt: Optional[datetime]) -> Optional[Timestamp]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(dt.astimezone(timezone.utc))
    return ts


@dataclass(frozen=True)
class RatingResult:
    rating_id: int
    user_id: int
    movie_id: int
    rating: float
    review: str
    tag: str
    created_at: datetime
    updated_at: datetime

#to use inside FastAPI endpoints, so it can be shared across requests without needing to start/stop the gRPC channel each time.
class ReviewGrpcClient: # 
    def __init__(self, target: str = GRPC_URL) -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[rating_pb2_grpc.RatingServiceStub] = None

    async def start(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = rating_pb2_grpc.RatingServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        self._channel = None
        self._stub = None

    def _require_stub(self) -> rating_pb2_grpc.RatingServiceStub:
        if self._stub is None:
            raise RuntimeError("ReviewGrpcClient not started. Call await client.start().")
        return self._stub

    async def get_user_ratings(self, user_id: int) -> List[RatingResult]:
        stub = self._require_stub()
        req = rating_pb2.GetUserRatingsRequest(user_id=user_id)
        resp = await stub.GetUserRatings(req)

        results = []
        for r in resp.ratings:
            results.append(
                RatingResult(
                    rating_id=r.rating_id,
                    user_id=r.user_id,
                    movie_id=r.movie_id,
                    rating=r.rating,
                    review=r.review,
                    tag=r.tag,
                    created_at=r.created_at.ToDatetime(),
                    updated_at=r.updated_at.ToDatetime(),
                )
            )
        return results

    async def get_movie_ratings(self, movie_id: int) -> List[RatingResult]:
        stub = self._require_stub()
        req = rating_pb2.GetMovieRatingsRequest(movie_id=movie_id)
        resp = await stub.GetMovieRatings(req)

        results = []
        for r in resp.ratings:
            results.append(
                RatingResult(
                    rating_id=r.rating_id,
                    user_id=r.user_id,
                    movie_id=r.movie_id,
                    rating=r.rating,
                    review=r.review,
                    tag=r.tag,
                    created_at=r.created_at.ToDatetime(),
                    updated_at=r.updated_at.ToDatetime(),
                )
            )
        return results
