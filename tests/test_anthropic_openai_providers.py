"""Unit tests for Anthropic and OpenAI Providers."""

from pathlib import Path
import tempfile
import unittest

from urex_benchmark.models import ModelMessage
from urex_benchmark.providers.anthropic import AnthropicProvider, encode_image_for_anthropic
from urex_benchmark.providers.openai import OpenAIProvider


class TestNewProviders(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_img = Path(self.tmp_dir.name) / "test_diagram.png"
        self.test_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_image_data")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_encode_image_for_anthropic(self):
        block = encode_image_for_anthropic(self.test_img)
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["type"], "base64")
        self.assertEqual(block["source"]["media_type"], "image/png")
        self.assertTrue(len(block["source"]["data"]) > 0)

    def test_build_anthropic_messages_multimodal(self):
        provider = AnthropicProvider(
            model_identifier="claude-haiku-5-5",
            api_key="mock-key",
            thinking_level="high",
        )
        history = [
            ModelMessage(role="student", content="Explain adder", image_path=str(self.test_img)),
            ModelMessage(role="assistant", content="An adder sums bits."),
        ]
        messages = provider._build_anthropic_messages(
            student_message="Follow up query",
            image_path=None,
            history=history,
        )
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(len(messages[0]["content"]), 2)
        self.assertEqual(messages[0]["content"][0]["type"], "image")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")

    def test_build_openai_messages_multimodal(self):
        provider = OpenAIProvider(
            model_identifier="gpt-6.1-sol",
            api_key="mock-key",
            thinking_level="high",
        )
        history = [
            ModelMessage(role="student", content="Explain adder", image_path=str(self.test_img)),
            ModelMessage(role="assistant", content="An adder sums bits."),
        ]
        messages = provider._build_openai_messages(
            student_message="Follow up query",
            image_path=str(self.test_img),
            history=history,
        )
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"][0]["type"], "image_url")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")
        self.assertEqual(messages[2]["content"][0]["type"], "image_url")


if __name__ == "__main__":
    unittest.main()
