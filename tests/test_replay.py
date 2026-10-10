from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from companion.cli import main
from companion.replay import replay
from companion.settings import Settings


ROOT = Path(__file__).resolve().parents[1]


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "events.jsonl"
        self.settings = Settings.load(ROOT / "config/example.toml")
        def box(text, x, y):
            return {"text": text, "x": x, "y": y, "width": 10, "height": 10, "confidence": .99}
        self.frame = {"frame_id": "saved", "captured_at": 1234, "width": 1024, "height": 720,
                      "boxes": [box("30", 495, 555), box("5级", 75, 555), box("2-3", 325, 5),
                                box("备战环节", 10, 10), box("奥恩", 225, 685), box("余震", 810, 685)]}

    def write(self, frames):
        self.path.write_text("\n".join(json.dumps({"event": "ocr", "data": row}, ensure_ascii=False)
                                      for row in frames), encoding="utf-8")

    def test_select_recorded_frame_and_keep_original_capture_time(self):
        self.write([self.frame, {**self.frame, "frame_id": "later"}])
        result = replay(self.settings, self.path, frame_id="saved")
        self.assertEqual(result.frame_id, "saved")
        self.assertEqual(result.captured_at, 1234)
        self.assertEqual(result.store[0].name, "奥恩")
        self.assertEqual(result.store[4].kind, "charm")
        self.assertEqual(result.errors, ())

    def test_wrong_or_missing_dimensions_do_not_become_valid_observation(self):
        for frame, expected in (({**self.frame, "width": 1920}, "resolution_mismatch"),
                                ({key: value for key, value in self.frame.items()
                                  if key not in ("width", "height")}, "unverified_resolution")):
            self.write([frame])
            self.assertEqual(replay(self.settings, self.path).errors, (expected,))

    def test_missing_timestamp_is_not_replaced_with_current_time(self):
        frame = dict(self.frame)
        del frame["captured_at"]
        self.write([frame])
        result = replay(self.settings, self.path)
        self.assertEqual(result.captured_at, 0)
        self.assertIn("unverified_capture_time", result.errors)

    def test_replay_cli_never_opens_device(self):
        self.write([self.frame])
        with patch("companion.device.Device.open", side_effect=AssertionError("Device opened")), \
                patch("companion.cli.emit") as emit:
            result = main(["--config", str(ROOT / "config/example.toml"), "replay", "--ocr", str(self.path)])
        self.assertEqual(result, 0)
        self.assertFalse(emit.call_args.args[0]["input_sent"])


if __name__ == "__main__":
    unittest.main()
