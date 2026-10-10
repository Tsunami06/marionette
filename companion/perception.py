"""Pure parsing of one OCR frame. No device or machine-learning imports."""
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import re


def match_name(text: str, names, threshold: float = 0.86, margin: float = 0.15):
    text = re.sub(r"\s+", "", text)
    names = sorted(set(names))
    if not text:
        return None
    if text in names:
        return text
    scores = sorted(((SequenceMatcher(None, text, name).ratio(), name)
                     for name in names), reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    return scores[0][1]


@dataclass(frozen=True)
class TextBox:
    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float


@dataclass(frozen=True)
class Card:
    name: str
    price: int | None


@dataclass(frozen=True)
class Snapshot:
    frame_id: str
    captured_at: float
    phase: str
    coin: int | None
    level: int | None
    period: tuple[int, int] | None
    store: tuple[Card | None, ...]
    errors: tuple[str, ...] = ()
    store_text: tuple[str, ...] = ()

    def json(self):
        return asdict(self)


def text_in(boxes, area, confidence=0.85):
    x, y, width, height = area
    selected = [box for box in boxes
                if box.confidence >= confidence
                and x <= box.x + box.width / 2 < x + width
                and y <= box.y + box.height / 2 < y + height]
    return "".join(box.text for box in sorted(selected, key=lambda b: (b.y, b.x)))


def integer(text, minimum, maximum, suffix=""):
    text = text.strip()
    if suffix and text.endswith(suffix):
        text = text[:-len(suffix)]
    if not re.fullmatch(r"[0-9]+", text):
        return None
    value = int(text)
    return value if minimum <= value <= maximum else None


def phase_of(boxes):
    words = {box.text.strip() for box in boxes if box.confidence >= 0.85}
    # Selection screens take precedence over buttons visible behind an overlay.
    if any("强化符文" in word or "选择强化" in word for word in words):
        return "selection"
    ready = "备战环节" in words
    combat = "战斗环节" in words
    if ready != combat:
        return "preparation" if ready else "combat"
    if "您获得了" in words or any(f"第{rank}名" in words for rank in "一二三四五六七八"):
        return "result"
    return "unknown"


def parse_frame(boxes, layout, heroes, frame_id, captured_at):
    coin = integer(text_in(boxes, layout["coin"]), 0, 999)
    level = integer(text_in(boxes, layout["level"]), 1, 20, "级")
    period_text = text_in(boxes, layout["period"])
    match = re.fullmatch(r"\s*([0-9]+)\s*[-－—]\s*([0-9]+)\s*", period_text)
    period = (int(match[1]), int(match[2])) if match else None
    cards = []
    store_text = []
    for area in layout["store"]:
        raw_text = text_in(boxes, area)
        store_text.append(raw_text)
        name = match_name(raw_text, heroes)
        cards.append(Card(name, heroes[name]) if name else None)
    errors = tuple(key for key, value in (("coin", coin), ("level", level), ("period", period))
                   if value is None)
    return Snapshot(frame_id, captured_at, phase_of(boxes), coin, level, period,
                    tuple(cards), errors, tuple(store_text))
