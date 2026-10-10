import unittest

from companion.perception import TextBox, integer, match_name, parse_frame, phase_of


class PerceptionTests(unittest.TestCase):
    def test_unknown_hero_is_not_forced_to_old_dictionary(self):
        self.assertIsNone(match_name("新赛季陌生英雄", ["蔚", "金克丝"]))
        self.assertIsNone(match_name("", ["蔚", "金克丝"]))

    def test_ambiguous_fuzzy_match_is_rejected(self):
        self.assertIsNone(match_name("ABCDEFGH", ["ABCDEFGX", "ABCDEFGY"]))

    def test_exact_match_is_kept(self):
        self.assertEqual(match_name(" 金克丝 ", ["蔚", "金克丝"]), "金克丝")

    def test_numeric_errors_are_unknown_not_exceptions(self):
        for value in ("2O", "", "-1", "1000"):
            self.assertIsNone(integer(value, 0, 999))

    def test_one_frame_keeps_unknown_shop_text(self):
        boxes = [TextBox("32", 1, 1, 10, 10, .99),
                 TextBox("5级", 21, 1, 10, 10, .99),
                 TextBox("2-3", 41, 1, 10, 10, .99),
                 TextBox("金克丝", 61, 1, 10, 10, .99),
                 TextBox("陌生英雄", 81, 1, 10, 10, .99),
                 TextBox("备战环节", 1, 40, 20, 10, .99)]
        layout = {"coin": [0, 0, 20, 20], "level": [20, 0, 20, 20],
                  "period": [40, 0, 20, 20],
                  "store": [[60, 0, 20, 20], [80, 0, 20, 20]]}
        snapshot = parse_frame(boxes, layout, {"金克丝": 5}, "frame-1", 10)
        self.assertEqual((snapshot.coin, snapshot.level, snapshot.period), (32, 5, (2, 3)))
        self.assertEqual(snapshot.store[0].name, "金克丝")
        self.assertIsNone(snapshot.store[1])
        self.assertEqual(snapshot.store_text[1], "陌生英雄")
        self.assertEqual(snapshot.phase, "preparation")

    def test_conflicting_phases_and_low_confidence_are_unknown(self):
        ready = TextBox("备战环节", 0, 0, 10, 10, .99)
        combat = TextBox("战斗环节", 0, 0, 10, 10, .99)
        self.assertEqual(phase_of([ready, combat]), "unknown")
        self.assertEqual(phase_of([TextBox("备战环节", 0, 0, 10, 10, .5)]), "unknown")

    def test_selection_blocks_preparation(self):
        boxes = [TextBox(word, 0, 0, 10, 10, .99) for word in ("备战环节", "选择强化符文")]
        self.assertEqual(phase_of(boxes), "selection")
