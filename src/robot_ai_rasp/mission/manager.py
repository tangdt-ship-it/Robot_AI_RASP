from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

from ..robotlink.client import RobotLinkClient, RobotLinkError
from ..robotlink.models import DistanceResult, Odometry, TurnResult
from ..safety.gate import MotionPreflight, PreflightReport


class MissionState(str, Enum):
    IDLE = "IDLE"
    PREFLIGHT = "PREFLIGHT"
    MOVING = "MOVING"
    TURNING = "TURNING"
    HOLD = "HOLD"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


@dataclass(slots=True)
class HeldDistanceMission:
    forward: bool
    target_mm: int
    speed: int
    start_odometry: Odometry
    remaining_mm: int
    reset_generation: int


class MissionManager:
    """High-level mission owner. No automatic resume after STOP/HOLD/AI interruption."""

    def __init__(self, robot: RobotLinkClient, preflight: MotionPreflight):
        self.robot = robot
        self.preflight = preflight
        self.state = MissionState.IDLE
        self.last_preflight: PreflightReport | None = None
        self._mission_lock = asyncio.Lock()
        self._active_task: asyncio.Task | None = None
        self._held: HeldDistanceMission | None = None

    async def _prepare(self) -> PreflightReport:
        self.state = MissionState.PREFLIGHT
        if not self.robot.protocol_compatible:
            await self.robot.negotiate()
        await self.robot.set_mode(True)
        report = await self.preflight.evaluate()
        self.last_preflight = report
        if not report.passed:
            self.state = MissionState.FAILED
            with contextlib.suppress(Exception):
                await self.robot.stop()
            raise RobotLinkError("preflight failed: " + ",".join(report.blockers))
        return report

    async def move_distance(self, forward: bool, distance_mm: int, speed: int = 20) -> DistanceResult:
        async with self._mission_lock:
            await self._prepare()
            self.state = MissionState.MOVING
            start = await self.robot.get_odometry()
            try:
                result = await self.robot.move_distance(forward, distance_mm, speed)
            except Exception:
                self.state = MissionState.FAILED
                raise
            self.state = MissionState.COMPLETE if result.completed else MissionState.FAILED
            self._held = None
            return result

    async def turn_relative(self, left: bool, angle_deg: int, speed: int = 20) -> TurnResult:
        async with self._mission_lock:
            await self._prepare()
            self.state = MissionState.TURNING
            try:
                result = await self.robot.turn_relative(left, angle_deg, speed)
            except Exception:
                self.state = MissionState.FAILED
                raise
            self.state = MissionState.COMPLETE
            return result

    async def turn_absolute(self, heading_deg: int, speed: int = 20) -> TurnResult:
        async with self._mission_lock:
            await self._prepare()
            self.state = MissionState.TURNING
            try:
                result = await self.robot.turn_absolute(heading_deg, speed)
            except Exception:
                self.state = MissionState.FAILED
                raise
            self.state = MissionState.COMPLETE
            return result

    async def hold_distance(self, forward: bool, target_mm: int, speed: int, start: Odometry) -> HeldDistanceMission:
        """Explicit HOLD boundary. Caller supplies the mission start odometry."""
        await self.robot.stop()
        now = await self.robot.get_odometry()
        if now.reset_generation != start.reset_generation:
            self.state = MissionState.FAILED
            raise RobotLinkError("encoder reset generation changed across HOLD")
        travelled = abs(now.distance_mm - start.distance_mm)
        remaining = max(0, int(round(target_mm - travelled)))
        self._held = HeldDistanceMission(forward, target_mm, speed, start, remaining, now.reset_generation)
        self.state = MissionState.HOLD
        return self._held

    async def resume_held(self) -> DistanceResult:
        """Manual/explicit resume only; never called automatically after AI interaction."""
        if self.state != MissionState.HOLD or self._held is None:
            raise RobotLinkError("no held mission")
        held = self._held
        now = await self.robot.get_odometry()
        if now.reset_generation != held.reset_generation:
            self.state = MissionState.FAILED
            raise RobotLinkError("encoder reset generation changed before RESUME")
        if held.remaining_mm <= 0:
            self.state = MissionState.COMPLETE
            return DistanceResult(completed=True, target_mm=held.target_mm, travelled_mm=held.target_mm)
        return await self.move_distance(held.forward, held.remaining_mm, held.speed)

    async def cancel(self) -> None:
        await self.robot.stop()
        with contextlib.suppress(Exception):
            await self.robot.set_mode(False)
        self._held = None
        self.state = MissionState.CANCELLED


import contextlib  # kept at end to make cancellation intent obvious near uses
