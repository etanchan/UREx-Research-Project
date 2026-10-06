"""Unit and integration tests for conversation runner."""

import json
from pathlib import Path
import tempfile
import unittest

from urex_benchmark.models import Scenario, Turn
from urex_benchmark.providers.mock import MockProvider
from urex_benchmark.runner import ConversationRunner


class TestConversationRunner(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp_dir.name) / "runs"
        self.output_dir.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_dummy_scenario(self, scenario_id="dummy_sc", revised_at_turn=4):
        turns = [
            Turn(turn_id=i, student_message=f"Student question {i}", revised_image_path=f"img_revised_{i}.png" if i == revised_at_turn else None)
            for i in range(1, 6)
        ]
        return Scenario(
            scenario_id=scenario_id,
            course="TEST",
            title="Dummy Scenario",
            status="ready",
            initial_image_path="initial_img.png",
            turns=turns,
        )

    def test_runner_executes_five_turns_in_order(self):
        scenario = self._create_dummy_scenario("test_sc_order")
        provider = MockProvider(model_identifier="mock-v1")
        runner = ConversationRunner(provider=provider, output_dir=self.output_dir)

        result = runner.run_scenario(scenario)

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.turns), 5)
        # Check turn order
        for idx, t in enumerate(result.turns, start=1):
            self.assertEqual(t.turn_id, idx)
            self.assertIsNotNone(t.model_response)
            self.assertIsNone(t.error)

    def test_immediate_persistence_and_file_existence(self):
        scenario = self._create_dummy_scenario("test_sc_persist")
        provider = MockProvider(model_identifier="mock-v1")
        runner = ConversationRunner(provider=provider, output_dir=self.output_dir)

        runner.run_scenario(scenario)

        expected_file = self.output_dir / "test_sc_persist.json"
        self.assertTrue(expected_file.exists())

        with open(expected_file, "r") as f:
            saved_data = json.load(f)

        self.assertEqual(saved_data["status"], "completed")
        self.assertEqual(len(saved_data["turns"]), 5)

    def test_failure_isolation_does_not_erase_completed_turns(self):
        scenario = self._create_dummy_scenario("test_sc_fail")
        # Configure mock provider to fail on turn 3
        provider = MockProvider(
            model_identifier="mock-v1",
            fail_scenario="test_sc_fail",
            fail_turn=3,
        )
        runner = ConversationRunner(provider=provider, output_dir=self.output_dir)

        result = runner.run_scenario(scenario)

        self.assertEqual(result.status, "failed")
        self.assertIn("Failed at turn 3", result.error)
        self.assertEqual(len(result.turns), 3)

        # Turns 1 and 2 must have succeeded and have non-null responses
        self.assertIsNotNone(result.turns[0].model_response)
        self.assertIsNone(result.turns[0].error)
        self.assertIsNotNone(result.turns[1].model_response)
        self.assertIsNone(result.turns[1].error)

        # Turn 3 recorded the error
        self.assertIsNone(result.turns[2].model_response)
        self.assertIn("Simulated network/provider error", result.turns[2].error)

        # File on disk must retain the partial run
        saved_file = self.output_dir / "test_sc_fail.json"
        self.assertTrue(saved_file.exists())
        with open(saved_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["status"], "failed")
        self.assertEqual(len(data["turns"]), 3)

    def test_scenario_failure_does_not_halt_subsequent_scenarios(self):
        sc1 = self._create_dummy_scenario("sc_first")
        sc2 = self._create_dummy_scenario("sc_second")

        # Provider fails on sc1, but sc2 should succeed
        provider = MockProvider(
            model_identifier="mock-v1",
            fail_scenario="sc_first",
            fail_turn=2,
        )
        runner = ConversationRunner(provider=provider, output_dir=self.output_dir)

        manifest = runner.run_all([sc1, sc2], skip_drafts=False)

        self.assertEqual(manifest["total_submitted"], 2)
        self.assertEqual(manifest["failed"], 1)
        self.assertEqual(manifest["completed"], 1)

        # Both files exist
        self.assertTrue((self.output_dir / "sc_first.json").exists())
        self.assertTrue((self.output_dir / "sc_second.json").exists())


if __name__ == "__main__":
    unittest.main()
