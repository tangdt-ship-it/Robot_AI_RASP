from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(slots=True)
class RobotState:
    valid: bool = False
    ai_mode: bool = False
    heading_deg: float = 0.0
    speed: int = 0
    left: int = 0
    right: int = 0
    moving: bool = False
    brake_enabled: bool = False
    ramp_enabled: bool = False
    compass_ok: bool = False
    ps2_ok: bool = False
    motion_owner: str = "UNKNOWN"
    received_at: float = 0.0
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ObstacleStatus:
    valid: bool = False
    fresh: bool = False
    echo_valid: bool = False
    health: str = "UNKNOWN"
    distance_cm: float = 0.0
    approach_rate_cm_s: float = 0.0
    zone: str = "UNKNOWN"
    limited: bool = False
    front_left_distance_cm: float = 0.0
    front_right_distance_cm: float = 0.0
    front_left_zone: str = "UNKNOWN"
    front_right_zone: str = "UNKNOWN"
    front_left_health: str = "UNKNOWN"
    front_right_health: str = "UNKNOWN"
    front_left_age_ms: int = 0
    front_right_age_ms: int = 0
    encoder_reset_generation: int = 0
    suggested_avoidance: str = ""


@dataclass(slots=True)
class Odometry:
    valid: bool = False
    distance_mm: float = 0.0
    x_mm: float = 0.0
    y_mm: float = 0.0
    heading_rad: float = 0.0
    left_ticks: int = 0
    right_ticks: int = 0
    reset_generation: int = 0


@dataclass(slots=True)
class EncoderStatus:
    valid: bool = False
    ready: bool = False
    health: str = "UNKNOWN"
    left_velocity_mm_s: float = 0.0
    right_velocity_mm_s: float = 0.0


@dataclass(slots=True)
class ImuStatus:
    valid: bool = False
    ready: bool = False
    calibrated: bool = False
    health: str = "UNKNOWN"
    gyro_z_dps: float = 0.0
    accel_x_g: float = 0.0
    accel_y_g: float = 0.0
    accel_z_g: float = 0.0


@dataclass(slots=True)
class FusionStatus:
    valid: bool = False
    ready: bool = False
    health: str = "UNKNOWN"
    heading_deg: float = 0.0
    yaw_rate_dps: float = 0.0
    confidence_pct: float = 0.0
    source: str = "UNKNOWN"


@dataclass(slots=True)
class TurnResult:
    completed: bool = False
    session_id: int = 0
    operation_id: int = 0
    heading_deg: float = 0.0
    target_deg: float = 0.0
    error_deg: float = 0.0
    raw: tuple[str, ...] = ()


class DistanceCode(str, Enum):
    NONE = "NONE"
    DONE = "DONE"
    TIMEOUT = "TIMEOUT"
    OBSTACLE = "OBSTACLE"
    ENCODER_FAULT = "ENCODER_FAULT"
    LINK_ERROR = "LINK_ERROR"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class DistanceResult:
    code: DistanceCode = DistanceCode.NONE
    completed: bool = False
    session_id: int = 0
    operation_id: int = 0
    target_mm: float = 0.0
    travelled_mm: float = 0.0
    raw: tuple[str, ...] = ()
