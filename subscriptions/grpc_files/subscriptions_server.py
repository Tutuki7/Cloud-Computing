import asyncio
from datetime import timezone
import os

import grpc
from google.protobuf.timestamp_pb2 import Timestamp
from sqlalchemy.orm import Session

from config import get_db, SubscriptionTable
from . import subscriptions_pb2, subscriptions_pb2_grpc
from dotenv import load_dotenv

load_dotenv()
GRPC_PORT = os.getenv("GRPC_PORT")

def _ts(dt):
    ts = Timestamp()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ts.FromDatetime(dt)
    return ts

class SubscriptionService(subscriptions_pb2_grpc.SubscriptionServiceServicer):
    def __init__(self):
        self._lock = asyncio.Lock()

    async def GetUserSubscription(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            try:
                subscription = db.query(SubscriptionTable).filter(
                    SubscriptionTable.user_id == request.user_id
                ).first()
            finally:
                db.close()

        if not subscription:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Subscription not found")

        response = subscriptions_pb2.GetUserSubscriptionResponse()
        response.subscription.subscription_id = subscription.subscription_id
        response.subscription.user_id = subscription.user_id
        response.subscription.type = subscription.type
        response.subscription.status = subscription.status

        if subscription.start_date:
            response.subscription.start_date.CopyFrom(_ts(subscription.start_date))
        if subscription.end_date:
            response.subscription.end_date.CopyFrom(_ts(subscription.end_date))

        return response

async def serve():
    server = grpc.aio.server()
    subscriptions_pb2_grpc.add_SubscriptionServiceServicer_to_server(
        SubscriptionService(), server
    )
    address = f'[::]:{GRPC_PORT}'
    server.add_insecure_port(address)
    await server.start()
    print(f"Subscriptions gRPC server running on port ${GRPC_PORT}")
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())