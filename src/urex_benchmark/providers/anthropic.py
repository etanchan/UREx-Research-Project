"""Anthropic Claude Provider for UREx benchmark."""

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


def encode_image_for_anthropic(image_path: str | Path) -> Dict[str, Any]:
    """Reads an image from disk and formats it for Anthropic image block."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Diagram image not found at path: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(p))
    if not mime_type:
        mime_type = "image/png"

    with open(p, "rb") as img_file:
        b64_str = base64.b64encode(img_file.read()).decode("utf-8")

    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": b64_str,
        },
    }


class AnthropicProvider(BaseProvider):
    """Vision-Language Model provider connecting to Anthropic Messages API."""

    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, model_identifier: str = "claude-haiku-5-5", **settings: Any):
        super().__init__(model_identifier, **settings)

        _load_env_file()

        self.api_key = settings.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self.temperature = settings.get("temperature")
        self.max_tokens = int(settings.get("max_tokens", 4096))
        self.timeout = float(settings.get("timeout", 120.0))
        self.thinking_level = settings.get("thinking_level") or settings.get("effort")
        self.system_prompt = settings.get("system_prompt")
        self.anthropic_version = settings.get("anthropic_version", "2023-06-01")
        self.active_conversations: Dict[str, Dict[str, Any]] = {}

    def start_conversation(self, scenario_id: str) -> str:
        """Initializes a new multi-turn conversation session."""
        conv_id = f"anthropic-{scenario_id}-{uuid.uuid4().hex[:8]}"
        self.active_conversations[conv_id] = {
            "scenario_id": scenario_id,
            "turns": [],
        }
        return conv_id

    def _build_anthropic_messages(
        self,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> List[Dict[str, Any]]:
        """Constructs multi-turn messages payload for Anthropic API."""
        messages: List[Dict[str, Any]] = []

        # Process previous history
        for msg in history:
            role = "user" if msg.role == "student" else "assistant"
            content_blocks: List[Dict[str, Any]] = []

            if msg.image_path and Path(msg.image_path).is_file():
                content_blocks.append(encode_image_for_anthropic(msg.image_path))

            content_blocks.append({"type": "text", "text": msg.content})
            messages.append({"role": role, "content": content_blocks})

        # Process current student turn
        current_blocks: List[Dict[str, Any]] = []
        if image_path and Path(image_path).is_file():
            current_blocks.append(encode_image_for_anthropic(image_path))

        current_blocks.append({"type": "text", "text": student_message})
        messages.append({"role": "user", "content": current_blocks})

        return messages

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        """Sends student turn to Anthropic /v1/messages endpoint."""
        if not self.api_key:
            raise ValueError(
                "Anthropic API Key not found. Please set ANTHROPIC_API_KEY in your .env or environment."
            )

        messages = self._build_anthropic_messages(student_message, image_path, history)
        endpoint = f"{self.API_BASE}/messages"

        payload: Dict[str, Any] = {
            "model": self.model_identifier,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }

        # Temperature (Anthropic recommends omitting temperature if adaptive thinking is enabled)
        if self.temperature is not None and not self.thinking_level:
            payload["temperature"] = float(self.temperature)

        if self.thinking_level:
            payload["output_config"] = {"effort": self.thinking_level}

        if self.system_prompt:
            payload["system"] = self.system_prompt

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=endpoint,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": self.anthropic_version,
            },
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

                # Extract text and thinking blocks from content
                reply_parts: List[str] = []
                thinking_tokens = 0
                for block in result.get("content", []):
                    if block.get("type") == "text":
                        reply_parts.append(block.get("text", ""))

                reply_text = "".join(reply_parts)

                usage = result.get("usage", {})
                token_usage = {
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                }

                if conversation_id in self.active_conversations:
                    self.active_conversations[conversation_id]["turns"].append(turn_id)

                return ProviderResponse(
                    content=reply_text,
                    token_usage=token_usage,
                    latency_ms=round(latency_ms, 2),
                    model_identifier=self.model_identifier,
                    raw_metadata={
                        "stop_reason": result.get("stop_reason"),
                        "id": result.get("id"),
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

                # Retry on rate limits (429) or temporary server errors (529, 500, 503)
                if http_err.code in (429, 500, 503, 529) and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if http_err.code in (401, 403):
                    raise PermissionError(
                        f"Anthropic API Authentication Error ({http_err.code}): {error_body}"
                    ) from http_err

                raise RuntimeError(
                    f"Anthropic API HTTP {http_err.code} ({http_err.reason}): {error_body}"
                ) from http_err

            except (TimeoutError, urllib.error.URLError) as net_err:
                is_timeout = isinstance(net_err, TimeoutError) or "timed out" in str(net_err).lower()
                if is_timeout and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if isinstance(net_err, urllib.error.URLError):
                    raise ConnectionError(
                        f"Failed to connect to Anthropic API: {net_err.reason}"
                    ) from net_err
                raise

    def close_conversation(self, conversation_id: str) -> None:
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
