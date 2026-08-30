from robot_ai_rasp.robotlink.frame import parse_inbound
from robot_ai_rasp.robotlink.parsers import parse_fusion, parse_obstacle, parse_odometry, parse_state


def f(text: str):
    frame = parse_inbound(text)
    assert frame is not None
    return frame


def test_parse_state_current_profile():
    state = parse_state(f("<STATE,MODE,AI,SPEED,20,BRAKE,ON,RAMP,ON,H,12.5,L,0,R,0,MOVE,0,PS2,OK,COMPASS,OK,AI_LINK,OK,OWNER,AI>"))
    assert state.valid and state.ai_mode and state.motion_owner == "AI"
    assert state.heading_deg == 12.5 and state.brake_enabled


def test_parse_odometry_with_reset_generation():
    odom = parse_odometry(f("<VALUE,ODOMETRY,DIST,-218.7,X,-218.4,Y,0.7,H,0.000,LT,0,RT,0,RESET_GEN,3>"))
    assert odom.distance_mm == -218.7
    assert odom.reset_generation == 3


def test_parse_fusion():
    fusion = parse_fusion(f("<VALUE,FUSION,READY,1,HEALTH,FUSED,H,90.0,RATE,0.1,CONF,97.5,SRC,I+E+C>"))
    assert fusion.ready and fusion.health == "FUSED" and fusion.confidence_pct == 97.5


def test_parse_obstacle_health():
    obs = parse_obstacle(f("<VALUE,OBSTACLE,FRESH,1,ECHO,1,HEALTH,HEALTHY,DIST,42,RATE,-3,ZONE,CLEAR,LIMIT,0,LEFT,43,RIGHT,41,LZ,CLEAR,RZ,CLEAR,LH,HEALTHY,RH,HEALTHY,LAGE,20,RAGE,21,SUG,NONE,RESET_GEN,4>"))
    assert obs.valid and obs.fresh and obs.echo_valid
    assert obs.distance_cm == 42 and obs.encoder_reset_generation == 4
