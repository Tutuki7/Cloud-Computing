import asyncio
from datetime import datetime, timezone
from google.protobuf.timestamp_pb2 import Timestamp
import grpc
from dotenv import load_dotenv
import os
import sys
from datetime import datetime, timezone
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from grpc_files import rating_pb2, rating_pb2_grpc
from config import get_db, RatingTable

load_dotenv()
GRPC_PORT = int(os.getenv("GRPC_PORT"))

def _ts(value):
    ts = Timestamp()

    if not value:  
        return ts
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    ts.FromDatetime(value)
    return ts

def _msg_struct(resp, r):
    msg = resp.ratings.add()
    msg.rating_id = r.rating_id
    msg.user_id = r.user_id
    msg.movie_id = r.movie_id
    msg.rating = float(r.rating)
    msg.review = r.review or ""
    msg.tag = r.tag or ""
    msg.created_at.CopyFrom(_ts(r.created_at))
    msg.updated_at.CopyFrom(_ts(r.updated_at))

class ReviewService(rating_pb2_grpc.ReviewServiceServicer):
    def __init__(self):
        self._lock = asyncio.Lock()

    async def GetRatings(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            query = db.query(RatingTable).filter(RatingTable.is_quarantined == False)

        if request.movie_id:
            query = query.filter(RatingTable.movie_id == request.movie_id)
        if request.user_id:
            query = query.filter(RatingTable.user_id == request.user_id)
        if request.min_rating:
            query = query.filter(RatingTable.rating >= request.min_rating)
        if request.max_rating:
            query = query.filter(RatingTable.rating <= request.max_rating)

        ratings = query.limit(1000).all()
        if not ratings:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("No ratings match criteria")
            return rating_pb2.GetRatingsResponse()

        resp = rating_pb2.GetRatingsResponse()
        for r in ratings:
            _msg_struct(resp, r)

        return resp

    async def GetMovieRatings(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            query = db.query(RatingTable).filter(RatingTable.is_quarantined == False, RatingTable.movie_id == request.movie_id)

        movie_ratings = query.limit(1000).all()
        if not movie_ratings:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("No ratings found for the specified movie")
            return rating_pb2.GetMovieRatingsResponse()

        resp = rating_pb2.GetMovieRatingsResponse()
        for r in movie_ratings:
            _msg_struct(resp, r)

        return resp

    async def GetUserRatings(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            query = db.query(RatingTable).filter(RatingTable.is_quarantined == False, RatingTable.user_id == request.user_id)

        ratings = query.order_by(RatingTable.created_at.desc()).limit(1000).all()
        if not ratings:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("No ratings found for user inserted")
            return rating_pb2.GetUserRatingsResponse()

        resp = rating_pb2.GetUserRatingsResponse()
        for r in ratings:
            _msg_struct(resp, r)

        return resp

async def serve(host="0.0.0.0", port=GRPC_PORT):
    server = grpc.aio.server(options=[
        ("grpc.keepalive_time_ms", 30_000),
        ("grpc.keepalive_timeout_ms", 10_000),
    ])
    rating_pb2_grpc.add_ReviewServiceServicer_to_server(ReviewService(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"Review gRPC server running on {host}:{port}")
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())
