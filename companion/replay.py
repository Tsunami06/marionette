"""Reparse recorded OCR without a device, model download, or any input commands."""
from dataclasses import replace
import json
from pathlib import Path

from companion.catalog import Catalog
from companion.layout import png_dimensions, validate_layout
from companion.perception import Snapshot, TextBox, parse_frame


def replay(settings, path, frame_id=None, image=None):
    source = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(source)
        records = payload if isinstance(payload, list) else [payload]
    except json.JSONDecodeError:
        records = [json.loads(line) for line in source.splitlines() if line.strip()]
    frames = [row["data"] if row.get("event") == "ocr" else row
              for row in records if row.get("event") == "ocr" or "boxes" in row]
    if frame_id:
        frames = [row for row in frames if row.get("frame_id") == frame_id]
    if not frames:
        raise ValueError("No matching OCR frame found")
    frame = frames[-1]
    width, height = png_dimensions(image) if image else (frame.get("width"), frame.get("height"))
    timestamp = frame.get("captured_at", 0)
    identifier = frame.get("frame_id", "recorded-frame")
    if (width, height) != (settings.width, settings.height):
        reason = "unverified_resolution" if width is None or height is None else "resolution_mismatch"
        return Snapshot(identifier, timestamp, "unknown", None, None, None, (None,) * 5, (reason,))
    layout = json.loads(settings.layout.read_text(encoding="utf-8"))
    validate_layout(layout, settings.width, settings.height)
    boxes = [TextBox(**row) for row in frame["boxes"]]
    result = parse_frame(boxes, layout, Catalog.load(settings.heroes), identifier, timestamp)
    if not timestamp:
        result = replace(result, errors=result.errors + ("unverified_capture_time",))
    return result
