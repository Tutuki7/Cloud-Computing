import grpc
import os
from dotenv import load_dotenv
from . import subscriptions_pb2
from . import subscriptions_pb2_grpc

load_dotenv()
GRPC_URL = os.getenv("GRPC_URL")

def run():
    with grpc.insecure_channel(GRPC_URL) as channel:
        stub = subscriptions_pb2_grpc.SubscriptionServiceStub(channel)
        try:
            response = stub.GetUserSubscription(
                subscriptions_pb2.GetUserSubscriptionRequest(user_id=90)
            )
            print("Response:", response)
        except grpc.RpcError as e:
            print("code:", e.code())
            print("details:", e.details())

if __name__ == "__main__":
    run()