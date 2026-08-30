from robot_ai_rasp.robotlink.frame import crc16_ccitt, encode_command, parse_inbound


def test_crc_vectors_match_esp32_contract():
    assert crc16_ccitt(b"RAI,3,0,PING,") == 0xFBC5
    assert crc16_ccitt(b"RAI,3,42,STOP,") == 0xEF16
    assert crc16_ccitt(b"RAI,3,7,MODE,AI") == 0xEB3F


def test_encode_empty_payload_command():
    assert encode_command(0, "PING") == b"$RAI,3,0,PING,*FBC5\r\n"


def test_parse_strict_correlation():
    frame = parse_inbound("<DONE,MOVE,TARGET,500,TRAVEL,499,SID,7,OP,31>")
    assert frame is not None
    assert frame.kind == "DONE"
    assert (frame.session_id, frame.operation_id) == (7, 31)


def test_missing_correlation_is_zero():
    frame = parse_inbound("<DONE,MOVE,TARGET,500,TRAVEL,499>")
    assert frame is not None
    assert (frame.session_id, frame.operation_id) == (0, 0)
