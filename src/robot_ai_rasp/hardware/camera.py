from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PiCamera:
    def __init__(self, width: int = 640, height: int = 480):
        self.width = width
        self.height = height

    def capture_jpeg(self, output: str | Path, timeout_ms: int = 1500) -> Path:
        command = shutil.which("rpicam-still") or shutil.which("libcamera-still")
        if not command:
            raise RuntimeError("rpicam-still/libcamera-still not installed")
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                command,
                "--nopreview",
                "--timeout",
                str(timeout_ms),
                "--width",
                str(self.width),
                "--height",
                str(self.height),
                "--output",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or "camera capture failed")
        return output
