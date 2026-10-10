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
from companion.catalog import Catalog
from companion.layout import create_calibration, validate_layout
from companion.replay import replay


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def doctor(settings, capture_only=False):
    versions = {}
    packages = ["adb-shell", "numpy", "opencv-python", "loguru", "psutil"]
    if not capture_only:
        packages += ["paddleocr", "paddlepaddle"]
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "missing"
    missing = [name for name, version in versions.items() if version == "missing"]
    problems = [f"Missing dependency: {name}" for name in missing]
    for package, major_limit in (("numpy", 2), ("paddleocr", 3), ("paddlepaddle", 3)):
        version = versions.get(package, "missing")
        if version != "missing" and int(version.split(".")[0]) >= major_limit:
            problems.append(f"Incompatible major version: {package} {version}; install the device extra in a clean venv")
    for path in (settings.layout, settings.heroes):
        if not path.is_file():
            problems.append(f"Missing file: {path}")
    catalog = None
    try:
        validate_layout(json.loads(settings.layout.read_text(encoding="utf-8")),
                        settings.width, settings.height)
        catalog = Catalog.load(settings.heroes).summary()
    except (ValueError, KeyError, OSError, TypeError) as error:
        problems.append(f"Invalid layout/catalog: {error}")
    emit({"python": sys.version.split()[0], "dependencies": versions,
          "adb": {"host": settings.host, "port": settings.port},
          "current_data_verified": settings.current_data_verified,
          "catalog": catalog,
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
    device = await Device.open(settings, audit, initialize_ocr=args.command not in ("capture", "probe"))
    try:
        session = Session(device, settings, audit)
        if args.command in ("capture", "probe"):
            frame, frame_id, _ = await device.capture()
            report = {"screenshot": str(audit.directory / f"{frame_id}.png"),
                      "width": frame.shape[1], "height": frame.shape[0],
                      "resolution_matches_config": frame.shape[:2] == (settings.height, settings.width),
                      "ocr_initialized": False}
            if args.command == "probe":
                report.update({"adb_connected": device.adb.is_connected(),
                    "reported_screen_size": await device.adb.get_screen_size(),
                    "reported_density": await device.adb.get_screen_density()})
                audit.write("device_probe", report)
            emit(report)
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
    diagnostic = commands.add_parser("doctor")
    diagnostic.add_argument("--capture-only", action="store_true", help="Check transport dependencies without OCR")
    for command in ("capture", "probe", "observe"):
        commands.add_parser(command)
    catalog = commands.add_parser("catalog", help="Inspect versioned data without a device")
    catalog.add_argument("--name", help="Inspect all IDs for a champion or charm name")
    recorded = commands.add_parser("replay", help="Parse saved OCR without connecting to a device")
    recorded.add_argument("--ocr", required=True, type=Path, help="OCR JSON or events.jsonl")
    recorded.add_argument("--frame-id")
    recorded.add_argument("--image", type=Path, help="PNG for old logs without dimensions")
    calibration = commands.add_parser("calibrate", help="Create a local screenshot region editor")
    calibration.add_argument("--image", required=True, type=Path)
    calibration.add_argument("--output", required=True, type=Path)
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
        if args.command == "catalog":
            reference = Catalog.load(settings.heroes)
            if args.name:
                emit({"champions": [asdict(row) for row in reference.by_name.get(args.name, [])],
                      "charms": [row for row in reference.charms if row["name"] == args.name],
                      "metadata": reference.metadata})
            else:
                emit(reference.summary())
            return 0
        if args.command == "replay":
            emit({"mode": "offline_replay", "input_sent": False,
                  "snapshot": replay(settings, args.ocr, args.frame_id, args.image).json()})
            return 0
        if args.command == "calibrate":
            emit(create_calibration(args.image,
                 json.loads(settings.layout.read_text(encoding="utf-8")), args.output))
            return 0
        return doctor(settings, args.capture_only) if args.command == "doctor" else asyncio.run(live(args, settings))
    except KeyboardInterrupt:
        print("Stopped by user.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
