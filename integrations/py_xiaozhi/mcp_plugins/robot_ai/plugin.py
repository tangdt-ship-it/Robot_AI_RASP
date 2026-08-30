from __future__ import annotations

import json
import os

from robot_ai_rasp.rpc import RobotRpcClient

SOCKET = os.environ.get("ROBOT_AI_SOCKET", "/run/robot-ai/robotd.sock")
rpc = RobotRpcClient(SOCKET)


def _text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def register(host):
    @host.tool("self.robot.get_state", "Đọc trạng thái robot, chế độ, tốc độ, motor và chủ sở hữu chuyển động.")
    async def get_state(_):
        return _text(await rpc.call("robot.get_state"))

    @host.tool("self.robot.get_encoder_status", "Đọc tình trạng encoder và vận tốc hai bánh.")
    async def get_encoder(_):
        return _text(await rpc.call("robot.get_encoder_status"))

    @host.tool("self.robot.get_odometry", "Đọc odometry DIST/X/Y/H/ticks/reset generation.")
    async def get_odometry(_):
        return _text(await rpc.call("robot.get_odometry"))

    @host.tool("self.robot.get_imu_status", "Đọc trạng thái IMU, gyro và gia tốc.")
    async def get_imu(_):
        return _text(await rpc.call("robot.get_imu_status"))

    @host.tool("self.robot.get_fusion_status", "Đọc heading fusion, yaw rate và confidence.")
    async def get_fusion(_):
        return _text(await rpc.call("robot.get_fusion_status"))

    @host.tool("self.robot.get_obstacle", "Đọc cảm biến vật cản trước trái/phải và vùng an toàn.")
    async def get_obstacle(_):
        return _text(await rpc.call("robot.get_obstacle"))

    @host.tool("self.robot.get_mission_state", "Đọc trạng thái nhiệm vụ và kết quả preflight gần nhất.")
    async def get_mission(_):
        return _text(await rpc.call("robot.get_mission_state"))

    @host.tool("self.robot.preflight", "Kiểm tra fail-closed trước khi robot chuyển động.")
    async def preflight(_):
        return _text(await rpc.call("robot.preflight"))

    @host.tool(
        "self.robot.move_distance",
        "Cho robot đi tiến/lùi một quãng hữu hạn; STM32 vẫn là safety authority.",
        [
            {"name": "direction", "type": "string", "default": "forward"},
            {"name": "distance_mm", "type": "integer", "min": 1, "max": 5000},
            {"name": "speed", "type": "integer", "default": 20, "min": 10, "max": 20}
        ],
    )
    async def move_distance(args):
        return _text(await rpc.call("robot.move_distance", **args))

    @host.tool(
        "self.robot.turn_relative",
        "Quay robot trái/phải một góc tương đối với strict SID/OP.",
        [
            {"name": "direction", "type": "string"},
            {"name": "angle_deg", "type": "integer", "min": 1, "max": 180},
            {"name": "speed", "type": "integer", "default": 20, "min": 10, "max": 20}
        ],
    )
    async def turn_relative(args):
        return _text(await rpc.call("robot.turn_relative", **args))

    @host.tool(
        "self.robot.turn_to_heading",
        "Quay robot tới heading tuyệt đối.",
        [
            {"name": "heading_deg", "type": "integer", "min": -180, "max": 180},
            {"name": "speed", "type": "integer", "default": 20, "min": 10, "max": 20}
        ],
    )
    async def turn_heading(args):
        return _text(await rpc.call("robot.turn_to_heading", **args))

    @host.tool("self.robot.stop", "DỪNG robot. Lệnh ưu tiên cao nhất; chờ STM32 xác nhận DONE,STOP.")
    async def stop(_):
        return _text(await rpc.call("robot.stop"))

    @host.tool("self.robot.cancel_mission", "Hủy nhiệm vụ hiện tại và trả robot về trạng thái an toàn.")
    async def cancel(_):
        return _text(await rpc.call("robot.cancel_mission"))

    @host.tool("self.robot.get_speed", "Đọc tốc độ cấu hình trên STM32.")
    async def get_speed(_):
        return _text(await rpc.call("robot.get_speed"))

    @host.tool("self.robot.set_speed", "Đặt tốc độ cấu hình.", [{"name": "speed", "type": "integer", "min": 10, "max": 255}])
    async def set_speed(args):
        return _text(await rpc.call("robot.set_speed", **args))

    @host.tool("self.robot.get_brake", "Đọc trạng thái brake.")
    async def get_brake(_):
        return _text(await rpc.call("robot.get_brake"))

    @host.tool("self.robot.set_brake", "Bật/tắt brake.", [{"name": "enabled", "type": "boolean"}])
    async def set_brake(args):
        return _text(await rpc.call("robot.set_brake", **args))

    @host.tool("self.robot.get_ramp", "Đọc trạng thái ramp.")
    async def get_ramp(_):
        return _text(await rpc.call("robot.get_ramp"))

    @host.tool("self.robot.set_ramp", "Bật/tắt ramp.", [{"name": "enabled", "type": "boolean"}])
    async def set_ramp(args):
        return _text(await rpc.call("robot.set_ramp", **args))

    @host.tool("self.robot.get_heading", "Đọc heading hợp nhất.")
    async def get_heading(_):
        return _text(await rpc.call("robot.get_heading"))

    @host.tool("self.robot.get_compass_status", "Đọc trạng thái compass.")
    async def get_compass(_):
        return _text(await rpc.call("robot.get_compass_status"))

    @host.tool("self.robot.reset_compass", "Đặt lại zero của compass khi robot đứng yên.")
    async def reset_compass(_):
        return _text(await rpc.call("robot.reset_compass"))

    @host.tool("self.robot.get_ps2_status", "Đọc trạng thái tay điều khiển PS2 và override.")
    async def get_ps2(_):
        return _text(await rpc.call("robot.get_ps2_status"))

    @host.tool("self.robot.set_home", "Lưu vị trí hiện tại làm Home trong SQLite trên Raspberry Pi.")
    async def set_home(_):
        return _text(await rpc.call("robot.set_home"))

    @host.tool("self.robot.get_home", "Đọc vị trí Home đã lưu.")
    async def get_home(_):
        return _text(await rpc.call("robot.get_home"))
