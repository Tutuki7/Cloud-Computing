from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import grpc
import os

from . import users_pb2, users_pb2_grpc
from dotenv import load_dotenv

load_dotenv()
GRPC_URL = os.getenv("USER_GRPC_URL")

class UserGrpcClient:
    def __init__(self, target: str = GRPC_URL) -> None:
        self._target = target
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[users_pb2_grpc.UserServiceStub] = None

    async def start(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = users_pb2_grpc.UserServiceStub(self._channel)

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
        self._channel = None
        self._stub = None

    def _require_stub(self) -> users_pb2_grpc.UserServiceStub:
        if self._stub is None:
            raise RuntimeError("UserGrpcClient not started. Call await client.start().")
        return self._stub

    async def validate_user(self, user_id: int) -> bool:
        stub = self._require_stub()
        req = users_pb2.ValidateUserRequest(user_id=user_id)
        resp = await stub.ValidateUser(req)
        return resp.exists