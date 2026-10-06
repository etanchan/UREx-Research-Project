"""Unit tests for Google Gemini Provider."""

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from urex_benchmark.models import ModelMessage, Scenario, Turn
from urex_benchmark.providers.gemini import (
    GeminiProvider,
    encode_image_for_gemini,
)
from urex_benchmark.runner import ConversationRunner


class TestGeminiProvider(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_img = Path(self.tmp_dir.name) / "test_diagram.png"
        self.test_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_image_data")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_encode_image_for_gemini(self):
        img_dict = encode_image_for_gemini(self.test_img)
        self.assertEqual(img_dict["mime_type"], "image/png")
        self.assertTrue(len(img_dict["data"]) > 0)

        with self.assertRaises(FileNotFoundError):
            encode_image_for_gemini("non_existent_image.png")

    def test_build_gemini_contents_multimodal(self):
        provider = GeminiProvider(
            model_identifier="gemini-flash-latest",
            api_key="test-key",
            system_prompt="You are an engineering tutor.",
        )

        history = [
            ModelMessage(role="student", content="What is this component?", image_path=str(self.test_img)),
            ModelMessage(role="assistant", content="It is a full adder."),
        ]

        contents = provider._build_gemini_contents(
            student_message="How do Cin and Cout work?",
            image_path=None,
            history=history,
        )

        self.assertEqual(len(contents), 3)
        # 1. First turn: user with image and text
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(len(contents[0]["parts"]), 2)
        self.assertIn("inline_data", contents[0]["parts"][0])
        self.assertEqual(contents[0]["parts"][1]["text"], "What is this component?")

        # 2. Second turn: model response
        self.assertEqual(contents[1]["role"], "model")
        self.assertEqual(contents[1]["parts"][0]["text"], "It is a full adder.")

        # 3. Third turn: user query
        self.assertEqual(contents[2]["role"], "user")
        self.assertEqual(contents[2]["parts"][0]["text"], "How do Cin and Cout work?")

    @patch("urllib.request.urlopen")
    def test_send_turn_success(self, mock_urlopen):
        mock_response_data = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Cin is carry-in and Cout is carry-out."}],
                        "role": "model",
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 85,
                "candidatesTokenCount": 18,
                "totalTokenCount": 103,
            },
            "modelVersion": "gemini-3.8-flash",
        }

        mock_resp_obj = MagicMock()
        mock_resp_obj.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp_obj.__enter__.return_value = mock_resp_obj
        mock_urlopen.return_value = mock_resp_obj

        provider = GeminiProvider(
            model_identifier="gemini-flash-latest",
            api_key="test-key",
        )

        conv_id = provider.start_conversation("scenario_01")
        response = provider.send_turn(
            conversation_id=conv_id,
            turn_id=1,
            student_message="Explain Cin and Cout.",
            image_path=str(self.test_img),
            history=[],
        )

        self.assertEqual(response.content, "Cin is carry-in and Cout is carry-out.")
        self.assertEqual(response.token_usage["prompt_tokens"], 85)
        self.assertEqual(response.token_usage["completion_tokens"], 18)
        self.assertEqual(response.token_usage["total_tokens"], 103)
        self.assertEqual(response.model_identifier, "gemini-flash-latest")
        self.assertGreaterEqual(response.latency_ms, 0)

        # Verify outgoing URL
        req = mock_urlopen.call_args[0][0]
        self.assertIn("models/gemini-flash-latest:generateContent", req.full_url)
        self.assertIn("key=test-key", req.full_url)

    def test_send_turn_missing_key_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = GeminiProvider(model_identifier="gemini-flash-latest", api_key=None)
            provider.api_key = None
            with self.assertRaises(ValueError) as ctx:
                provider.send_turn("c1", 1, "test", None, [])
            self.assertIn("Gemini API Key not found", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_send_turn_invalid_key_400(self, mock_urlopen):
        fp = BytesIO(b'{"error": {"code": 400, "message": "API_KEY_INVALID"}}')
        http_err = urllib.error.HTTPError(
            url="https://generativelanguage.googleapis.com",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=fp,
        )
        mock_urlopen.side_effect = http_err

        provider = GeminiProvider(model_identifier="gemini-flash-latest", api_key="bad-key")
        with self.assertRaises(PermissionError) as ctx:
            provider.send_turn("c1", 1, "test", None, [])
        self.assertIn("Invalid GEMINI_API_KEY", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_integration_with_conversation_runner(self, mock_urlopen):
        def make_gemini_resp(text, turn):
            resp_data = {
                "candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}],
                "usageMetadata": {"promptTokenCount": turn * 10, "candidatesTokenCount": 15, "totalTokenCount": turn * 10 + 15},
            }
            resp_obj = MagicMock()
            resp_obj.read.return_value = json.dumps(resp_data).encode("utf-8")
            resp_obj.__enter__.return_value = resp_obj
            return resp_obj

        mock_urlopen.side_effect = [
            make_gemini_resp("Gemini Turn 1", 1),
            make_gemini_resp("Gemini Turn 2", 2),
            make_gemini_resp("Gemini Turn 3", 3),
            make_gemini_resp("Gemini Turn 4", 4),
            make_gemini_resp("Gemini Turn 5", 5),
        ]

        provider = GeminiProvider(model_identifier="gemini-flash-latest", api_key="valid-key")
        output_dir = Path(self.tmp_dir.name) / "runs"
        runner = ConversationRunner(provider=provider, output_dir=output_dir)

        scenario = Scenario(
            scenario_id="gemini_integration_sc",
            course="CG3207",
            title="Adder Testing",
            status="ready",
            initial_image_path=str(self.test_img),
            turns=[
                Turn(turn_id=1, student_message="Turn 1 question"),
                Turn(turn_id=2, student_message="Turn 2 question"),
                Turn(turn_id=3, student_message="Turn 3 question"),
                Turn(turn_id=4, student_message="Turn 4 question", revised_image_path=str(self.test_img)),
                Turn(turn_id=5, student_message="Turn 5 question"),
            ],
        )

        result = runner.run_scenario(scenario)
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.turns), 5)
        self.assertEqual(result.turns[0].model_response, "Gemini Turn 1")
        self.assertEqual(result.turns[3].model_response, "Gemini Turn 4")


if __name__ == "__main__":
    unittest.main()
