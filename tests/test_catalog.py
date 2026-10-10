from pathlib import Path
import unittest

from companion.catalog import Catalog
from companion.perception import TextBox, parse_frame


ROOT = Path(__file__).resolve().parents[1]


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog.load(ROOT / "companion/data/s18-18.3.json")

    def test_multiple_lux_identities_survive_import_and_require_trait_evidence(self):
        rows = self.catalog.by_name["拉克丝"]
        self.assertGreater(len(rows), 1)
        self.assertEqual(len({row.id for row in rows}), len(rows))
        self.assertEqual(len(self.catalog.resolve("拉克丝")), len(rows))
        resolved = self.catalog.resolve("拉克丝", "大元素使 灵魂莲华")
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].variant, "灵魂莲华")
        self.assertEqual(len(self.catalog.resolve("拉克丝", "灵魂莲华 黑荆棘")), len(rows))

    def test_reference_provenance_is_not_an_execution_approval(self):
        self.assertFalse(self.catalog.metadata["device_verified"])
        self.assertEqual(self.catalog.metadata["verification"], "reference_only")
        self.assertEqual(self.catalog.metadata["patch"], "18.3")
        row = self.catalog.charms_by_name["余震"]
        self.assertFalse(row["provenance"]["verified_for_current_patch"])

    def test_legacy_same_name_rows_are_preserved_and_invalid_cost_is_unknown(self):
        catalog = Catalog.from_data({"data": {
            "one": {"name": "同名", "buyPrice": "3"},
            "two": {"name": "同名", "buyPrice": "4"},
            "bad": {"name": "未知费用", "buyPrice": True}}})
        self.assertEqual(len(catalog.by_name["同名"]), 2)
        self.assertIsNone(catalog.by_name["未知费用"][0].cost)

    def test_shop_distinguishes_charm_and_tracks_ambiguous_lux(self):
        layout = {"coin": [0, 0, 20, 20], "level": [20, 0, 20, 20],
                  "period": [40, 0, 20, 20], "store": [[60, 0, 20, 20], [80, 0, 20, 20]],
                  "store_details": [None, [80, 20, 20, 20]]}
        def box(text, x, y=1):
            return TextBox(text, x, y, 10, 10, .99)
        boxes = [box("32", 1), box("5级", 21), box("2-3", 41),
                 box("余震", 61), box("拉克丝", 81)]
        before = parse_frame(boxes, layout, self.catalog, "one", 10)
        self.assertEqual(before.store[0].kind, "charm")
        self.assertEqual(before.store[1].identity_status, "ambiguous")
        self.assertIsNone(before.store[1].entity_id)
        after = parse_frame(boxes + [box("灵魂莲华", 81, 21)], layout, self.catalog, "two", 11)
        self.assertEqual(after.store[1].identity_status, "resolved")
        self.assertEqual(after.store[1].entity_id, self.catalog.resolve("拉克丝", "灵魂莲华")[0].id)


if __name__ == "__main__":
    unittest.main()
