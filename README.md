# Robot_AI_RASP

Raspberry Pi Zero 2 W replacement stack for the Robot_AI ESP32-S3 controller.

> Status: active port / hardware validation required.

This repository ports the high-level Robot_AI controller from ESP32-S3/ESP-IDF to Raspberry Pi OS while preserving STM32 as the real-time motor and safety authority.

## Target architecture

```text
Xiaozhi / Wake word ROBOT / Audio / TFT / Camera / MCP / Mission / Map
                         Raspberry Pi Zero 2 W
                                   |
                         RobotLink UART 115200
                                   |
                                   v
                              STM32F103
                 Motor / Encoder / Sensors / Safety
```

The Raspberry Pi must never bypass STM32 safety. Autonomous movement remains fail-closed.

## Port reference

- ESP32 reference repository: `tangdt-ship-it/Robot_AI`
- HIL baseline: `baseline/v5-alpha9-hil-passed-pre-wireless` @ `7720eac7c59dc57843b5cdd162298526a42445b4`
- Xiaozhi-primary RAM/audio work reference: `fix/v5-xiaozhi-primary-service` @ `040678655c8be8a3a22d9284e26ca464b9e20bbe`
- Home-return candidate reference: `feature/v5.2-home-return-candidate` @ `ff58c2256bcacd3183fc9c8497b15ab4d4751f55`

## Wake word

Default wake word is **Robot**.

## Safety status

No motion feature is considered commissioned on Raspberry Pi until its corresponding HIL gate passes on the physical robot.
