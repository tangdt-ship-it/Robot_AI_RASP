from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RobotLinkConfig:
    device: str = "/dev/ttyAMA0"
    baudrate: int = 115200
    command_timeout_s: float = 2.0
    motion_timeout_s: float = 30.0
    heartbeat_s: float = 0.5
    stale_state_s: float = 1.5


@dataclass(frozen=True)
class SafetyConfig:
    require_robotlink: bool = True
    require_owner: bool = True
    require_sensor_health: bool = True
    require_encoder_health: bool = True
    require_odometry_health: bool = True
    automatic_detour: bool = False
    automatic_reverse: bool = False
    automatic_resume_after_ai: bool = False


@dataclass(frozen=True)
class WakeWordConfig:
    enabled: bool = True
    phrase: str = "ROBOT"
    backend: str = "sherpa_onnx"
    sample_rate: int = 16000
    threshold: float = 0.25
    score: float = 2.0
    cooldown_s: float = 1.5
    model_dir: str = "/opt/robot-ai/models/kws-gigaspeech"
    keyword_tokens: str = "R OW1 B AA2 T @ROBOT"


@dataclass(frozen=True)
class AppConfig:
    robotlink: RobotLinkConfig
    safety: SafetyConfig
    wakeword: WakeWordConfig
    raw: dict[str, Any]


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"configuration section {name!r} must be a mapping")
    return value


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError("root configuration must be a mapping")
    return AppConfig(
        robotlink=RobotLinkConfig(**_section(raw, "robotlink")),
        safety=SafetyConfig(**_section(raw, "safety")),
        wakeword=WakeWordConfig(**_section(raw, "wakeword")),
        raw=raw,
    )
