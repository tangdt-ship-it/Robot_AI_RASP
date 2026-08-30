from __future__ import annotations

import argparse
import asyncio
import logging

from .daemon.server import RobotDaemon
from .hardware.diagnostics import run_diagnostics


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="robot-ai")
    parser.add_argument("--config", default="/etc/robot-ai/robot.yaml")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command", required=True)
    daemon = sub.add_parser("daemon")
    daemon.add_argument("--socket", default="/run/robot-ai/robotd.sock")
    sub.add_parser("diagnostics")
    return parser


async def _daemon(config: str, socket: str) -> None:
    service = RobotDaemon(config, socket)
    await service.start()
    try:
        await service.serve_forever()
    finally:
        await service.close()


def cli() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.command == "daemon":
        asyncio.run(_daemon(args.config, args.socket))
    elif args.command == "diagnostics":
        raise SystemExit(run_diagnostics(args.config))


if __name__ == "__main__":
    cli()
