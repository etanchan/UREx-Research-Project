"""Unit tests for UREx benchmark validator."""

import json
from pathlib import Path
import tempfile
import unittest

from urex_benchmark.validator import BenchmarkValidator


class TestBenchmarkValidator(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.tmp_dir.name)
        self.scenarios_dir = self.base_path / "scenarios"
        self.keys_dir = self.base_path / "answer_keys"
        self.images_dir = self.base_path / "images"
        self.scenarios_dir.mkdir()
        self.keys_dir.mkdir()
        self.images_dir.mkdir()

        # Create dummy image
        self.img1 = self.images_dir / "diagram1.png"
        self.img1.write_bytes(b"dummy_png_bytes")
        self.img2 = self.images_dir / "diagram2.png"
        self.img2.write_bytes(b"dummy_png_bytes")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_scenario_dict(self, scenario_id="sc_01", status="ready", turn_count=5):
        turns = []
        for i in range(1, turn_count + 1):
            revised = str(self.img2) if i == 4 else None
            turns.append({
                "turn_id": i,
                "student_message": f"Question for turn {i}?",
                "revised_image_path": revised,
            })
        return {
            "scenario_id": scenario_id,
            "course": "CG3207",
            "title": "Test Title",
            "status": status,
            "initial_image_path": str(self.img1),
            "turns": turns,
        }

    def _create_key_dict(self, scenario_id="sc_01", turn_count=5):
        turns = []
        for i in range(1, turn_count + 1):
            turns.append({
                "turn_id": i,
                "expected_answer": f"Expected answer for turn {i}.",
            })
        return {
            "scenario_id": scenario_id,
            "turns": turns,
        }

    def test_valid_ready_scenario_passes(self):
        sc_data = self._create_scenario_dict("sc_01", "ready", 5)
        key_data = self._create_key_dict("sc_01", 5)

        with open(self.scenarios_dir / "sc_01.json", "w") as f:
            json.dump(sc_data, f)
        with open(self.keys_dir / "sc_01.json", "w") as f:
            json.dump(key_data, f)

        val = BenchmarkValidator(base_dir=self.base_path)
        report = val.validate_scenarios(self.scenarios_dir, self.keys_dir)

        self.assertFalse(report.has_errors)
        self.assertEqual(report.total_scenarios, 1)
        self.assertEqual(report.passed_ready_count, 1)

    def test_rejects_scenario_with_four_turns(self):
        sc_data = self._create_scenario_dict("sc_01", "ready", 4)
        key_data = self._create_key_dict("sc_01", 4)

        with open(self.scenarios_dir / "sc_01.json", "w") as f:
            json.dump(sc_data, f)
        with open(self.keys_dir / "sc_01.json", "w") as f:
            json.dump(key_data, f)

        val = BenchmarkValidator(base_dir=self.base_path)
        report = val.validate_scenarios(self.scenarios_dir, self.keys_dir)

        self.assertTrue(report.has_errors)
        errors = [i.message for i in report.issues if i.level == "ERROR"]
        self.assertTrue(any("exactly 5 turns" in err for err in errors))

    def test_rejects_missing_image_file_for_ready_status(self):
        sc_data = self._create_scenario_dict("sc_01", "ready", 5)
        sc_data["initial_image_path"] = "non_existent_image.png"
        key_data = self._create_key_dict("sc_01", 5)

        with open(self.scenarios_dir / "sc_01.json", "w") as f:
            json.dump(sc_data, f)
        with open(self.keys_dir / "sc_01.json", "w") as f:
            json.dump(key_data, f)

        val = BenchmarkValidator(base_dir=self.base_path)
        report = val.validate_scenarios(self.scenarios_dir, self.keys_dir)

        self.assertTrue(report.has_errors)
        errors = [i.message for i in report.issues if i.level == "ERROR"]
        self.assertTrue(any("Initial image file not found" in err for err in errors))

    def test_allows_missing_image_for_draft_status(self):
        sc_data = self._create_scenario_dict("sc_01", "draft", 5)
        sc_data["initial_image_path"] = "pending_crop.png"
        key_data = self._create_key_dict("sc_01", 5)

        with open(self.scenarios_dir / "sc_01.json", "w") as f:
            json.dump(sc_data, f)
        with open(self.keys_dir / "sc_01.json", "w") as f:
            json.dump(key_data, f)

        val = BenchmarkValidator(base_dir=self.base_path)
        report = val.validate_scenarios(self.scenarios_dir, self.keys_dir)

        # Draft scenarios with missing images should not produce validation errors
        self.assertFalse(report.has_errors)
        self.assertEqual(report.draft_count, 1)

    def test_strict_mode_rejects_draft(self):
        sc_data = self._create_scenario_dict("sc_01", "draft", 5)
        key_data = self._create_key_dict("sc_01", 5)

        with open(self.scenarios_dir / "sc_01.json", "w") as f:
            json.dump(sc_data, f)
        with open(self.keys_dir / "sc_01.json", "w") as f:
            json.dump(key_data, f)

        val = BenchmarkValidator(base_dir=self.base_path, require_all_ready=True)
        report = val.validate_scenarios(self.scenarios_dir, self.keys_dir)

        self.assertTrue(report.has_errors)
        errors = [i.message for i in report.issues if i.level == "ERROR"]
        self.assertTrue(any("strict mode" in err for err in errors))


if __name__ == "__main__":
    unittest.main()
