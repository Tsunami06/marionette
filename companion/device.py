"""Live adapter. Heavy dependencies are loaded only when connecting a device."""
import asyncio
import json
from pathlib import Path
import time
import uuid

from companion.perception import Snapshot, TextBox, parse_frame


class Device:
    def __init__(self, adb, settings, audit):
        self.adb = adb
        self.settings = settings
        self.audit = audit
        self.layout = json.loads(settings.layout.read_text(encoding="utf-8"))
        if len(self.layout.get("store", [])) != 5:
            raise ValueError("Layout must contain five shop regions")
        for key in ("coin", "level", "period", "store"):
            areas = self.layout[key] if key == "store" else [self.layout[key]]
            for area in areas:
                if len(area) != 4 or min(area[:2]) < 0 or min(area[2:]) <= 0:
                    raise ValueError(f"Invalid layout region: {key}")
                if area[0] + area[2] > settings.width or area[1] + area[3] > settings.height:
                    raise ValueError(f"Layout region outside screenshot: {key}")
        data = json.loads(settings.heroes.read_text(encoding="utf-8"))
        if "data" not in data or not isinstance(data["data"], dict):
            raise ValueError("Hero data must contain a data mapping")
        self.heroes = {}
        for hero in data["data"].values():
            name = hero.get("name")
            if not name:
                continue
            try:
                price = int(hero.get("buyPrice", hero.get("price")))
                price = price if 1 <= price <= 10 else None
            except (TypeError, ValueError):
                price = None
            self.heroes[name] = price
        if not self.heroes:
            raise ValueError("Hero data contains no names")
        self.audit.write("data_loaded", {"path": str(settings.heroes),
            "time": data.get("time"), "season": data.get("season"),
            "verified_by_user": settings.current_data_verified})

    @classmethod
    async def open(cls, settings, audit):
        from sunflower.adb import AdbOCR
        adb = AdbOCR()
        try:
            await adb.load(settings.port, host=settings.host, scan_if_fail=False)
            if not adb.is_connected():
                raise ConnectionError("Cannot connect to configured ADB endpoint")
            return cls(adb, settings, audit)
        except BaseException:
            if adb._device:
                await adb._device.close()
            raise

    async def close(self):
        if self.adb._device:
            await self.adb._device.close()

    async def capture(self):
        import cv2
        captured_at = time.time()
        frame = await self.adb.get_screen()
        if frame is None:
            raise RuntimeError("ADB returned an invalid screenshot")
        frame_id = uuid.uuid4().hex
        destination = self.audit.directory / f"{frame_id}.png"
        if not cv2.imwrite(str(destination), frame):
            raise OSError("Could not save screenshot")
        return frame, frame_id, captured_at

    async def observe(self):
        frame, frame_id, captured_at = await self.capture()
        if frame.shape[:2] != (self.settings.height, self.settings.width):
            return Snapshot(frame_id, captured_at, "unknown", None, None, None,
                            (None,) * 5, ("resolution_mismatch",))
        # One screenshot and one full-frame OCR call for all primary fields.
        # Offload CPU work so the event loop remains responsive.
        raw = await asyncio.to_thread(self.adb.ocr_engine.ocr, frame, cls=False)
        boxes = []
        for item in (raw[0] or []) if raw else []:
            points, (text, confidence) = item
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            boxes.append(TextBox(text, min(xs), min(ys), max(xs) - min(xs),
                                 max(ys) - min(ys), float(confidence)))
        self.audit.write("ocr", {"frame_id": frame_id,
                                 "boxes": [vars(box) for box in boxes]})
        return parse_frame(boxes, self.layout, self.heroes, frame_id, captured_at)

    async def buy(self, slot):
        x, y, width, height = self.layout["store"][slot]
        await self.adb.click(int(x + width / 2), int(y + height / 2))
