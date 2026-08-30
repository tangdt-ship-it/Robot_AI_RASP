from __future__ import annotations

import os
import shutil
from pathlib import Path

from ..config import load_config
from .audio import alsa_status


def run_diagnostics(config_path: str) -> int:
    config = load_config(config_path)
    checks: list[tuple[str, bool, str]] = []
    uart = Path(config.robotlink.device)
    checks.append(("UART", uart.exists(), str(uart)))
    checks.append(("SPI0", Path("/dev/spidev0.0").exists(), "/dev/spidev0.0"))
    checks.append(("GPIO", Path("/dev/gpiochip0").exists(), "/dev/gpiochip0"))
    audio = alsa_status()
    checks.append(("ALSA_CAPTURE", bool(audio.capture_devices.strip()), "arecord -l"))
    checks.append(("ALSA_PLAYBACK", bool(audio.playback_devices.strip()), "aplay -l"))
    checks.append(("CAMERA_TOOL", bool(shutil.which("rpicam-still") or shutil.which("libcamera-still")), "rpicam-still"))
    failed = False
    for name, passed, detail in checks:
        print(f"{name}={'PASS' if passed else 'FAIL'} {detail}")
        failed |= not passed
    print(f"WAKE_WORD={config.wakeword.phrase}")
    print(f"RESULT={'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0
