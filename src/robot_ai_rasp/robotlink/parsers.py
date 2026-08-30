from __future__ import annotations

import time

from .frame import InboundFrame, key_values
from .models import EncoderStatus, FusionStatus, ImuStatus, ObstacleStatus, Odometry, RobotState


def _bool(value: str | None) -> bool:
    return str(value or "").upper() in {"1", "ON", "TRUE", "OK", "YES", "AI"}


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def _int(value: str | None, default: int = 0) -> int:
    try:
        return int(value, 10) if value is not None else default
    except ValueError:
        return default


def parse_state(frame: InboundFrame) -> RobotState:
    if frame.kind != "STATE":
        raise ValueError("not a STATE frame")
    values = key_values(frame, 1)
    if "MODE" in values:
        return RobotState(
            valid=True,
            ai_mode=values.get("MODE", "").upper() == "AI",
            heading_deg=_float(values.get("H")),
            speed=_int(values.get("SPEED")),
            left=_int(values.get("L")),
            right=_int(values.get("R")),
            moving=_bool(values.get("MOVE")),
            brake_enabled=values.get("BRAKE", "").upper() == "ON",
            ramp_enabled=values.get("RAMP", "").upper() == "ON",
            compass_ok=values.get("COMPASS", "").upper() == "OK",
            ps2_ok=values.get("PS2", "").upper() != "LOST",
            motion_owner=values.get("OWNER", "UNKNOWN"),
            received_at=time.monotonic(),
            raw=values,
        )

    # Legacy: STATE,AI,H,0,S,10,L,0,R,0,MOVE,0
    fields = frame.fields
    try:
        values = {fields[i].upper(): fields[i + 1] for i in range(2, len(fields) - 1, 2)}
        return RobotState(
            valid=True,
            ai_mode=fields[1].upper() == "AI",
            heading_deg=_float(values.get("H")),
            speed=_int(values.get("S")),
            left=_int(values.get("L")),
            right=_int(values.get("R")),
            moving=_bool(values.get("MOVE")),
            motion_owner="UNKNOWN",
            received_at=time.monotonic(),
            raw=values,
        )
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid STATE frame: {frame.raw}") from exc


def _value_pairs(frame: InboundFrame, subtype: str) -> dict[str, str]:
    if len(frame.fields) < 2 or frame.kind != "VALUE" or frame.fields[1].upper() != subtype:
        raise ValueError(f"not VALUE,{subtype}")
    return key_values(frame, 2)


def parse_odometry(frame: InboundFrame) -> Odometry:
    v = _value_pairs(frame, "ODOMETRY")
    return Odometry(
        valid=True,
        distance_mm=_float(v.get("DIST")),
        x_mm=_float(v.get("X")),
        y_mm=_float(v.get("Y")),
        heading_rad=_float(v.get("H")),
        left_ticks=_int(v.get("LT")),
        right_ticks=_int(v.get("RT")),
        reset_generation=_int(v.get("RESET_GEN")),
    )


def parse_encoder(frame: InboundFrame) -> EncoderStatus:
    v = _value_pairs(frame, "ENCODER")
    return EncoderStatus(
        valid=True,
        ready=_bool(v.get("READY")),
        health=v.get("HEALTH", "UNKNOWN"),
        left_velocity_mm_s=_float(v.get("LV")),
        right_velocity_mm_s=_float(v.get("RV")),
    )


def parse_imu(frame: InboundFrame) -> ImuStatus:
    v = _value_pairs(frame, "IMU")
    return ImuStatus(
        valid=True,
        ready=_bool(v.get("READY")),
        calibrated=_bool(v.get("CAL")),
        health=v.get("HEALTH", "UNKNOWN"),
        gyro_z_dps=_float(v.get("GZ")),
        accel_x_g=_float(v.get("AX")),
        accel_y_g=_float(v.get("AY")),
        accel_z_g=_float(v.get("AZ")),
    )


def parse_fusion(frame: InboundFrame) -> FusionStatus:
    v = _value_pairs(frame, "FUSION")
    return FusionStatus(
        valid=True,
        ready=_bool(v.get("READY")),
        health=v.get("HEALTH", "UNKNOWN"),
        heading_deg=_float(v.get("H")),
        yaw_rate_dps=_float(v.get("RATE")),
        confidence_pct=_float(v.get("CONF")),
        source=v.get("SRC", "UNKNOWN"),
    )


def parse_obstacle(frame: InboundFrame) -> ObstacleStatus:
    v = _value_pairs(frame, "OBSTACLE")
    health = v.get("HEALTH") or ("HEALTHY" if _bool(v.get("FRESH")) and _bool(v.get("ECHO")) else "UNKNOWN")
    return ObstacleStatus(
        valid=True,
        fresh=_bool(v.get("FRESH")),
        echo_valid=_bool(v.get("ECHO")),
        health=health,
        distance_cm=_float(v.get("DIST")),
        approach_rate_cm_s=_float(v.get("RATE")),
        zone=v.get("ZONE", "UNKNOWN"),
        limited=_bool(v.get("LIMIT")),
        front_left_distance_cm=_float(v.get("LEFT")),
        front_right_distance_cm=_float(v.get("RIGHT")),
        front_left_zone=v.get("LZ", "UNKNOWN"),
        front_right_zone=v.get("RZ", "UNKNOWN"),
        front_left_health=v.get("LH", "UNKNOWN"),
        front_right_health=v.get("RH", "UNKNOWN"),
        front_left_age_ms=_int(v.get("LAGE")),
        front_right_age_ms=_int(v.get("RAGE")),
        encoder_reset_generation=_int(v.get("RESET_GEN")),
        suggested_avoidance=v.get("SUG", ""),
    )
