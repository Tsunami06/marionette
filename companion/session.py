"""Serialized observation/action loop with bounded purchases and audit logs."""
import asyncio
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str
    slot: int
    before_frame: str | None = None
    after_frame: str | None = None


class Audit:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def write(self, kind, value):
        record = {"time": time.time(), "event": kind, "data": value}
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


class Session:
    def __init__(self, device, settings, audit):
        self.device = device
        self.settings = settings
        self.audit = audit
        self.lock = asyncio.Lock()
        self.paused = False
        self.actions = 0

    async def _observe(self):
        snapshot = await self.device.observe()
        self.audit.write("observation", snapshot.json())
        return snapshot

    async def observe(self):
        async with self.lock:
            return await self._observe()

    async def buy(self, slot, execute=False, expected_name=None):
        async with self.lock:
            before = None
            try:
                before = await self._observe()
                reason = None
                if self.paused:
                    reason = "session_paused"
                elif not 0 <= slot < len(before.store):
                    reason = "invalid_slot"
                elif before.phase != "preparation":
                    reason = "not_preparation"
                elif time.time() - before.captured_at > self.settings.max_observation_age:
                    reason = "stale_observation"
                elif before.errors:
                    reason = "incomplete_observation"
                elif before.store[slot] is None or before.store[slot].price is None:
                    reason = "unknown_card_or_price"
                elif expected_name and before.store[slot].name != expected_name:
                    reason = "shop_changed"
                elif before.coin - before.store[slot].price < self.settings.reserve_gold:
                    reason = "gold_reserve"
                elif self.actions >= self.settings.max_actions:
                    reason = "action_limit"
                elif execute and not self.settings.current_data_verified:
                    reason = "season_data_not_verified"
                if reason:
                    return self._outcome(Outcome("blocked", reason, slot, before.frame_id))
                if not execute:
                    return self._outcome(Outcome("dry_run", "no_input_sent", slot, before.frame_id))
                # Count the attempt before input: an ambiguous failure must never cause an automatic retry.
                self.actions += 1
                self.audit.write("action_started", {"slot": slot, "before_frame": before.frame_id})
                await self.device.buy(slot)
                await asyncio.sleep(self.settings.action_delay)
                after = await self._observe()
                fresh = (after.frame_id != before.frame_id
                         and after.captured_at >= before.captured_at
                         and time.time() - after.captured_at <= self.settings.max_observation_age)
                same_round = before.period == after.period and after.phase == "preparation"
                card = before.store[slot]
                expected_coin = before.coin - card.price
                # Require exact debit and disappearance of the target name, with no unmatched
                # OCR text in that slot. This is purchase evidence, not a bench inventory check.
                shop_text_missing = (len(after.store_text) == len(after.store)
                                     and not after.store_text[slot].strip())
                verified = (fresh and same_round and not after.errors and card.price > 0
                            and after.coin == expected_coin and after.store[slot] is None
                            and shop_text_missing and before.coin != after.coin)
                if verified:
                    return self._outcome(Outcome("verified", "debit_and_name_disappearance", slot,
                                                 before.frame_id, after.frame_id))
                self.paused = True
                return self._outcome(Outcome("paused", "purchase_unconfirmed", slot,
                                             before.frame_id, after.frame_id))
            except Exception as error:
                self.paused = True
                return self._outcome(Outcome("paused", f"{type(error).__name__}: {error}", slot,
                                             before.frame_id if before else None))

    def _outcome(self, result):
        self.audit.write("action_result", asdict(result))
        return result

    async def run(self, execute=False, limit=None):
        iterations = 0
        while not self.paused and (limit is None or iterations < limit):
            try:
                snapshot = await self.observe()
                if snapshot.phase == "result":
                    return "result"
                if snapshot.phase in ("unknown", "selection"):
                    self.paused = True
                    self.audit.write("paused", {"reason": f"unsupported_phase:{snapshot.phase}"})
                    break
                if snapshot.phase == "preparation":
                    for slot, card in enumerate(snapshot.store):
                        if card and card.name in self.settings.targets:
                            result = await self.buy(slot, execute, expected_name=card.name)
                            if result.status in ("verified", "paused"):
                                break
                iterations += 1
                if iterations < (limit if limit is not None else float("inf")):
                    await asyncio.sleep(self.settings.poll_seconds)
            except Exception as error:
                self.paused = True
                self.audit.write("paused", {"reason": f"{type(error).__name__}: {error}"})
        return "paused" if self.paused else "limit_reached"
