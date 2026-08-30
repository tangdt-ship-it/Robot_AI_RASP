from __future__ import annotations

import asyncio
import dataclasses
import enum
import json
import logging
import os
from pathlib import Path
from typing import Any

from ..blackbox import SafetyBlackBox
from ..config import AppConfig, load_config
from ..mission.manager import MissionManager, MissionState
from ..robotlink.client import RobotLinkClient
from ..safety.gate import MotionPreflight
from ..storage.route_store import RouteStore

LOG = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {k: _jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class RobotDaemon:
    """Single owner of UART/motion. Xiaozhi, web and UI call it through a Unix socket."""

    def __init__(self, config_path: str | Path, socket_path: str | Path = "/run/robot-ai/robotd.sock"):
        self.config_path = Path(config_path)
        self.config: AppConfig = load_config(config_path)
        self.socket_path = Path(socket_path)
        data_dir = Path(self.config.raw.get("system", {}).get("data_dir", "/var/lib/robot-ai"))
        self.blackbox = SafetyBlackBox(512, data_dir / "safety-blackbox.jsonl")
        self.robot = RobotLinkClient(self.config.robotlink, self.blackbox)
        self.preflight = MotionPreflight(self.robot, self.config.safety)
        self.mission = MissionManager(self.robot, self.preflight)
        self.routes = RouteStore(data_dir / "robot.db")
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            self.socket_path.unlink()
        await self.robot.connect()
        self._server = await asyncio.start_unix_server(self._handle_client, path=str(self.socket_path))
        os.chmod(self.socket_path, 0o660)
        LOG.info("robotd listening on %s", self.socket_path)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        with contextlib.suppress(Exception):
            await self.robot.stop()
        with contextlib.suppress(Exception):
            await self.robot.set_mode(False)
        await self.robot.close()
        self.routes.close()
        with contextlib.suppress(FileNotFoundError):
            self.socket_path.unlink()

    async def serve_forever(self) -> None:
        if not self._server:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while line := await reader.readline():
                try:
                    req = json.loads(line)
                    result = await self.dispatch(str(req.get("method", "")), req.get("params") or {})
                    response = {"id": req.get("id"), "ok": True, "result": _jsonable(result)}
                except Exception as exc:
                    LOG.exception("RPC failure")
                    response = {"id": req.get("id") if isinstance(req, dict) else None, "ok": False, "error": str(exc)}
                writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode())
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "robot.ping":
            return {"connected": self.robot.is_connected(), "protocol": self.robot.protocol_compatible}
        if method == "robot.get_state":
            return await self.robot.get_state()
        if method == "robot.get_odometry":
            return await self.robot.get_odometry()
        if method == "robot.get_encoder_status":
            return await self.robot.get_encoder_status()
        if method == "robot.get_imu_status":
            return await self.robot.get_imu_status()
        if method == "robot.get_fusion_status":
            return await self.robot.get_fusion_status()
        if method == "robot.get_obstacle":
            return await self.robot.get_obstacle()
        if method == "robot.get_mission_state":
            return {"state": self.mission.state.value, "preflight": _jsonable(self.mission.last_preflight)}
        if method == "robot.stop":
            stopped = await self.robot.stop()
            self.mission.state = MissionState.CANCELLED
            return {"stopped": stopped}
        if method == "robot.cancel_mission":
            await self.mission.cancel()
            return {"state": self.mission.state.value}
        if method == "robot.move_distance":
            direction = str(params.get("direction", "forward")).lower()
            return await self.mission.move_distance(
                direction not in {"back", "backward", "reverse"},
                int(params["distance_mm"]),
                int(params.get("speed", 20)),
            )
        if method == "robot.turn_relative":
            direction = str(params.get("direction", "left")).lower()
            return await self.mission.turn_relative(
                direction == "left", int(params["angle_deg"]), int(params.get("speed", 20))
            )
        if method == "robot.turn_to_heading":
            return await self.mission.turn_absolute(int(params["heading_deg"]), int(params.get("speed", 20)))
        if method == "robot.get_speed":
            return {"speed": await self.robot.get_speed()}
        if method == "robot.set_speed":
            return {"ok": await self.robot.set_speed(int(params["speed"]))}
        if method == "robot.get_brake":
            return {"enabled": await self.robot.get_brake()}
        if method == "robot.set_brake":
            return {"ok": await self.robot.set_brake(bool(params["enabled"]))}
        if method == "robot.get_ramp":
            return {"enabled": await self.robot.get_ramp()}
        if method == "robot.set_ramp":
            return {"ok": await self.robot.set_ramp(bool(params["enabled"]))}
        if method == "robot.get_heading":
            return {"heading_deg": await self.robot.get_heading()}
        if method == "robot.get_compass_status":
            return await self.robot.get_compass_status()
        if method == "robot.reset_compass":
            return {"ok": await self.robot.reset_compass()}
        if method == "robot.reset_encoders":
            return {"ok": await self.robot.reset_encoders()}
        if method == "robot.get_ps2_status":
            return await self.robot.get_ps2_status()
        if method == "robot.preflight":
            return await self.preflight.evaluate()
        if method == "robot.set_home":
            odom = await self.robot.get_odometry()
            return self.routes.set_home(odom.x_mm, odom.y_mm, odom.heading_rad, odom.reset_generation)
        if method == "robot.get_home":
            return self.routes.get_home()
        if method == "robot.list_routes":
            return self.routes.list_routes()
        if method == "robot.blackbox":
            return self.blackbox.snapshot()
        raise ValueError(f"unknown RPC method: {method}")


import contextlib
