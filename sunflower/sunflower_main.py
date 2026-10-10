"""Compatibility entry point; use python -m companion.cli for the new CLI."""
from datetime import datetime, timezone
import uuid

from companion.device import Device
from companion.session import Audit, Session
from companion.settings import Settings


class Sunflower:
    def __init__(self, config="config/example.toml"):
        self.settings = Settings.load(config)
        self.device = None
        self.session = None

    async def init_emulator(self):
        # Calibration is explicit; never silently change device resolution or DPI.
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        audit = Audit(self.settings.logs / name)
        self.device = await Device.open(self.settings, audit)
        self.session = Session(self.device, self.settings, audit)

    async def init_game(self):
        return await self.session.observe()

    async def wrapper_loop(self):
        return await self.main()

    async def main(self):
        return await self.session.run(execute=False, limit=10)

    async def start(self):
        try:
            await self.init_emulator()
            await self.init_game()
            return await self.wrapper_loop()
        finally:
            if self.device:
                await self.device.close()
