from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

import serial_asyncio

from ..blackbox import SafetyBlackBox
from ..config import RobotLinkConfig
from .frame import InboundFrame, encode_command, parse_inbound
from .models import (
    DistanceCode,
    DistanceResult,
    FusionStatus,
    ImuStatus,
    ObstacleStatus,
    Odometry,
    RobotState,
    TurnResult,
)
from .parsers import (
    parse_encoder,
    parse_fusion,
    parse_imu,
    parse_obstacle,
    parse_odometry,
    parse_state,
)

LOG = logging.getLogger(__name__)
Predicate = Callable[[InboundFrame], bool]


class RobotLinkError(RuntimeError):
    pass


class RobotLinkTimeout(RobotLinkError):
    pass


@dataclass(slots=True)
class _Waiter:
    predicate: Predicate
    future: asyncio.Future[InboundFrame]


def _nonzero_u32() -> int:
    value = 0
    while value in {0, 0xFFFFFFFF}:
        value = secrets.randbits(32)
    return value


def _field_after(frame: InboundFrame, label: str, default: str = "") -> str:
    target = label.upper()
    for index, field in enumerate(frame.fields[:-1]):
        if field.upper() == target:
            return frame.fields[index + 1]
    return default


class RobotLinkClient:
    """Async RobotLink V3 client preserving the ESP32 fail-closed contract."""

    def __init__(self, config: RobotLinkConfig, blackbox: SafetyBlackBox | None = None):
        self.config = config
        self.blackbox = blackbox or SafetyBlackBox()
        self._reader: asyncio.StreamReader | None = None
        self._writer = None
        self._rx_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._recovery_task: asyncio.Task | None = None
        self._transaction_lock = asyncio.Lock()
        self._tx_lock = asyncio.Lock()
        self._motion_lock = asyncio.Lock()
        self._waiters: list[_Waiter] = []
        self._sequence = 0
        self._last_rx = 0.0
        self._protocol_compatible = False
        self._motion_lease = False
        self._active_motion_type = ""
        self._stop_in_progress = False
        self._ps2_override = False
        self._session_id = _nonzero_u32()
        self._next_operation_id = _nonzero_u32()
        self._active_pair: tuple[int, int] | None = None
        self._terminal_operation_id = 0
        self._motion_cancel_event = asyncio.Event()
        self._cached_obstacle = ObstacleStatus()

    @property
    def protocol_compatible(self) -> bool:
        return self._protocol_compatible

    @property
    def motion_session_id(self) -> int:
        return self._session_id

    @property
    def motion_lease_active(self) -> bool:
        return self._motion_lease

    @property
    def ps2_override_active(self) -> bool:
        return self._ps2_override

    def is_connected(self) -> bool:
        return self._last_rx > 0 and (time.monotonic() - self._last_rx) <= self.config.stale_state_s

    def session_ready(self) -> bool:
        return self._protocol_compatible and self.is_connected() and not self._stop_in_progress

    async def connect(self) -> None:
        if self._reader is not None:
            return
        self._reader, self._writer = await serial_asyncio.open_serial_connection(
            url=self.config.device, baudrate=self.config.baudrate
        )
        self._rx_task = asyncio.create_task(self._reader_loop(), name="robotlink-rx")
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(), name="robotlink-heartbeat")
        self._recovery_task = asyncio.create_task(self._recovery_loop(), name="robotlink-recovery")

    async def close(self) -> None:
        tasks = (self._recovery_task, self._heartbeat_task, self._rx_task)
        for task in tasks:
            if task:
                task.cancel()
        for task in tasks:
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._writer is not None:
            self._writer.close()
            wait_closed = getattr(self._writer, "wait_closed", None)
            if wait_closed:
                with contextlib.suppress(Exception):
                    await wait_closed()
        self._reader = None
        self._writer = None
        self._invalidate_session("CLOSE")

    async def _reader_loop(self) -> None:
        assert self._reader is not None
        receiving = False
        buffer = bytearray()
        try:
            while True:
                byte = await self._reader.readexactly(1)
                value = byte[0]
                if value == ord("<"):
                    receiving = True
                    buffer.clear()
                    continue
                if not receiving:
                    continue
                if value == ord(">"):
                    receiving = False
                    frame = parse_inbound(bytes(buffer))
                    if frame:
                        self._dispatch(frame)
                    buffer.clear()
                    continue
                if value in (10, 13):
                    continue
                if len(buffer) >= 1024:
                    receiving = False
                    buffer.clear()
                    continue
                buffer.append(value)
        except (asyncio.IncompleteReadError, OSError) as exc:
            LOG.warning("RobotLink reader stopped: %s", exc)
            self._invalidate_session("LINK_LOSS")
            self._fail_waiters(RobotLinkError("RobotLink disconnected"))

    def _dispatch(self, frame: InboundFrame) -> None:
        self._last_rx = time.monotonic()
        LOG.debug("ROBOT RX <%s>", frame.raw)
        if frame.kind == "BOOT" and frame.has("STM32"):
            self.blackbox.record("LINK_LOSS", *(self._active_pair or (0, 0)), detail="STM32_BOOT")
            self._invalidate_session("STM32_BOOT")
            self._motion_cancel_event.set()
            self._fail_waiters(RobotLinkError("STM32 rebooted"))
            return
        if frame.kind == "EVENT":
            self._handle_event(frame)
        if frame.kind == "VALUE" and len(frame.fields) > 1 and frame.fields[1].upper() == "OBSTACLE":
            with contextlib.suppress(ValueError):
                self._cached_obstacle = parse_obstacle(frame)

        delivered: list[_Waiter] = []
        for waiter in tuple(self._waiters):
            if waiter.future.done():
                delivered.append(waiter)
                continue
            try:
                matched = waiter.predicate(frame)
            except Exception as exc:
                waiter.future.set_exception(exc)
                delivered.append(waiter)
                continue
            if matched:
                waiter.future.set_result(frame)
                delivered.append(waiter)
        for waiter in delivered:
            with contextlib.suppress(ValueError):
                self._waiters.remove(waiter)

    def _handle_event(self, frame: InboundFrame) -> None:
        text = ",".join(frame.fields).upper()
        pair = self._active_pair or (0, 0)
        if text == "EVENT,AI_CANCELLED,PS2_OVERRIDE":
            self._ps2_override = True
            self._motion_lease = False
            self._motion_cancel_event.set()
            self.blackbox.record("PS2_OVERRIDE", *pair)
        elif text == "EVENT,STOP,MOTION_LEASE_TIMEOUT":
            self._motion_lease = False
            self._motion_cancel_event.set()
            self.blackbox.record("LEASE_TIMEOUT", *pair)
        elif text.startswith("EVENT,ENCODER,FAULT"):
            self._motion_lease = False
            self._motion_cancel_event.set()
            self.blackbox.record("ENCODER_FAULT", *pair)
        elif text.startswith("EVENT,OBSTACLE,STOPPED"):
            # ESP32 keeps the heartbeat alive during an avoidance TURN.
            if self._active_motion_type != "TURN":
                self._motion_lease = False
            self.blackbox.record("OBSTACLE_STOPPED", *pair)

    def _fail_waiters(self, exc: Exception) -> None:
        for waiter in tuple(self._waiters):
            if not waiter.future.done():
                waiter.future.set_exception(exc)
        self._waiters.clear()

    def _invalidate_motion(self, reason: str) -> None:
        if self._active_pair:
            self.blackbox.record("SESSION_CHANGE", *self._active_pair, detail=reason)
        self._active_pair = None
        self._terminal_operation_id = 0
        self._active_motion_type = ""
        self._motion_lease = False

    def _invalidate_session(self, reason: str) -> None:
        self._invalidate_motion(reason)
        self._protocol_compatible = False

    async def _send(self, body: str) -> None:
        if self._writer is None:
            raise RobotLinkError("RobotLink not connected")
        async with self._tx_lock:
            frame = encode_command(self._sequence, body)
            self._sequence = (self._sequence + 1) & 0xFFFF
            self._writer.write(frame)
            drain = getattr(self._writer, "drain", None)
            if drain:
                await drain()
        if body != "HB":
            LOG.info("ROBOT TX: %s", body)

    async def _wait_for(self, predicate: Predicate, timeout: float) -> InboundFrame:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[InboundFrame] = loop.create_future()
        waiter = _Waiter(predicate, future)
        self._waiters.append(waiter)
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            raise RobotLinkTimeout("RobotLink response timeout") from exc
        finally:
            with contextlib.suppress(ValueError):
                self._waiters.remove(waiter)

    async def _request(
        self,
        body: str,
        accept: Predicate,
        timeout: float | None = None,
        *,
        generic_errors: bool = True,
    ) -> InboundFrame:
        timeout = timeout or self.config.command_timeout_s

        def response(frame: InboundFrame) -> bool:
            if accept(frame):
                return True
            return generic_errors and frame.kind in {"NACK", "ERR"}

        async with self._transaction_lock:
            waiter = asyncio.create_task(self._wait_for(response, timeout))
            await asyncio.sleep(0)  # install waiter before bytes leave the UART
            await self._send(body)
            frame = await waiter
            if generic_errors and frame.kind in {"NACK", "ERR"} and not accept(frame):
                raise RobotLinkError(frame.raw)
            return frame

    async def ping(self, timeout: float | None = None) -> bool:
        await self._request("PING", lambda f: f.kind == "PONG", timeout)
        return True

    async def negotiate(self, timeout: float = 0.7) -> bool:
        if self._motion_lease or self._active_pair:
            raise RobotLinkError("cannot negotiate during motion")
        self._invalidate_session("NEGOTIATE")
        await self._request(
            "HELLO,PROTO,3",
            lambda f: f.kind == "HELLO" and f.has("STM32") and f.has("3"),
            timeout,
        )
        await self.ping(timeout)
        self._protocol_compatible = True
        self._session_id = (self._session_id + 1) & 0xFFFFFFFF or 1
        self.blackbox.record("SESSION_CHANGE", self._session_id, 0, "HELLO")
        return True

    async def _recovery_loop(self) -> None:
        await asyncio.sleep(0.8)
        while True:
            if (
                self._writer is not None
                and not self._protocol_compatible
                and not self._motion_lease
                and self._active_pair is None
                and not self._stop_in_progress
            ):
                with contextlib.suppress(RobotLinkError, RobotLinkTimeout, OSError):
                    await self.negotiate(0.7)
            await asyncio.sleep(0.75)

    async def set_mode(self, ai_mode: bool, timeout: float = 0.7) -> bool:
        if ai_mode and not self._protocol_compatible:
            await self.negotiate(timeout)
        if not ai_mode:
            self._motion_lease = False
        await self._request(f"MODE,{'AI' if ai_mode else 'MANUAL'}", lambda f: f.kind == "ACK", timeout)
        if ai_mode:
            self._ps2_override = False
        return True

    async def stop(self, timeout: float = 0.7) -> bool:
        self._stop_in_progress = True
        self._motion_lease = False
        active = self._active_pair or (0, 0)
        self.blackbox.record("STOP", *active, detail="STOP")
        # STOP is not a HELLO/PING session boundary on the ESP32 implementation.
        self._invalidate_motion("STOP")
        try:
            await self._request("STOP", lambda f: f.kind == "DONE" and f.has("STOP"), timeout)
            # Finite waiters are released only after physical DONE,STOP confirmation.
            self._motion_cancel_event.set()
            return True
        finally:
            self._stop_in_progress = False

    async def get_state(self, timeout: float = 0.7) -> RobotState:
        return parse_state(await self._request("GET,STATE", lambda f: f.kind == "STATE", timeout))

    async def get_odometry(self, timeout: float = 0.7) -> Odometry:
        frame = await self._request("GET,ODOMETRY", lambda f: f.kind == "VALUE" and f.has("ODOMETRY"), timeout)
        return parse_odometry(frame)

    async def get_encoder_status(self, timeout: float = 0.7):
        frame = await self._request("GET,ENCODER", lambda f: f.kind == "VALUE" and f.has("ENCODER"), timeout)
        return parse_encoder(frame)

    async def get_imu_status(self, timeout: float = 0.7) -> ImuStatus:
        frame = await self._request("GET,IMU", lambda f: f.kind == "VALUE" and f.has("IMU"), timeout)
        return parse_imu(frame)

    async def get_fusion_status(self, timeout: float = 0.7) -> FusionStatus:
        frame = await self._request("GET,FUSION", lambda f: f.kind == "VALUE" and f.has("FUSION"), timeout)
        return parse_fusion(frame)

    async def get_obstacle(self, timeout: float = 0.7) -> ObstacleStatus:
        frame = await self._request("GET,OBSTACLE", lambda f: f.kind == "VALUE" and f.has("OBSTACLE"), timeout)
        return parse_obstacle(frame)

    def get_cached_obstacle(self) -> ObstacleStatus:
        return self._cached_obstacle

    async def get_value(self, name: str, timeout: float = 0.7) -> str:
        upper = name.upper()
        frame = await self._request(f"GET,{upper}", lambda f: f.kind == "VALUE" and f.has(upper), timeout)
        if len(frame.fields) < 3:
            raise RobotLinkError(frame.raw)
        return frame.fields[2]

    async def get_heading(self, timeout: float = 0.7) -> float:
        return float(await self.get_value("HEADING", timeout))

    async def get_speed(self, timeout: float = 0.7) -> int:
        return int(await self.get_value("SPEED", timeout))

    async def get_brake(self, timeout: float = 0.7) -> bool:
        return (await self.get_value("BRAKE", timeout)).upper() == "ON"

    async def get_ramp(self, timeout: float = 0.7) -> bool:
        return (await self.get_value("RAMP", timeout)).upper() == "ON"

    async def get_compass_status(self, timeout: float = 0.7) -> dict[str, str]:
        frame = await self._request("GET,COMPASS_STATUS", lambda f: f.kind == "VALUE" and f.has("COMPASS"), timeout)
        return {frame.fields[i].upper(): frame.fields[i + 1] for i in range(2, len(frame.fields) - 1, 2)}

    async def get_ps2_status(self, timeout: float = 0.7) -> dict[str, str]:
        frame = await self._request("PS2,STATUS", lambda f: f.kind == "PS2" and f.has("STATE"), timeout)
        return {frame.fields[i].upper(): frame.fields[i + 1] for i in range(1, len(frame.fields) - 1, 2)}

    async def set_speed(self, speed: int, timeout: float = 0.7) -> bool:
        if not 10 <= speed <= 255:
            raise ValueError("speed must be 10..255")
        await self._request(f"SET,SPEED,{speed}", lambda f: f.kind == "ACK", timeout)
        return True

    async def set_brake(self, enabled: bool, timeout: float = 0.7) -> bool:
        await self._request(f"SET,BRAKE,{'ON' if enabled else 'OFF'}", lambda f: f.kind == "ACK", timeout)
        return True

    async def set_ramp(self, enabled: bool, timeout: float = 0.7) -> bool:
        await self._request(f"SET,RAMP,{'ON' if enabled else 'OFF'}", lambda f: f.kind == "ACK", timeout)
        return True

    async def reset_compass(self, timeout: float = 0.7) -> bool:
        await self._request("COMPASS,RESET", lambda f: f.kind == "ACK", timeout)
        return True

    async def reset_encoders(self, timeout: float = 0.7) -> bool:
        await self._request("ENCODER,RESET", lambda f: f.kind == "ACK", timeout)
        return True

    @staticmethod
    def _clamp_motion_speed(speed: int) -> int:
        return max(10, min(int(speed), 20))

    async def move_forward(self, speed: int = 20, timeout: float = 0.7) -> bool:
        await self._request(f"CMD,FWD,{self._clamp_motion_speed(speed)}", lambda f: f.kind == "ACK", timeout)
        return True

    async def move_backward(self, speed: int = 20, timeout: float = 0.7) -> bool:
        await self._request(f"CMD,BACK,{self._clamp_motion_speed(speed)}", lambda f: f.kind == "ACK", timeout)
        return True

    async def turn_left(self, speed: int = 20, timeout: float = 0.7) -> bool:
        await self._request(f"CMD,LEFT,{self._clamp_motion_speed(speed)}", lambda f: f.kind == "ACK", timeout)
        return True

    async def turn_right(self, speed: int = 20, timeout: float = 0.7) -> bool:
        await self._request(f"CMD,RIGHT,{self._clamp_motion_speed(speed)}", lambda f: f.kind == "ACK", timeout)
        return True

    async def start_continuous(self, forward: bool, speed: int = 20, timeout: float = 0.7) -> bool:
        command = f"MOVE,{'FWD' if forward else 'BACK'},{self._clamp_motion_speed(speed)},CONT"
        await self._request(command, lambda f: f.kind == "ACK", timeout)
        self._active_motion_type = "MOVE"
        self._motion_lease = True
        return True

    async def start_continuous_rotation(self, left: bool, speed: int = 20, timeout: float = 0.7) -> bool:
        command = f"MOVE,{'LEFT' if left else 'RIGHT'},{self._clamp_motion_speed(speed)},CONT"
        await self._request(command, lambda f: f.kind == "ACK", timeout)
        self._active_motion_type = "TURN"
        self._motion_lease = True
        return True

    def _begin_pair(self, motion_type: str) -> tuple[int, int]:
        if not self.session_ready() or self._active_pair is not None:
            raise RobotLinkError("motion session not ready")
        op = self._next_operation_id
        self._next_operation_id = (self._next_operation_id + 1) & 0xFFFFFFFF or 1
        self._active_pair = (self._session_id, op)
        self._terminal_operation_id = 0
        self._active_motion_type = motion_type
        self._motion_cancel_event.clear()
        self.blackbox.record("COMMAND_SEND", self._session_id, op, "MOTION")
        return self._active_pair

    @staticmethod
    def _match_pair(frame: InboundFrame, pair: tuple[int, int]) -> bool:
        return (
            frame.session_id == pair[0]
            and frame.operation_id == pair[1]
            and frame.session_id != 0
            and frame.operation_id != 0
        )

    async def _motion_ack(self, command: str, pair: tuple[int, int], timeout: float = 0.7) -> None:
        def accept(frame: InboundFrame) -> bool:
            if frame.kind not in {"ACK", "NACK", "ERR"}:
                return False
            if not self._match_pair(frame, pair):
                self.blackbox.record("ACK_STALE", frame.session_id, frame.operation_id, "MISMATCH_OR_MISSING")
                return False
            self.blackbox.record("ACK_ACCEPT", *pair, detail=frame.kind)
            return True

        # generic_errors=False is critical: a stale NACK/ERR must not abort the
        # current finite operation unless its SID/OP matches the pending pair.
        frame = await self._request(command, accept, timeout, generic_errors=False)
        if frame.kind != "ACK":
            raise RobotLinkError(frame.raw)

    async def _wait_motion_terminal(self, pair: tuple[int, int], motion: str, timeout: float) -> InboundFrame:
        motion = motion.upper()

        def terminal(frame: InboundFrame) -> bool:
            if frame.kind not in {"DONE", "ERR"} or not frame.has(motion):
                return False
            if not self._match_pair(frame, pair) or self._terminal_operation_id == pair[1]:
                self.blackbox.record("RESULT_STALE", frame.session_id, frame.operation_id, "MISMATCH_OR_DUPLICATE")
                return False
            self._terminal_operation_id = pair[1]
            self.blackbox.record("RESULT_ACCEPT", *pair, detail=f"{motion}_{frame.kind}")
            return True

        terminal_task = asyncio.create_task(self._wait_for(terminal, timeout))
        cancel_task = asyncio.create_task(self._motion_cancel_event.wait())
        done, pending = await asyncio.wait({terminal_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if cancel_task in done and cancel_task.result():
            terminal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await terminal_task
            raise RobotLinkError("motion cancelled by STOP/safety/PS2")
        return terminal_task.result()

    async def move_distance(
        self,
        forward: bool,
        distance_mm: int,
        speed: int,
        timeout: float | None = None,
    ) -> DistanceResult:
        distance_mm = max(1, min(int(distance_mm), 5000))
        speed = self._clamp_motion_speed(speed)
        timeout = timeout or self.config.motion_timeout_s
        async with self._motion_lock:
            pair = self._begin_pair("MOVE")
            command = f"MOVE,{'FWD' if forward else 'BACK'},{distance_mm},{speed},SID,{pair[0]},OP,{pair[1]}"
            try:
                await self._motion_ack(command, pair)
                self._motion_lease = True
                self.blackbox.record("LEASE_ACQUIRE", *pair, detail="MOVE")
                frame = await self._wait_motion_terminal(pair, "MOVE", timeout)
                self._motion_lease = False
                target = float(_field_after(frame, "TARGET", str(distance_mm)))
                travel = float(_field_after(frame, "TRAVEL", "0"))
                if frame.kind == "DONE":
                    return DistanceResult(DistanceCode.DONE, True, *pair, target, travel, frame.fields)

                code_text = frame.fields[2].upper() if len(frame.fields) > 2 else "LINK_ERROR"
                code = DistanceCode(code_text) if code_text in DistanceCode._value2member_map_ else DistanceCode.LINK_ERROR
                result = DistanceResult(code, False, *pair, target, travel, frame.fields)
                if not self._ps2_override and not self._stop_in_progress:
                    with contextlib.suppress(RobotLinkError, RobotLinkTimeout):
                        await self.stop()
                return result
            except (RobotLinkError, RobotLinkTimeout):
                self._motion_lease = False
                if not self._ps2_override and not self._stop_in_progress:
                    with contextlib.suppress(RobotLinkError, RobotLinkTimeout):
                        await self.stop()
                raise
            finally:
                self._active_pair = None
                self._terminal_operation_id = 0
                self._active_motion_type = ""

    async def turn_relative(self, left: bool, angle_deg: int, speed: int, timeout: float = 13.0) -> TurnResult:
        angle_deg = max(1, min(int(angle_deg), 180))
        return await self._turn(f"TURN,REL,{'LEFT' if left else 'RIGHT'},{angle_deg}", speed, timeout)

    async def turn_absolute(self, heading_deg: int, speed: int, timeout: float = 13.0) -> TurnResult:
        heading_deg = max(-180, min(int(heading_deg), 180))
        return await self._turn(f"TURN,ABS,{heading_deg}", speed, timeout)

    async def _turn(self, prefix: str, speed: int, timeout: float) -> TurnResult:
        speed = self._clamp_motion_speed(speed)
        async with self._motion_lock:
            pair = self._begin_pair("TURN")
            command = f"{prefix},{speed},SID,{pair[0]},OP,{pair[1]}"
            try:
                await self._motion_ack(command, pair)
                self._motion_lease = True
                self.blackbox.record("LEASE_ACQUIRE", *pair, detail="TURN")
                frame = await self._wait_motion_terminal(pair, "TURN", timeout)
                self._motion_lease = False
                if frame.kind != "DONE":
                    raise RobotLinkError(frame.raw)
                return TurnResult(
                    True,
                    *pair,
                    float(_field_after(frame, "H", "0")),
                    float(_field_after(frame, "TGT", "0")),
                    float(_field_after(frame, "ERR", "0")),
                    frame.fields,
                )
            except (RobotLinkError, RobotLinkTimeout):
                self._motion_lease = False
                if not self._ps2_override and not self._stop_in_progress:
                    with contextlib.suppress(RobotLinkError, RobotLinkTimeout):
                        await self.stop()
                raise
            finally:
                self._active_pair = None
                self._terminal_operation_id = 0
                self._active_motion_type = ""

    async def _heartbeat_loop(self) -> None:
        last = 0.0
        while True:
            await asyncio.sleep(0.02)
            now = time.monotonic()
            if self._motion_lease and now - last >= self.config.heartbeat_s:
                with contextlib.suppress(RobotLinkError, OSError):
                    await self._send("HB")
                    last = now
