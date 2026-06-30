
from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from grpc_files import badges_pb2 as pb
from grpc_files import badges_pb2_grpc as pb_grpc

def _ts_to_dt(ts) -> Optional[datetime]:
    if ts is None or (ts.seconds == 0 and ts.nanos == 0):
        return None
    return ts.ToDatetime(tzinfo=timezone.utc)

def _now_ts() -> Timestamp:
    """Helper to generate a Protobuf Timestamp for the current UTC time."""
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts

def _badge_to_dict(b: pb.Badge) -> dict:
    return {
        "badge_id": b.badge_id,
        "title": b.title,
        "milestone": b.milestone,
        "description": b.description or None,
    }


def _user_badge_to_dict(ub: pb.UserBadge) -> dict:
    return {
        "badge_id": ub.badge_id,
        "user_id": ub.user_id,
        "awarded_at": _ts_to_dt(ub.awarded_at),
        "badge": _badge_to_dict(ub.badge),
    }


class BadgeGrpcClient:
    def __init__(self, address: str = "badge-service:50052") -> None:
        self._address = address
        self._channel: grpc.aio.Channel | None = None
        self._stub: pb_grpc.BadgeServiceStub | None = None

    async def start(self) -> None:
        self._channel = grpc.aio.insecure_channel(self._address)
        self._stub = pb_grpc.BadgeServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel:
            await self._channel.close()

    async def list_badges(self) -> List[dict]:
        resp = await self._stub.ListBadges(pb.ListBadgesRequest())
        return [_badge_to_dict(b) for b in resp.badges]

    async def get_badge(self, badge_id: int) -> dict:
        resp = await self._stub.GetBadge(pb.GetBadgeRequest(badge_id=badge_id))
        return _badge_to_dict(resp.badge)

    async def create_badge(self, title: str, milestone: int, description: str = "") -> dict:
        resp = await self._stub.CreateBadge(
            pb.CreateBadgeRequest(title=title, milestone=milestone, description=description)
        )
        return _badge_to_dict(resp.badge)

    async def update_badge(self, badge_id: int, title: str = "", milestone: int = 0, description: str = "") -> dict:
        resp = await self._stub.UpdateBadge(
            pb.UpdateBadgeRequest(badge_id=badge_id, title=title, milestone=milestone, description=description)
        )
        return _badge_to_dict(resp.badge)

    async def delete_badge(self, badge_id: int) -> bool:
        resp = await self._stub.DeleteBadge(pb.DeleteBadgeRequest(badge_id=badge_id))
        return resp.deleted

    async def get_user_badges(self, user_id: str) -> List[dict]:
        resp = await self._stub.GetUserBadges(pb.GetUserBadgesRequest(user_id=user_id))
        return [_user_badge_to_dict(ub) for ub in resp.user_badges]

    async def award_badge(self, user_id: str, badge_id: int) -> dict:
        # Pass awarded_at from the client
        resp = await self._stub.AwardBadge(
            pb.AwardBadgeRequest(user_id=user_id, badge_id=badge_id, awarded_at=_now_ts())
        )
        return _user_badge_to_dict(resp.user_badge)

    async def stream_user_badge_events(self, user_id: str) -> AsyncIterator[dict]:
        async for event in self._stub.StreamUserBadgeEvents(
            pb.StreamUserBadgeEventsRequest(user_id=user_id)
        ):
            yield {
                "user_id": event.user_id,
                "badge": _badge_to_dict(event.badge),
                "awarded_at": _ts_to_dt(event.awarded_at),
            }