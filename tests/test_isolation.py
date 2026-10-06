"""Tests verifying conversation isolation and revised-image handling."""

from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import unittest

from urex_benchmark.models import ModelMessage, Scenario, Turn
from urex_benchmark.providers.base import BaseProvider, ProviderResponse
from urex_benchmark.runner import ConversationRunner


class RecordingSpyProvider(BaseProvider):
    """Spy provider that records all interactions for test assertions."""

    def __init__(self, model_identifier="spy-model"):
        super().__init__(model_identifier)
        self.conversations_created: List[str] = []
        self.closed_conversations: List[str] = []
        self.call_history: List[Dict[str, Any]] = []

    def start_conversation(self, scenario_id: str) -> str:
        conv_id = f"session-{scenario_id}-{len(self.conversations_created)}"
        self.conversations_created.append(conv_id)
        return conv_id

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        self.call_history.append({
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "student_message": student_message,
            "image_path": image_path,
            "history_roles": [m.role for m in history],
            "history_contents": [m.content for m in history],
            "history_length": len(history),
        })
        return ProviderResponse(
            content=f"Spy response to turn {turn_id}",
            token_usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
            latency_ms=5.0,
            model_identifier=self.model_identifier,
        )

    def close_conversation(self, conversation_id: str) -> None:
        self.closed_conversations.append(conversation_id)


class TestConversationIsolation(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_scenarios_have_isolated_conversations(self):
        sc_a = Scenario(
            scenario_id="scenario_A",
            course="CG3207",
            title="Scenario A",
            status="ready",
            initial_image_path="img_a.png",
            turns=[Turn(i, f"A question {i}") for i in range(1, 6)],
        )
        sc_b = Scenario(
            scenario_id="scenario_B",
            course="CG2271",
            title="Scenario B",
            status="ready",
            initial_image_path="img_b.png",
            turns=[Turn(i, f"B question {i}") for i in range(1, 6)],
        )

        spy = RecordingSpyProvider()
        runner = ConversationRunner(provider=spy, output_dir=self.output_dir)

        runner.run_all([sc_a, sc_b], skip_drafts=False)

        # Check that two distinct conversations were created and closed
        self.assertEqual(len(spy.conversations_created), 2)
        self.assertEqual(len(spy.closed_conversations), 2)
        conv_a = spy.conversations_created[0]
        conv_b = spy.conversations_created[1]
        self.assertNotEqual(conv_a, conv_b)

        # Calls for scenario B must never contain scenario A texts in history
        calls_b = [c for c in spy.call_history if c["conversation_id"] == conv_b]
        for c in calls_b:
            for hist_text in c["history_contents"]:
                self.assertNotIn("A question", hist_text)

        # Turn 1 of scenario B must start with empty history
        self.assertEqual(calls_b[0]["history_length"], 0)

    def test_revised_image_handling(self):
        turns = [
            Turn(1, "Question 1"),
            Turn(2, "Question 2"),
            Turn(3, "Question 3"),
            Turn(4, "Question 4 with revised image", revised_image_path="revised_circuit.png"),
            Turn(5, "Question 5"),
        ]
        scenario = Scenario(
            scenario_id="scenario_revised_img",
            course="CS2113",
            title="Revised Image Test",
            status="ready",
            initial_image_path="original_circuit.png",
            turns=turns,
        )

        spy = RecordingSpyProvider()
        runner = ConversationRunner(provider=spy, output_dir=self.output_dir)
        runner.run_scenario(scenario)

        self.assertEqual(len(spy.call_history), 5)

        # Turn 1: initial image
        self.assertEqual(spy.call_history[0]["image_path"], "original_circuit.png")
        # Turn 2: None
        self.assertIsNone(spy.call_history[1]["image_path"])
        # Turn 3: None
        self.assertIsNone(spy.call_history[2]["image_path"])
        # Turn 4: revised image attached
        self.assertEqual(spy.call_history[3]["image_path"], "revised_circuit.png")
        # Turn 5: None
        self.assertIsNone(spy.call_history[4]["image_path"])

    def test_history_grows_sequentially(self):
        scenario = Scenario(
            scenario_id="scenario_history",
            course="TEST",
            title="History Growth Test",
            status="ready",
            initial_image_path="img.png",
            turns=[Turn(i, f"Question {i}") for i in range(1, 6)],
        )

        spy = RecordingSpyProvider()
        runner = ConversationRunner(provider=spy, output_dir=self.output_dir)
        runner.run_scenario(scenario)

        # Turn 1 history length: 0
        # Turn 2 history length: 2 (student 1 + assistant 1)
        # Turn 3 history length: 4 (student 1,2 + assistant 1,2)
        # Turn 4 history length: 6
        # Turn 5 history length: 8
        expected_lengths = [0, 2, 4, 6, 8]
        for idx, exp_len in enumerate(expected_lengths):
            self.assertEqual(spy.call_history[idx]["history_length"], exp_len)


if __name__ == "__main__":
    unittest.main()
