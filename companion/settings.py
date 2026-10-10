from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class Settings:
    host: str = "localhost"
    port: int = 16384
    width: int = 1024
    height: int = 720
    dpi: int = 240
    layout: Path = Path("config/layout.json")
    heroes: Path = Path("sunflower/statics/heroes.json")
    current_data_verified: bool = False
    targets: tuple[str, ...] = ()
    reserve_gold: int = 20
    max_actions: int = 1
    poll_seconds: float = 2.0
    action_delay: float = 0.5
    max_observation_age: float = 3.0
    logs: Path = Path("runs")

    @classmethod
    def load(cls, path: str | Path):
        path = Path(path).resolve()
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        known = set(cls.__dataclass_fields__)
        if set(data) - known:
            raise ValueError(f"Unknown settings: {sorted(set(data) - known)}")
        base = path.parent
        for key in ("layout", "heroes", "logs"):
            if key in data:
                data[key] = (base / data[key]).resolve()
        if "targets" in data:
            if not isinstance(data["targets"], list):
                raise ValueError("targets must be an array of hero names")
            data["targets"] = tuple(data["targets"])
        result = cls(**data)
        if type(result.current_data_verified) is not bool:
            raise ValueError("current_data_verified must be a boolean")
        if not all(isinstance(name, str) and name.strip() for name in result.targets):
            raise ValueError("targets must contain non-empty hero names")
        if not 1 <= result.port <= 65535:
            raise ValueError("ADB port must be between 1 and 65535")
        if min(result.width, result.height, result.dpi) <= 0:
            raise ValueError("Screen settings must be positive")
        if result.reserve_gold < 0 or result.max_actions < 1:
            raise ValueError("Invalid action limits")
        if min(result.poll_seconds, result.action_delay, result.max_observation_age) <= 0:
            raise ValueError("Timing settings must be positive")
        return result
