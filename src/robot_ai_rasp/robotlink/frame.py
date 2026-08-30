from __future__ import annotations

from dataclasses import dataclass


def crc16_ccitt(data: bytes) -> int:
    """RobotLink V3 CRC16-CCITT: init=0xFFFF, polynomial=0x1021, MSB first."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode_command(sequence: int, body: str) -> bytes:
    if not body or "\r" in body or "\n" in body:
        raise ValueError("invalid RobotLink command body")
    sequence &= 0xFFFF
    protected = (
        f"RAI,3,{sequence},{body}"
        if "," in body
        else f"RAI,3,{sequence},{body},"
    )
    crc = crc16_ccitt(protected.encode("ascii"))
    return f"${protected}*{crc:04X}\r\n".encode("ascii")


@dataclass(frozen=True, slots=True)
class InboundFrame:
    raw: str
    fields: tuple[str, ...]
    kind: str
    session_id: int = 0
    operation_id: int = 0

    def has(self, value: str) -> bool:
        target = value.upper()
        return any(field.upper() == target for field in self.fields)


def _correlation(fields: tuple[str, ...]) -> tuple[int, int]:
    sid = op = 0
    for index, field in enumerate(fields[:-1]):
        upper = field.upper()
        try:
            if upper == "SID":
                sid = int(fields[index + 1], 10)
            elif upper == "OP":
                op = int(fields[index + 1], 10)
        except (TypeError, ValueError):
            return 0, 0
    if sid <= 0 or op <= 0:
        return 0, 0
    return sid & 0xFFFFFFFF, op & 0xFFFFFFFF


def parse_inbound(line: str | bytes) -> InboundFrame | None:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    raw = line.strip()
    if not raw:
        return None
    payload = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw
    fields = tuple(part.strip() for part in payload.split(",") if part.strip() != "")
    if not fields:
        return None
    sid, op = _correlation(fields)
    return InboundFrame(raw=raw, fields=fields, kind=fields[0].upper(), session_id=sid, operation_id=op)


def key_values(frame: InboundFrame, start: int = 1) -> dict[str, str]:
    """Best-effort parser for VALUE/STATE frames encoded as KEY,VALUE pairs."""
    result: dict[str, str] = {}
    fields = frame.fields
    index = start
    while index + 1 < len(fields):
        key = fields[index].upper()
        if key in {"SID", "OP"}:
            index += 2
            continue
        result[key] = fields[index + 1]
        index += 2
    return result
