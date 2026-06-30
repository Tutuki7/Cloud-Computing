from __future__ import annotations

import asyncio
import datetime
import logging
import os

import asyncpg
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from grpc_files import badges_pb2 as pb
from grpc_files import badges_pb2_grpc as pb_grpc

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


def _row_to_badge(row) -> pb.Badge:
    return pb.Badge(
        badge_id=row["badge_id"],
        title=row["title"],
        milestone=row["milestone"] or 0,
        description=row["description"] or "",
    )


def _row_to_user_badge(row) -> pb.UserBadge:
    return pb.UserBadge(
        badge_id=row["badge_id"],
        user_id=str(row["user_id"]),
        awarded_at=_dt_to_ts(row["awarded_at"]),
        badge=pb.Badge(
            badge_id=row["badge_id"],
            title=row["title"],
            milestone=row["milestone"] or 0,
        ),
    )


class BadgeServicer(pb_grpc.BadgeServiceServicer):

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def ListBadges(self, request, context):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM badges ORDER BY badge_id")
        return pb.ListBadgesResponse(badges=[_row_to_badge(r) for r in rows])

    async def GetBadge(self, request, context):
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM badges WHERE badge_id = $1", request.badge_id)
        if row is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Badge {request.badge_id} not found")
            return pb.GetBadgeResponse()
        return pb.GetBadgeResponse(badge=_row_to_badge(row))

    async def CreateBadge(self, request, context):
        if not request.title:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "title is required")
            return pb.CreateBadgeResponse()
        if not request.milestone:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "milestone is required")
            return pb.CreateBadgeResponse()

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT badge_id FROM badges WHERE title = $1", request.title
            )
            if existing:
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    f"Badge '{request.title}' already exists (id={existing['badge_id']})"
                )
                return pb.CreateBadgeResponse()

            try:
                row = await conn.fetchrow(
                    "INSERT INTO badges (title, milestone, description) VALUES ($1, $2, $3) RETURNING *",
                    request.title, request.milestone, request.description,
                )
            except asyncpg.UniqueViolationError:
                await context.abort(
                    grpc.StatusCode.ALREADY_EXISTS,
                    f"Badge '{request.title}' already exists"
                )
                return pb.CreateBadgeResponse()

        log.info("Created badge %d: %s", row["badge_id"], row["title"])
        return pb.CreateBadgeResponse(badge=_row_to_badge(row))

    async def UpdateBadge(self, request, context):
        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow("SELECT * FROM badges WHERE badge_id = $1", request.badge_id)
            if existing is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Badge {request.badge_id} not found")
                return pb.UpdateBadgeResponse()
            row = await conn.fetchrow(
                "UPDATE badges SET title=$1, milestone=$2, description=$3 WHERE badge_id=$4 RETURNING *",
                request.title or existing["title"],
                request.milestone or existing["milestone"],
                request.description if request.description else existing["description"],
                request.badge_id,
            )
        return pb.UpdateBadgeResponse(badge=_row_to_badge(row))

    async def DeleteBadge(self, request, context):
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM badges WHERE badge_id = $1", request.badge_id)
        if result == "DELETE 0":
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Badge {request.badge_id} not found")
            return pb.DeleteBadgeResponse()
        return pb.DeleteBadgeResponse(deleted=True)

    async def GetUserBadges(self, request, context):
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ub.badge_id, ub.user_id, ub.awarded_at, b.title, b.milestone
                FROM user_badges ub
                JOIN badges b ON b.badge_id = ub.badge_id
                WHERE ub.user_id = $1
                ORDER BY ub.awarded_at DESC
                """,
                int(request.user_id),
            )
        return pb.GetUserBadgesResponse(user_badges=[_row_to_user_badge(r) for r in rows])

    async def AwardBadge(self, request, context):
        async with self._pool.acquire() as conn:
            badge_row = await conn.fetchrow("SELECT * FROM badges WHERE badge_id = $1", request.badge_id)
            if badge_row is None:
                await context.abort(grpc.StatusCode.NOT_FOUND, f"Badge {request.badge_id} not found")
                return pb.AwardBadgeResponse()
                
            # Extract timestamp from request
            awarded_dt = _ts_to_dt(request.awarded_at)
            
            try:
                ub_row = await conn.fetchrow(
                    "INSERT INTO user_badges (badge_id, user_id, awarded_at) VALUES ($1, $2, $3) RETURNING *",
                    request.badge_id, int(request.user_id), awarded_dt
                )
            except asyncpg.UniqueViolationError:
                await context.abort(grpc.StatusCode.ALREADY_EXISTS, "User already has this badge")
                return pb.AwardBadgeResponse()

        log.info("Awarded badge %d to user %s", request.badge_id, request.user_id)
        combined = {**dict(ub_row), "title": badge_row["title"], "milestone": badge_row["milestone"]}
        return pb.AwardBadgeResponse(user_badge=_row_to_user_badge(combined))


async def serve():
    pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10, ssl=False)
    log.info("Connected to PostgreSQL")
    server = grpc.aio.server()
    pb_grpc.add_BadgeServiceServicer_to_server(BadgeServicer(pool), server)
    address = f'[::]:{GRPC_PORT}'
    server.add_insecure_port(address)
    log.info(f"BadgeService listening on 0.0.0.0:{GRPC_PORT}")
    await server.start()
    await server.wait_for_termination()
    await pool.close()


if __name__ == "__main__":
    asyncio.run(serve())