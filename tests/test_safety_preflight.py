from types import SimpleNamespace

import pytest

from robot_ai_rasp.config import SafetyConfig
from robot_ai_rasp.safety.gate import MotionPreflight


class FakeRobot:
    def __init__(self, *, ready=True, owner="AI", zone="CLEAR"):
        self.ready = ready
        self.owner = owner
        self.zone = zone

    def session_ready(self):
        return self.ready

    async def get_state(self):
        return SimpleNamespace(motion_owner=self.owner, ai_mode=True, moving=False)

    async def get_obstacle(self):
        return SimpleNamespace(valid=True, fresh=True, echo_valid=True, health="HEALTHY", zone=self.zone, limited=False)

    async def get_encoder_status(self):
        return SimpleNamespace(valid=True, ready=True, health="OK")

    async def get_odometry(self):
        return SimpleNamespace(valid=True, reset_generation=2, x_mm=0.0, y_mm=0.0)

    async def get_fusion_status(self):
        return SimpleNamespace(valid=True, ready=True, health="FUSED", confidence_pct=99.0)


@pytest.mark.asyncio
async def test_preflight_passes_healthy_robot():
    report = await MotionPreflight(FakeRobot(), SafetyConfig()).evaluate()
    assert report.passed
    assert not report.blockers


@pytest.mark.asyncio
async def test_preflight_fails_closed_without_link():
    report = await MotionPreflight(FakeRobot(ready=False), SafetyConfig()).evaluate()
    assert not report.passed
    assert "ROBOTLINK_SESSION_NOT_READY" in report.blockers


@pytest.mark.asyncio
async def test_preflight_blocks_non_ai_owner():
    report = await MotionPreflight(FakeRobot(owner="PS2"), SafetyConfig()).evaluate()
    assert not report.passed
    assert "MOTION_OWNER_NOT_AI" in report.blockers


@pytest.mark.asyncio
async def test_preflight_blocks_obstacle():
    report = await MotionPreflight(FakeRobot(zone="BLOCKED"), SafetyConfig()).evaluate()
    assert not report.passed
    assert "PATH_BLOCKED" in report.blockers
