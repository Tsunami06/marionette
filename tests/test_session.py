import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import time
import unittest

from companion.perception import Card, Snapshot
from companion.session import Audit, Session
from companion.settings import Settings


def snapshot(frame_id="before", **changes):
    base = Snapshot(frame_id, time.time(), "preparation", 30, 5, (2, 3),
                    (Card("目标英雄", 3), None, None, None, None),
                    store_text=("目标英雄", "", "", "", ""))
    return replace(base, **changes)


class FakeDevice:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.clicks = []
        self.observing = False

    async def observe(self):
        if self.observing:
            raise AssertionError("Overlapping device operations")
        self.observing = True
        try:
            await asyncio.sleep(0)
            frame = next(self.frames)
            # Model a screenshot captured at observation time, unless explicitly stale.
            if time.time() - frame.captured_at < 3:
                frame = replace(frame, captured_at=time.time())
            return frame
        finally:
            self.observing = False

    async def buy(self, slot):
        self.clicks.append(slot)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings(current_data_verified=True, action_delay=.001)

    def session(self, frames, **settings):
        device = FakeDevice(frames)
        return Session(device, replace(self.settings, **settings), Audit(Path(self.temp.name)))

    async def test_dry_run_never_clicks(self):
        session = self.session([snapshot()])
        result = await session.buy(0)
        self.assertEqual(result.status, "dry_run")
        self.assertEqual(session.device.clicks, [])

    async def test_unknown_and_stale_frames_never_click(self):
        for frame in (snapshot(phase="unknown"), snapshot(captured_at=time.time()-10),
                      snapshot(errors=("coin",)), snapshot(store=(None,)*5)):
            with self.subTest(frame=frame):
                session = self.session([frame])
                self.assertEqual((await session.buy(0, execute=True)).status, "blocked")
                self.assertEqual(session.device.clicks, [])

    async def test_unverified_data_blocks_real_input(self):
        session = self.session([snapshot()], current_data_verified=False)
        self.assertEqual((await session.buy(0, execute=True)).reason, "season_data_not_verified")
        self.assertEqual(session.device.clicks, [])

    async def test_gold_reserve_and_changed_shop_block(self):
        session = self.session([snapshot(coin=21)])
        self.assertEqual((await session.buy(0, execute=True)).reason, "gold_reserve")
        session = self.session([snapshot()])
        self.assertEqual((await session.buy(0, execute=True, expected_name="另一个英雄")).reason, "shop_changed")

    async def test_purchase_requires_debit_and_name_disappearance(self):
        after = snapshot("after", coin=27, store=(None,)*5, store_text=("",)*5)
        session = self.session([snapshot(), after])
        self.assertEqual((await session.buy(0, execute=True)).status, "verified")
        self.assertEqual(session.device.clicks, [0])

    async def test_unchanged_or_unmatched_shop_pauses_without_retry(self):
        for after in (snapshot("after"),
                      snapshot("after", coin=27, store=(None,)*5,
                               store_text=("陌生英雄", "", "", "", "")),
                      snapshot("after", coin=27, period=(2, 4), store=(None,)*5, store_text=("",)*5)):
            session = self.session([snapshot(), after, snapshot("retry")])
            self.assertEqual((await session.buy(0, execute=True)).status, "paused")
            self.assertEqual((await session.buy(0, execute=True)).reason, "session_paused")
            self.assertEqual(session.device.clicks, [0])

    async def test_action_budget_prevents_second_click(self):
        after = snapshot("after", coin=27, store=(None,)*5, store_text=("",)*5)
        session = self.session([snapshot(), after, snapshot("next")])
        await session.buy(0, execute=True)
        self.assertEqual((await session.buy(0, execute=True)).reason, "action_limit")
        self.assertEqual(session.device.clicks, [0])

    async def test_concurrent_requests_are_serialized(self):
        session = self.session([snapshot("one"), snapshot("two")])
        results = await asyncio.gather(session.buy(0), session.observe())
        self.assertEqual(results[0].status, "dry_run")
        self.assertEqual(results[1].frame_id, "two")

    async def test_unknown_phase_stops_loop(self):
        session = self.session([snapshot(phase="unknown")])
        self.assertEqual(await session.run(limit=10), "paused")
        self.assertEqual(session.device.clicks, [])

    async def test_result_stops_loop(self):
        session = self.session([snapshot(phase="result")])
        self.assertEqual(await session.run(limit=10), "result")
