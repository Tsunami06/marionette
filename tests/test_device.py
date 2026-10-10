from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock

from companion.device import Device
from companion.session import Audit
from companion.settings import Settings


class Frame:
    shape = (720, 1024)


class Engine:
    def __init__(self):
        self.calls = 0

    def ocr(self, frame, cls=False):
        self.calls += 1
        def box(text, x, y):
            return [[[x, y], [x+10, y], [x+10, y+10], [x, y+10]], [text, .99]]
        return [[box("30", 495, 555), box("5级", 75, 555),
                 box("2-3", 325, 5), box("备战环节", 10, 10)]]


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(__file__).resolve().parents[1] / "config/example.toml"
        self.settings = Settings.load(path)
        self.audit = Audit(Path(self.temp.name))

    def device(self):
        class Adb:
            ocr_engine = Engine()
        return Device(Adb(), self.settings, self.audit)

    async def test_primary_fields_use_one_capture_and_one_ocr(self):
        device = self.device()
        device.capture = AsyncMock(return_value=(Frame(), "one-frame", time.time()))
        snapshot = await device.observe()
        self.assertEqual(device.capture.await_count, 1)
        self.assertEqual(device.adb.ocr_engine.calls, 1)
        self.assertEqual((snapshot.coin, snapshot.level, snapshot.period), (30, 5, (2, 3)))

    async def test_wrong_resolution_skips_ocr(self):
        device = self.device()
        class WrongFrame:
            shape = (1080, 1920)
        device.capture = AsyncMock(return_value=(WrongFrame(), "wrong", time.time()))
        snapshot = await device.observe()
        self.assertEqual(snapshot.errors, ("resolution_mismatch",))
        self.assertEqual(device.adb.ocr_engine.calls, 0)

    async def test_empty_ocr_is_unknown_without_exception(self):
        device = self.device()
        device.adb.ocr_engine.ocr = lambda *args, **kwargs: [None]
        device.capture = AsyncMock(return_value=(Frame(), "empty", time.time()))
        snapshot = await device.observe()
        self.assertEqual(snapshot.phase, "unknown")
        self.assertEqual(snapshot.errors, ("coin", "level", "period"))
