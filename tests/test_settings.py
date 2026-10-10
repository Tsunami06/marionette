from pathlib import Path
import tempfile
import unittest

from companion.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_example_paths_are_relative_to_config(self):
        path = Path(__file__).resolve().parents[1] / "config/example.toml"
        settings = Settings.load(path)
        self.assertTrue(settings.layout.is_file())
        self.assertTrue(settings.heroes.is_file())
        self.assertFalse(settings.current_data_verified)

    def test_string_verification_flag_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text('current_data_verified = "false"', encoding="utf-8")
            with self.assertRaises(ValueError):
                Settings.load(path)
