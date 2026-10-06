"""Google Gemini Provider for UREx benchmark."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.request
import uuid

from urex_benchmark.models import ModelMessage
from urex_benchmark.providers.base import BaseProvider, ProviderResponse
from urex_benchmark.providers.soclaas import _load_env_file


def encode_image_for_gemini(image_path: str | Path) -> Dict[str, str]:
    """Reads an image from disk and formats it for Gemini inline_data."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Diagram image not found at path: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(p))
    if not mime_type:
        mime_type = "image/png"

    with open(p, "rb") as img_file:
        b64_str = base64.b64encode(img_file.read()).decode("utf-8")

    return {
        "mime_type": mime_type,
        "data": b64_str,
    }


class GeminiProvider(BaseProvider):
    """Vision-Language Model provider connecting to Google Gemini REST API."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model_identifier: str = "gemini-flash-latest", **settings: Any):
        super().__init__(model_identifier, **settings)

        _load_env_file()

        self.api_key = (
            settings.get("api_key")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self.temperature = float(settings.get("temperature", 0.2))
        self.max_tokens = int(settings.get("max_tokens", 2048))
        self.timeout = float(settings.get("timeout", 120.0))
        self.system_prompt = settings.get("system_prompt")
        self.active_conversations: Dict[str, Dict[str, Any]] = {}

    def start_conversation(self, scenario_id: str) -> str:
        """Initializes a new multi-turn conversation session."""
        conv_id = f"gemini-{scenario_id}-{uuid.uuid4().hex[:8]}"
        self.active_conversations[conv_id] = {
            "scenario_id": scenario_id,
            "turns": [],
        }
        return conv_id

    def _build_gemini_contents(
        self,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> List[Dict[str, Any]]:
        """Constructs multi-turn contents payload for Gemini API."""
        contents: List[Dict[str, Any]] = []

        # Process previous history
        for msg in history:
            role = "user" if msg.role == "student" else "model"
            parts: List[Dict[str, Any]] = []

            if msg.image_path and Path(msg.image_path).is_file():
                inline_img = encode_image_for_gemini(msg.image_path)
                parts.append({"inline_data": inline_img})

            parts.append({"text": msg.content})
            contents.append({"role": role, "parts": parts})

        # Process current turn
        current_parts: List[Dict[str, Any]] = []
        if image_path and Path(image_path).is_file():
            inline_img = encode_image_for_gemini(image_path)
            current_parts.append({"inline_data": inline_img})

        current_parts.append({"text": student_message})
        contents.append({"role": "user", "parts": current_parts})

        return contents

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        """Sends student turn to Gemini generateContent endpoint."""
        if not self.api_key:
            raise ValueError(
                "Gemini API Key not found. Please set GEMINI_API_KEY in your .env or environment."
            )

        contents = self._build_gemini_contents(student_message, image_path, history)

        model_name = self.model_identifier
        if model_name.startswith("models/"):
            model_name = model_name[len("models/"):]

        endpoint = f"{self.API_BASE}/models/{model_name}:generateContent?key={self.api_key}"

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }

        if self.system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": self.system_prompt}]
            }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=endpoint,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        max_retries = int(self.settings.get("max_retries", 3))
        backoff_delay = 2.0

        for attempt in range(max_retries + 1):
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    resp_bytes = resp.read()
                    latency_ms = (time.perf_counter() - t0) * 1000.0

                result = json.loads(resp_bytes.decode("utf-8"))

                candidates = result.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"Gemini returned no candidates: {result}")

                # Extract generated text from candidate parts
                parts = candidates[0].get("content", {}).get("parts", [])
                reply_text = "".join(part.get("text", "") for part in parts)

                usage = result.get("usageMetadata", {})
                token_usage = {
                    "prompt_tokens": usage.get("promptTokenCount", 0),
                    "completion_tokens": usage.get("candidatesTokenCount", 0),
                    "total_tokens": usage.get("totalTokenCount", 0),
                }

                if conversation_id in self.active_conversations:
                    self.active_conversations[conversation_id]["turns"].append(turn_id)

                return ProviderResponse(
                    content=reply_text,
                    token_usage=token_usage,
                    latency_ms=round(latency_ms, 2),
                    model_identifier=self.model_identifier,
                    raw_metadata={
                        "finishReason": candidates[0].get("finishReason"),
                        "modelVersion": result.get("modelVersion"),
                    },
                )

            except urllib.error.HTTPError as http_err:
                error_body = ""
                try:
                    error_body = http_err.read().decode("utf-8")
                    parsed = json.loads(error_body)
                    error_body = parsed.get("error", {}).get("message", error_body)
                except Exception:
                    pass

                # Retry on high demand (503) or rate limits (429)
                if http_err.code in (429, 503) and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if http_err.code == 400 and ("key" in error_body.lower() or "api_key" in error_body.lower()):
                    raise PermissionError(f"Gemini API Error: Invalid GEMINI_API_KEY. {error_body}") from http_err

                raise RuntimeError(
                    f"Gemini API HTTP {http_err.code} ({http_err.reason}): {error_body}"
                ) from http_err

            except (TimeoutError, urllib.error.URLError) as net_err:
                # Retry on transient network or read timeouts if attempts remain
                is_timeout = isinstance(net_err, TimeoutError) or "timed out" in str(net_err).lower()
                if is_timeout and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if isinstance(net_err, urllib.error.URLError):
                    raise ConnectionError(
                        f"Failed to connect to Google Gemini API: {net_err.reason}"
                    ) from net_err
                raise

    def close_conversation(self, conversation_id: str) -> None:
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
