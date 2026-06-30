import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import grpc

from config import get_db, UserTable
from sqlalchemy.orm import Session

import users_pb2
import users_pb2_grpc


class UserService(users_pb2_grpc.UserServiceServicer):
    def __init__(self):
        self._lock = asyncio.Lock()

    async def GetUser(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            user = db.query(UserTable).filter(UserTable.user_id == request.user_id).first()

        if not user:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("User not found")
            return users_pb2.GetUserResponse()

        return users_pb2.GetUserResponse(
            user=users_pb2.User(
                user_id=user.user_id,
                username=user.username,
                email=user.email,
                gender=user.gender or "",
                age=user.age or 0,
            )
        )

    async def ValidateUser(self, request, context):
        async with self._lock:
            db: Session = next(get_db())
            exists = db.query(UserTable).filter(UserTable.user_id == request.user_id).first() is not None

        return users_pb2.ValidateUserResponse(exists=exists)


async def serve(host="0.0.0.0", port=50053):
    server = grpc.aio.server()
    users_pb2_grpc.add_UserServiceServicer_to_server(UserService(), server)
    server.add_insecure_port(f"{host}:{port}")
    await server.start()
    print(f"User gRPC server running on {host}:{port}")
    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())