from __future__ import annotations

import asyncio
import itertools
import json
from pathlib import Path
from typing import Any


class RobotRpcError(RuntimeError):
    pass


class RobotRpcClient:
    def __init__(self, socket_path: str | Path = "/run/robot-ai/robotd.sock"):
        self.socket_path = str(socket_path)
        self._ids = itertools.count(1)

    async def call(self, method: str, **params: Any) -> Any:
        request_id = next(self._ids)
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        try:
            request = {"id": request_id, "method": method, "params": params}
            writer.write((json.dumps(request, ensure_ascii=False) + "\n").encode())
            await writer.drain()
            raw = await reader.readline()
            if not raw:
                raise RobotRpcError("robotd closed the RPC connection")
            response = json.loads(raw)
            if response.get("id") != request_id:
                raise RobotRpcError("RPC id mismatch")
            if not response.get("ok", False):
                raise RobotRpcError(str(response.get("error", "unknown robotd error")))
            return response.get("result")
        finally:
            writer.close()
            await writer.wait_closed()
