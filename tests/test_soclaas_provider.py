"""Unit tests for NUS SoCLaaS Provider."""

from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from urex_benchmark.models import ModelMessage, Scenario, Turn
from urex_benchmark.providers.soclaas import (
    SoCLaaSProvider,
    _load_env_file,
    encode_image_to_data_url,
)
from urex_benchmark.runner import ConversationRunner


class TestSoCLaaSProvider(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_img = Path(self.tmp_dir.name) / "test_diagram.png"
        self.test_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy_image_data")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_encode_image_to_data_url(self):
        data_url = encode_image_to_data_url(self.test_img)
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        b64_content = data_url.split(",", 1)[1]
        self.assertTrue(len(b64_content) > 0)

        with self.assertRaises(FileNotFoundError):
            encode_image_to_data_url("non_existent_image.png")

    def test_load_env_file(self):
        env_file = Path(self.tmp_dir.name) / ".env"
        env_file.write_text("SOCLAAS_API_KEY=test_clsk_key\nSOCLAAS_MODEL=test_model\n", encoding="utf-8")
        
        with patch.dict(os.environ, {}, clear=True):
            _load_env_file(env_file)
            self.assertEqual(os.environ.get("SOCLAAS_API_KEY"), "test_clsk_key")
            self.assertEqual(os.environ.get("SOCLAAS_MODEL"), "test_model")

    def test_build_openai_messages_with_multimodal_turns(self):
        provider = SoCLaaSProvider(
            model_identifier="test-model",
            api_key="test-key",
            system_prompt="You are an engineering tutor.",
        )

        history = [
            ModelMessage(role="student", content="What is this component?", image_path=str(self.test_img)),
            ModelMessage(role="assistant", content="It is a full adder."),
        ]

        # Current turn has no new image
        messages = provider._build_openai_messages(
            student_message="How do Cin and Cout work?",
            image_path=None,
            history=history,
        )

        self.assertEqual(len(messages), 4)
        # 1. System prompt
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "You are an engineering tutor.")
        # 2. History student message with image
        self.assertEqual(messages[1]["role"], "user")
        self.assertIsInstance(messages[1]["content"], list)
        self.assertEqual(messages[1]["content"][0]["type"], "text")
        self.assertEqual(messages[1]["content"][1]["type"], "image_url")
        # 3. History assistant message
        self.assertEqual(messages[2]["role"], "assistant")
        self.assertEqual(messages[2]["content"], "It is a full adder.")
        # 4. Current turn student query
        self.assertEqual(messages[3]["role"], "user")
        self.assertEqual(messages[3]["content"], "How do Cin and Cout work?")

    @patch("urllib.request.urlopen")
    def test_send_turn_success(self, mock_urlopen):
        mock_response_data = {
            "id": "chatcmpl-123",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "qwen2.5-vl",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "A is the first operand bit, B is the second.",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 25,
                "total_tokens": 145,
            },
        }

        mock_resp_obj = MagicMock()
        mock_resp_obj.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_resp_obj.__enter__.return_value = mock_resp_obj
        mock_urlopen.return_value = mock_resp_obj

        provider = SoCLaaSProvider(
            model_identifier="qwen2.5-vl",
            api_key="test-key",
            base_url="https://soclaas-api.comp.nus.edu.sg/v1",
        )

        conv_id = provider.start_conversation("scenario_01")
        response = provider.send_turn(
            conversation_id=conv_id,
            turn_id=1,
            student_message="Explain inputs A and B.",
            image_path=str(self.test_img),
            history=[],
        )

        self.assertEqual(response.content, "A is the first operand bit, B is the second.")
        self.assertEqual(response.token_usage["total_tokens"], 145)
        self.assertEqual(response.token_usage["prompt_tokens"], 120)
        self.assertEqual(response.token_usage["completion_tokens"], 25)
        self.assertEqual(response.model_identifier, "qwen2.5-vl")
        self.assertGreaterEqual(response.latency_ms, 0)

        # Verify outgoing request headers and payload
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://soclaas-api.comp.nus.edu.sg/v1/chat/completions")
        self.assertEqual(req.headers["Authorization"], "Bearer test-key")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "qwen2.5-vl")
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["role"], "user")

    def test_send_turn_missing_api_key_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = SoCLaaSProvider(model_identifier="dummy-model", api_key=None)
            provider.api_key = None
            with self.assertRaises(ValueError) as ctx:
                provider.send_turn(
                    conversation_id="c1",
                    turn_id=1,
                    student_message="Hello",
                    image_path=None,
                    history=[],
                )
            self.assertIn("SoCLaaS API Key not found", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_send_turn_unauthorized_401(self, mock_urlopen):
        fp = BytesIO(b'{"error": {"message": "Invalid API key provided"}}')
        http_err = urllib.error.HTTPError(
            url="https://soclaas-api.comp.nus.edu.sg/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=fp,
        )
        mock_urlopen.side_effect = http_err

        provider = SoCLaaSProvider(model_identifier="test-model", api_key="bad-key")
        with self.assertRaises(PermissionError) as ctx:
            provider.send_turn("c1", 1, "test", None, [])
        self.assertIn("401 Unauthorized", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_send_turn_non_vision_model_400(self, mock_urlopen):
        fp = BytesIO(b'{"error": {"message": "Model does not support image input"}}')
        http_err = urllib.error.HTTPError(
            url="https://soclaas-api.comp.nus.edu.sg/v1/chat/completions",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=fp,
        )
        mock_urlopen.side_effect = http_err

        provider = SoCLaaSProvider(model_identifier="text-only-model", api_key="valid-key")
        with self.assertRaises(RuntimeError) as ctx:
            provider.send_turn("c1", 1, "test", str(self.test_img), [])
        self.assertIn("rejected image input", str(ctx.exception))
        self.assertIn("Ensure you are targeting a multimodal/VLM model", str(ctx.exception))

    @patch("urllib.request.urlopen")
    def test_integration_with_conversation_runner(self, mock_urlopen):
        # Mock 5 consecutive turns
        def make_resp(text, turn):
            resp_data = {
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 10 * turn, "completion_tokens": 20, "total_tokens": 10 * turn + 20},
            }
            resp_obj = MagicMock()
            resp_obj.read.return_value = json.dumps(resp_data).encode("utf-8")
            resp_obj.__enter__.return_value = resp_obj
            return resp_obj

        mock_urlopen.side_effect = [
            make_resp("Turn 1 answer", 1),
            make_resp("Turn 2 answer", 2),
            make_resp("Turn 3 answer", 3),
            make_resp("Turn 4 answer", 4),
            make_resp("Turn 5 answer", 5),
        ]

        provider = SoCLaaSProvider(model_identifier="test-vlm", api_key="valid-key")
        output_dir = Path(self.tmp_dir.name) / "runs"
        runner = ConversationRunner(provider=provider, output_dir=output_dir)

        scenario = Scenario(
            scenario_id="soclaas_integration_sc",
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
        self.assertEqual(result.turns[0].model_response, "Turn 1 answer")
        self.assertEqual(result.turns[3].model_response, "Turn 4 answer")


if __name__ == "__main__":
    unittest.main()
