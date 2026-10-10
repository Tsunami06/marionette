import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import sys
import uuid

from companion.session import Audit, Session
from companion.settings import Settings


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def doctor(settings):
    versions = {}
    for package in ("adb-shell", "numpy", "opencv-python", "paddleocr", "paddlepaddle", "loguru", "psutil"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "missing"
    missing = [name for name, version in versions.items() if version == "missing"]
    problems = [f"Missing dependency: {name}" for name in missing]
    for package, major_limit in (("numpy", 2), ("paddleocr", 3), ("paddlepaddle", 3)):
        version = versions[package]
        if version != "missing" and int(version.split(".")[0]) >= major_limit:
            problems.append(f"Incompatible major version: {package} {version}; install the device extra in a clean venv")
    for path in (settings.layout, settings.heroes):
        if not path.is_file():
            problems.append(f"Missing file: {path}")
    emit({"python": sys.version.split()[0], "dependencies": versions,
          "adb": {"host": settings.host, "port": settings.port},
          "current_data_verified": settings.current_data_verified,
          "problems": problems,
          "note": "This command does not connect to a device or validate game compatibility."})
    return 1 if problems else 0


async def live(args, settings):
    from companion.device import Device
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    audit = Audit(settings.logs / name)
    audit.write("session_started", {"command": args.command,
        "execute": getattr(args, "execute", False), "settings": {
            **asdict(settings), "layout": str(settings.layout),
            "heroes": str(settings.heroes), "logs": str(settings.logs)}})
    device = await Device.open(settings, audit)
    try:
        session = Session(device, settings, audit)
        if args.command == "capture":
            frame, frame_id, _ = await device.capture()
            emit({"screenshot": str(audit.directory / f"{frame_id}.png"),
                  "width": frame.shape[1], "height": frame.shape[0]})
        elif args.command == "observe":
            emit((await session.observe()).json())
        elif args.command == "buy":
            outcome = await session.buy(args.slot - 1, execute=args.execute)
            emit(asdict(outcome))
            if outcome.status in ("blocked", "paused"):
                return 2
        else:
            result = await session.run(execute=args.execute, limit=args.iterations)
            emit({"state": result, "attempted_actions": session.actions,
                  "logs": str(audit.directory)})
            if result == "paused":
                return 2
        return 0
    finally:
        await device.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sunflower-derived game observation and purchase MVP")
    parser.add_argument("--config", default="config/example.toml")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "capture", "observe"):
        commands.add_parser(command)
    buy = commands.add_parser("buy", help="Preview a purchase; --execute sends input")
    buy.add_argument("--slot", type=int, choices=range(1, 6), required=True)
    buy.add_argument("--execute", action="store_true")
    run = commands.add_parser("run", help="Observe and preview target purchases by default")
    run.add_argument("--execute", action="store_true")
    run.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args(argv)
    if args.command == "run" and args.iterations < 1:
        parser.error("--iterations must be positive")
    try:
        settings = Settings.load(args.config)
        return doctor(settings) if args.command == "doctor" else asyncio.run(live(args, settings))
    except KeyboardInterrupt:
        print("Stopped by user.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
