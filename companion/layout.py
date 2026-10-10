"""Validate pixel regions and generate a local PNG-based calibration page."""
import base64
import json
from pathlib import Path
import struct


def validate_layout(layout, width, height):
    if not isinstance(layout, dict):
        raise ValueError("Layout must be an object")
    if len(layout.get("store", [])) != 5:
        raise ValueError("Layout must contain five shop name regions")
    if "store_details" in layout and len(layout["store_details"]) != 5:
        raise ValueError("store_details must contain five optional regions")
    for key in ("coin", "level", "period", "store", "store_details"):
        if key == "store_details" and key not in layout:
            continue
        if key not in layout:
            raise ValueError(f"Missing layout region: {key}")
        areas = layout[key] if key in ("store", "store_details") else [layout[key]]
        for area in areas:
            if area is None and key == "store_details":
                continue
            if (not isinstance(area, (list, tuple)) or len(area) != 4
                    or any(type(value) is not int for value in area)
                    or min(area[:2]) < 0 or min(area[2:]) <= 0):
                raise ValueError(f"Invalid layout region: {key}")
            if area[0] + area[2] > width or area[1] + area[3] > height:
                raise ValueError(f"Layout region outside screenshot: {key}")


def png_dimensions(path):
    with Path(path).open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Calibration/replay screenshot must be a PNG file")
    width, height = struct.unpack(">II", header[16:24])
    if min(width, height) <= 0:
        raise ValueError("Invalid PNG dimensions")
    return width, height


def create_calibration(image_path, layout, output):
    width, height = png_dimensions(image_path)
    payload = {"width": width, "height": height, "layout": layout}
    serialized = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    source = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    template = (Path(__file__).parent / "templates/calibration.html").read_text(encoding="utf-8")
    page = template.replace("__CALIBRATION_DATA__", serialized).replace("__SCREENSHOT_DATA__", source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return {"page": str(output.resolve()), "width": width, "height": height,
            "note": "Open locally, draw regions, export layout.json; update config dimensions separately."}
