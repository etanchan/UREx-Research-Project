"""Strict benchmark integrity test verifying expected answers never reach model providers."""

import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import unittest

from urex_benchmark.models import AnswerKey, Scenario
from urex_benchmark.providers.base import BaseProvider, ProviderResponse
from urex_benchmark.runner import ConversationRunner


class PayloadInspectorProvider(BaseProvider):
    """Provider that intercepts and records all payloads to check for data leaks."""

    def __init__(self, model_identifier="inspector-model"):
        super().__init__(model_identifier)
        self.recorded_payload_texts: List[str] = []

    def start_conversation(self, scenario_id: str) -> str:
        return f"leak-check-{scenario_id}"

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[Any],
    ) -> ProviderResponse:
        # Collect every bit of text sent into the provider
        self.recorded_payload_texts.append(student_message)
        if image_path:
            self.recorded_payload_texts.append(image_path)
        for msg in history:
            self.recorded_payload_texts.append(msg.content)

        return ProviderResponse(
            content=f"Inspector response for turn {turn_id}",
            token_usage={"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            model_identifier=self.model_identifier,
        )


class TestZeroLeakage(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_fixture_expected_answers_never_enter_model_requests(self):
        scenario_path = Path("data/fixtures/scenarios/demo_counter.json")
        key_path = Path("data/fixtures/answer_keys/demo_counter.json")

        self.assertTrue(scenario_path.exists(), "Demo scenario must exist")
        self.assertTrue(key_path.exists(), "Demo answer key must exist")

        scenario = Scenario.from_json_file(scenario_path)
        answer_key = AnswerKey.from_json_file(key_path)

        inspector = PayloadInspectorProvider()
        runner = ConversationRunner(provider=inspector, output_dir=self.output_dir)

        result = runner.run_scenario(scenario)
        self.assertEqual(result.status, "completed")

        # Gather all private strings from answer key
        private_phrases: List[str] = []
        for kturn in answer_key.turns:
            private_phrases.append(kturn.expected_answer)
            private_phrases.extend(kturn.key_points)
            private_phrases.extend(kturn.common_misconceptions)

        # Concatenate all provider payload text
        all_payload_corpus = " ".join(inspector.recorded_payload_texts).lower()

        # Verify not a single private phrase appears in model requests
        for phrase in private_phrases:
            phrase_clean = phrase.strip().lower()
            if len(phrase_clean) > 5:  # meaningful phrase
                self.assertNotIn(
                    phrase_clean,
                    all_payload_corpus,
                    f"LEAK DETECTED! Private expected answer '{phrase}' found in provider payload corpus!"
                )

    def test_runner_class_has_no_answer_key_dependencies(self):
        """Ensure ConversationRunner has no import or parameter accepting answer keys."""
        import inspect
        runner_sig = inspect.signature(ConversationRunner.__init__)
        params = list(runner_sig.parameters.keys())

        for p in params:
            self.assertNotIn("key", p.lower(), "Runner init must not accept answer keys")
            self.assertNotIn("answer", p.lower(), "Runner init must not accept answer keys")


if __name__ == "__main__":
    unittest.main()
