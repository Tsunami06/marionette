"""Versioned identities and shop classification, independent of device libraries."""
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Champion:
    id: str
    name: str
    cost: int | None
    trait_ids: tuple[str, ...] = ()
    traits: tuple[str, ...] = ()
    variant: str | None = None


class Catalog:
    def __init__(self, champions, charms=(), metadata=None):
        self.champions = tuple(champions)
        self.charms = tuple(charms)
        self.metadata = metadata or {}
        self.by_name = {}
        ids = set()
        for champion in self.champions:
            if champion.id in ids:
                raise ValueError(f"Duplicate champion ID: {champion.id}")
            ids.add(champion.id)
            self.by_name.setdefault(champion.name, []).append(champion)
        self.charms_by_name = {row["name"]: row for row in self.charms}
        if not self.by_name:
            raise ValueError("Catalog contains no champion names")

    @staticmethod
    def _cost(value, maximum=10):
        if type(value) is int:
            return value if 1 <= value <= maximum else None
        if isinstance(value, str) and re.fullmatch(r"[0-9]+", value):
            number = int(value)
            return number if 1 <= number <= maximum else None
        return None

    @classmethod
    def from_data(cls, data):
        if "champions" in data:
            champions = [Champion(str(row["id"]), row["name"], cls._cost(row.get("cost")),
                tuple(row.get("trait_ids", [])), tuple(row.get("traits", [])), row.get("variant"))
                for row in data["champions"]]
            return cls(champions, data.get("charms", []), data.get("metadata", {}))
        if "data" not in data or not isinstance(data["data"], dict):
            raise ValueError("Expected a versioned catalog or a legacy data mapping")
        champions = [Champion(str(key), row["name"],
                    cls._cost(row.get("buyPrice", row.get("price"))))
                    for key, row in data["data"].items() if row.get("name")]
        return cls(champions, metadata={key: data.get(key) for key in ("season", "time")})

    @classmethod
    def load(cls, path):
        return cls.from_data(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_prices(cls, prices):
        return cls([Champion(name, name, cls._cost(price)) for name, price in prices.items()])

    def resolve(self, name, details=""):
        candidates = self.by_name.get(name, [])
        if len(candidates) <= 1:
            return candidates
        # Never infer the base form merely because OCR failed to read a trait.
        compact = re.sub(r"\s+", "", details)
        explicit = [row for row in candidates if row.variant and row.variant in compact]
        return explicit if len(explicit) == 1 else candidates

    def summary(self):
        return {"metadata": self.metadata, "champion_records": len(self.champions),
                "unique_champion_names": len(self.by_name), "charms": len(self.charms),
                "ambiguous_names": {name: [row.id for row in rows]
                                    for name, rows in self.by_name.items() if len(rows) > 1}}
