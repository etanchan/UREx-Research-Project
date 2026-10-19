"""OpenAI Provider for UREx benchmark."""

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
from urex_benchmark.providers.soclaas import _load_env_file, encode_image_to_data_url


class OpenAIProvider(BaseProvider):
    """Vision-Language Model provider connecting to OpenAI API."""

    API_BASE = "https://api.openai.com/v1"

    def __init__(self, model_identifier: str = "gpt-6.1-sol", **settings: Any):
        super().__init__(model_identifier, **settings)

        _load_env_file()

        self.api_key = settings.get("api_key") or os.environ.get("OPENAI_API_KEY")
        self.temperature = settings.get("temperature")
        self.max_tokens = int(settings.get("max_tokens", 2048))
        self.timeout = float(settings.get("timeout", 120.0))
        self.reasoning_effort = settings.get("reasoning_effort") or settings.get("thinking_level")
        self.system_prompt = settings.get("system_prompt")
        self.active_conversations: Dict[str, Dict[str, Any]] = {}

    def start_conversation(self, scenario_id: str) -> str:
        """Initializes a new multi-turn conversation session."""
        conv_id = f"openai-{scenario_id}-{uuid.uuid4().hex[:8]}"
        self.active_conversations[conv_id] = {
            "scenario_id": scenario_id,
            "turns": [],
        }
        return conv_id

    def _build_openai_messages(
        self,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> List[Dict[str, Any]]:
        """Constructs multi-turn messages payload for OpenAI Chat Completions API."""
        messages: List[Dict[str, Any]] = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Process previous history
        for msg in history:
            role = "user" if msg.role == "student" else "assistant"
            if role == "assistant":
                messages.append({"role": role, "content": msg.content})
            else:
                parts: List[Dict[str, Any]] = []
                if msg.image_path and Path(msg.image_path).is_file():
                    data_url = encode_image_to_data_url(msg.image_path)
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    })
                parts.append({"type": "text", "text": msg.content})
                messages.append({"role": role, "content": parts})

        # Process current student turn
        current_parts: List[Dict[str, Any]] = []
        if image_path and Path(image_path).is_file():
            data_url = encode_image_to_data_url(image_path)
            current_parts.append({
                "type": "image_url",
                "image_url": {"url": data_url, "detail": "high"},
            })

        current_parts.append({"type": "text", "text": student_message})
        messages.append({"role": "user", "content": current_parts})

        return messages

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        """Sends student turn to OpenAI /v1/chat/completions endpoint."""
        if not self.api_key:
            raise ValueError(
                "OpenAI API Key not found. Please set OPENAI_API_KEY in your .env or environment."
            )

        messages = self._build_openai_messages(student_message, image_path, history)
        endpoint = f"{self.API_BASE}/chat/completions"

        payload: Dict[str, Any] = {
            "model": self.model_identifier,
            "messages": messages,
            "max_completion_tokens": self.max_tokens,
        }

        # Temperature (only set if specified and not reasoning model enforcing default)
        if self.temperature is not None:
            payload["temperature"] = float(self.temperature)

        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=endpoint,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
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

                choices = result.get("choices", [])
                if not choices:
                    raise RuntimeError(f"OpenAI returned no choices: {result}")

                reply_text = choices[0].get("message", {}).get("content", "")

                usage = result.get("usage", {})
                completion_tokens_details = usage.get("completion_tokens_details", {})
                reasoning_tokens = completion_tokens_details.get("reasoning_tokens", 0)

                token_usage = {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "reasoning_tokens": reasoning_tokens,
                }

                if conversation_id in self.active_conversations:
                    self.active_conversations[conversation_id]["turns"].append(turn_id)

                return ProviderResponse(
                    content=reply_text,
                    token_usage=token_usage,
                    latency_ms=round(latency_ms, 2),
                    model_identifier=self.model_identifier,
                    raw_metadata={
                        "finish_reason": choices[0].get("finish_reason"),
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

                # Retry on rate limits (429) or transient server errors (500, 502, 503)
                if http_err.code in (429, 500, 502, 503) and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if http_err.code == 401:
                    raise PermissionError(
                        f"OpenAI API Authentication Error (401): {error_body}"
                    ) from http_err

                raise RuntimeError(
                    f"OpenAI API HTTP {http_err.code} ({http_err.reason}): {error_body}"
                ) from http_err

            except (TimeoutError, urllib.error.URLError) as net_err:
                is_timeout = isinstance(net_err, TimeoutError) or "timed out" in str(net_err).lower()
                if is_timeout and attempt < max_retries:
                    time.sleep(backoff_delay)
                    backoff_delay *= 2
                    continue

                if isinstance(net_err, urllib.error.URLError):
                    raise ConnectionError(
                        f"Failed to connect to OpenAI API: {net_err.reason}"
                    ) from net_err
                raise

    def close_conversation(self, conversation_id: str) -> None:
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
