from __future__ import annotations

from dataclasses import dataclass, field

from ..config import SafetyConfig
from ..robotlink.client import RobotLinkClient


@dataclass(frozen=True, slots=True)
class PreflightReport:
    passed: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evidence: dict[str, object] = field(default_factory=dict)


class MotionPreflight:
    """Fail-closed high-level gate. STM32 remains the final safety authority."""

    def __init__(self, robot: RobotLinkClient, config: SafetyConfig):
        self.robot = robot
        self.config = config

    async def evaluate(self) -> PreflightReport:
        blockers: list[str] = []
        warnings: list[str] = []
        evidence: dict[str, object] = {}

        if self.config.require_robotlink and not self.robot.session_ready():
            blockers.append("ROBOTLINK_SESSION_NOT_READY")
            return PreflightReport(False, tuple(blockers), tuple(warnings), evidence)

        try:
            state = await self.robot.get_state()
            evidence["owner"] = state.motion_owner
            evidence["ai_mode"] = state.ai_mode
            evidence["moving"] = state.moving
        except Exception as exc:
            return PreflightReport(False, ("STATE_UNAVAILABLE",), (), {"error": str(exc)})

        if not state.ai_mode:
            blockers.append("MODE_NOT_AI")
        if self.config.require_owner and state.motion_owner.upper() != "AI":
            blockers.append("MOTION_OWNER_NOT_AI")

        if self.config.require_sensor_health:
            try:
                obstacle = await self.robot.get_obstacle()
                evidence["obstacle_zone"] = obstacle.zone
                evidence["obstacle_health"] = obstacle.health
                if not obstacle.valid or not obstacle.fresh or not obstacle.echo_valid:
                    blockers.append("FRONT_SENSOR_NOT_FRESH")
                if obstacle.health.upper() not in {"OK", "HEALTHY"}:
                    blockers.append("FRONT_SENSOR_UNHEALTHY")
                if obstacle.zone.upper() in {"BLOCKED", "EMERGENCY"} or obstacle.limited:
                    blockers.append("PATH_BLOCKED")
            except Exception as exc:
                blockers.append("OBSTACLE_UNAVAILABLE")
                evidence["obstacle_error"] = str(exc)

        if self.config.require_encoder_health:
            try:
                encoder = await self.robot.get_encoder_status()
                evidence["encoder_health"] = encoder.health
                if not encoder.valid or not encoder.ready or encoder.health.upper() not in {"OK", "HEALTHY"}:
                    blockers.append("ENCODER_UNHEALTHY")
            except Exception as exc:
                blockers.append("ENCODER_UNAVAILABLE")
                evidence["encoder_error"] = str(exc)

        if self.config.require_odometry_health:
            try:
                odometry = await self.robot.get_odometry()
                evidence["reset_generation"] = odometry.reset_generation
                evidence["x_mm"] = odometry.x_mm
                evidence["y_mm"] = odometry.y_mm
                if not odometry.valid:
                    blockers.append("ODOMETRY_INVALID")
            except Exception as exc:
                blockers.append("ODOMETRY_UNAVAILABLE")
                evidence["odometry_error"] = str(exc)

        try:
            fusion = await self.robot.get_fusion_status()
            evidence["fusion_health"] = fusion.health
            evidence["fusion_confidence"] = fusion.confidence_pct
            if not fusion.valid or not fusion.ready or fusion.health.upper() not in {"OK", "HEALTHY", "FUSED"}:
                blockers.append("FUSION_UNHEALTHY")
        except Exception as exc:
            blockers.append("FUSION_UNAVAILABLE")
            evidence["fusion_error"] = str(exc)

        return PreflightReport(not blockers, tuple(dict.fromkeys(blockers)), tuple(warnings), evidence)
