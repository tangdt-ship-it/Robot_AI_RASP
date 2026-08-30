from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlsaStatus:
    arecord_present: bool
    aplay_present: bool
    capture_devices: str
    playback_devices: str


def alsa_status() -> AlsaStatus:
    arecord = shutil.which("arecord")
    aplay = shutil.which("aplay")
    capture = subprocess.run([arecord, "-l"], capture_output=True, text=True).stdout if arecord else ""
    playback = subprocess.run([aplay, "-l"], capture_output=True, text=True).stdout if aplay else ""
    return AlsaStatus(bool(arecord), bool(aplay), capture, playback)


def full_duplex_smoke_test(input_device: str, output_device: str, seconds: int = 2) -> tuple[bool, str]:
    """Capture 48 kHz PCM then play it. Simultaneous duplex is validated by HIL script separately."""
    arecord = shutil.which("arecord")
    aplay = shutil.which("aplay")
    if not arecord or not aplay:
        return False, "alsa-utils not installed"
    path = "/tmp/robot-ai-audio-smoke.wav"
    capture = subprocess.run(
        [arecord, "-D", input_device, "-c", "1", "-r", "48000", "-f", "S32_LE", "-d", str(seconds), path],
        capture_output=True,
        text=True,
    )
    if capture.returncode != 0:
        return False, capture.stderr
    playback = subprocess.run([aplay, "-D", output_device, path], capture_output=True, text=True)
    return playback.returncode == 0, playback.stderr
