from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image


class ST7789:
    """Minimal ST7789 240x240 SPI0 driver matching the former ESP32 panel."""

    def __init__(
        self,
        *,
        bus: int = 0,
        device: int = 0,
        dc_gpio: int = 25,
        reset_gpio: int = 24,
        backlight_gpio: int = 23,
        speed_hz: int = 40_000_000,
    ):
        import spidev
        from gpiozero import OutputDevice
        from gpiozero.pins.lgpio import LGPIOFactory

        factory = LGPIOFactory(chip=0)
        self.dc = OutputDevice(dc_gpio, pin_factory=factory, initial_value=False)
        self.reset = OutputDevice(reset_gpio, pin_factory=factory, initial_value=True)
        self.backlight = OutputDevice(backlight_gpio, pin_factory=factory, initial_value=False)
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = 0
        self.width = 240
        self.height = 240

    def _cmd(self, command: int, data: bytes = b"") -> None:
        self.dc.off()
        self.spi.writebytes2([command & 0xFF])
        if data:
            self.dc.on()
            self.spi.writebytes2(list(data))

    def initialize(self) -> None:
        self.reset.off()
        time.sleep(0.05)
        self.reset.on()
        time.sleep(0.12)
        self._cmd(0x01)  # SWRESET
        time.sleep(0.12)
        self._cmd(0x11)  # SLPOUT
        time.sleep(0.12)
        self._cmd(0x3A, b"\x55")  # RGB565
        self._cmd(0x36, b"\x60")  # MX + MV: mirror_x=true, swap_xy=true
        self._cmd(0x21)  # inversion on, matching ESP32 config
        self._cmd(0x13)  # normal display mode
        self._cmd(0x29)  # display on
        self.backlight.on()

    def set_window(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self._cmd(0x2A, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._cmd(0x2B, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))
        self._cmd(0x2C)

    def display(self, image: "Image") -> None:
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height))
        rgb = image.convert("RGB")
        source = rgb.tobytes()
        output = bytearray(len(source) // 3 * 2)
        j = 0
        for i in range(0, len(source), 3):
            r, g, b = source[i], source[i + 1], source[i + 2]
            value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            output[j] = value >> 8
            output[j + 1] = value & 0xFF
            j += 2
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.dc.on()
        chunk = 4096
        for offset in range(0, len(output), chunk):
            self.spi.writebytes2(list(output[offset : offset + chunk]))

    def close(self) -> None:
        self.backlight.off()
        self.spi.close()
        self.dc.close()
        self.reset.close()
        self.backlight.close()
