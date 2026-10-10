"""Live adapter. Heavy dependencies are loaded only when connecting a device."""
import asyncio
import json
from pathlib import Path
import time
import uuid

from companion.perception import Snapshot, TextBox, parse_frame
from companion.catalog import Catalog
from companion.layout import validate_layout


class Device:
    def __init__(self, adb, settings, audit):
        self.adb = adb
        self.settings = settings
        self.audit = audit
        self.layout = json.loads(settings.layout.read_text(encoding="utf-8"))
        validate_layout(self.layout, settings.width, settings.height)
        self.catalog = Catalog.load(settings.heroes)
        self.audit.write("data_loaded", {"path": str(settings.heroes),
            **self.catalog.summary(),
            "verified_by_user": settings.current_data_verified})

    @classmethod
    async def open(cls, settings, audit, initialize_ocr=True):
        from sunflower.adb import AdbOCR
        adb = AdbOCR()
        try:
            await adb.load(settings.port, host=settings.host, scan_if_fail=False,
                           initialize_ocr=initialize_ocr)
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
        started = time.perf_counter()
        frame = await self.adb.get_screen()
        if frame is None:
            raise RuntimeError("ADB returned an invalid screenshot")
        frame_id = uuid.uuid4().hex
        destination = self.audit.directory / f"{frame_id}.png"
        if not cv2.imwrite(str(destination), frame):
            raise OSError("Could not save screenshot")
        self.audit.write("capture", {"frame_id": frame_id, "captured_at": captured_at,
            "width": frame.shape[1], "height": frame.shape[0],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
        return frame, frame_id, captured_at

    async def observe(self):
        frame, frame_id, captured_at = await self.capture()
        if frame.shape[:2] != (self.settings.height, self.settings.width):
            return Snapshot(frame_id, captured_at, "unknown", None, None, None,
                            (None,) * 5, ("resolution_mismatch",))
        # One screenshot and one full-frame OCR call for all primary fields.
        # Offload CPU work so the event loop remains responsive.
        if self.adb.ocr_engine is None:
            raise RuntimeError("OCR was not initialized; use capture/probe or open with OCR enabled")
        started = time.perf_counter()
        raw = await asyncio.to_thread(self.adb.ocr_engine.ocr, frame, cls=False)
        boxes = []
        for item in (raw[0] or []) if raw else []:
            points, (text, confidence) = item
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            boxes.append(TextBox(text, min(xs), min(ys), max(xs) - min(xs),
                                 max(ys) - min(ys), float(confidence)))
        self.audit.write("ocr", {"frame_id": frame_id,
                                 "captured_at": captured_at,
                                 "width": frame.shape[1], "height": frame.shape[0],
                                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "boxes": [vars(box) for box in boxes]})
        return parse_frame(boxes, self.layout, self.catalog, frame_id, captured_at)

    async def buy(self, slot):
        x, y, width, height = self.layout["store"][slot]
        await self.adb.click(int(x + width / 2), int(y + height / 2))
