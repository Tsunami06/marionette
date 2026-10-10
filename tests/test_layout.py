import json
from pathlib import Path
import struct
import tempfile
import unittest

from companion.layout import create_calibration, png_dimensions, validate_layout


ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = json.loads((ROOT / "config/layout.json").read_text(encoding="utf-8"))

    def test_optional_trait_regions_and_bad_geometry(self):
        self.layout["store_details"] = [None] * 5
        validate_layout(self.layout, 1024, 720)
        for region in ([1000, 700, 50, 50], [1, 1, 0, 10], [True, 1, 5, 5]):
            self.layout["store_details"][0] = region
            with self.assertRaises(ValueError):
                validate_layout(self.layout, 1024, 720)

    def test_png_calibration_retains_actual_image_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "screen.png"
            # Header-only fixture validates header parsing/page embedding, not image decoding.
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1920, 1080))
            self.assertEqual(png_dimensions(path), (1920, 1080))
            output = Path(directory) / "calibration.html"
            result = create_calibration(path, self.layout, output)
            self.assertEqual((result["width"], result["height"]), (1920, 1080))
            self.assertNotIn("__CALIBRATION_DATA__", output.read_text(encoding="utf-8"))
            self.assertNotIn("__SCREENSHOT_DATA__", output.read_text(encoding="utf-8"))

    def test_non_png_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.png"
            path.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ValueError):
                png_dimensions(path)


if __name__ == "__main__":
    unittest.main()
