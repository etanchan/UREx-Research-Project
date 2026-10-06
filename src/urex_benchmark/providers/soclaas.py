"""NUS SoCLaaS (School of Computing LLM-as-a-Service) Provider for UREx benchmark."""

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


def _load_env_file(dotenv_path: Optional[Path] = None) -> None:
    """Lightweight environment loader checking .env, repository root, and ~/.zshrc."""
    candidates = []
    if dotenv_path:
        candidates.append(dotenv_path)
    else:
        cwd = Path.cwd()
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        candidates.extend([cwd / ".env", repo_root / ".env", cwd.parent / ".env"])

    for candidate in candidates:
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("\"'")
                        if key and key not in os.environ:
                            os.environ[key] = val
                break
            except Exception:
                pass

    # If SOCLAAS_API_KEY is not in os.environ, attempt loading directly from ~/.zshrc
    if "SOCLAAS_API_KEY" not in os.environ:
        zshrc = Path.home() / ".zshrc"
        if zshrc.is_file():
            try:
                import re
                text = zshrc.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r'^\s*export\s+SOCLAAS_API_KEY=["\']?([^"\'\s#]+)["\']?', text, re.M)
                if match:
                    val = match.group(1).strip()
                    if val and "<" not in val:  # ignore placeholder
                        os.environ["SOCLAAS_API_KEY"] = val
                match_url = re.search(r'^\s*export\s+SOCLAAS_BASE_URL=["\']?([^"\'\s#]+)["\']?', text, re.M)
                if match_url and "SOCLAAS_BASE_URL" not in os.environ:
                    val_url = match_url.group(1).strip()
                    if val_url and "<" not in val_url:
                        os.environ["SOCLAAS_BASE_URL"] = val_url
            except Exception:
                pass


def encode_image_to_data_url(image_path: str | Path) -> str:
    """Reads an image file from disk and encodes it into a base64 data URL."""
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Diagram image not found at path: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(p))
    if not mime_type:
        mime_type = "image/png"

    with open(p, "rb") as img_file:
        raw_bytes = img_file.read()

    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64_str}"


class SoCLaaSProvider(BaseProvider):
    """Vision-Language Model provider connecting to NUS SoCLaaS OpenAI-compatible API."""

    DEFAULT_BASE_URL = "https://soclaas-api.comp.nus.edu.sg/v1"

    def __init__(self, model_identifier: str, **settings: Any):
        super().__init__(model_identifier, **settings)

        # Attempt reading .env and shell config if needed
        _load_env_file()

        # Resolve credentials and endpoint (must be SoCLaaS-specific key, not OpenAI key)
        self.api_key = settings.get("api_key") or os.environ.get("SOCLAAS_API_KEY")
        self.base_url = (
            settings.get("base_url")
            or os.environ.get("SOCLAAS_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")

        self.temperature = float(settings.get("temperature", 0.2))
        self.max_tokens = int(settings.get("max_tokens", 2048))
        self.timeout = float(settings.get("timeout", 60.0))
        self.system_prompt = settings.get("system_prompt")
        self.active_conversations: Dict[str, Dict[str, Any]] = {}

    def start_conversation(self, scenario_id: str) -> str:
        """Initializes a new multi-turn scenario conversation session."""
        conv_id = f"soclaas-{scenario_id}-{uuid.uuid4().hex[:8]}"
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
        """Transforms conversation history and current turn into OpenAI multimodal message payload."""
        messages: List[Dict[str, Any]] = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # Process past history
        for msg in history:
            role = "user" if msg.role == "student" else msg.role
            if msg.image_path and Path(msg.image_path).is_file():
                data_url = encode_image_to_data_url(msg.image_path)
                messages.append({
                    "role": role,
                    "content": [
                        {"type": "text", "text": msg.content},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                })
            else:
                messages.append({"role": role, "content": msg.content})

        # Process current turn
        if image_path:
            data_url = encode_image_to_data_url(image_path)
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": student_message},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            })
        else:
            messages.append({"role": "user", "content": student_message})

        return messages

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        """Sends student turn with optional diagram to SoCLaaS /v1/chat/completions."""
        if not self.api_key:
            raise ValueError(
                "SoCLaaS API Key not found. Please set SOCLAAS_API_KEY in your environment, "
                ".env file, or pass api_key in settings."
            )

        messages = self._build_openai_messages(student_message, image_path, history)

        payload = {
            "model": self.model_identifier,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        req_data = json.dumps(payload).encode("utf-8")
        api_endpoint = f"{self.base_url}/chat/completions"

        req = urllib.request.Request(
            url=api_endpoint,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "UREx-Benchmark/1.0",
            },
            method="POST",
        )

        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                latency_ms = (time.perf_counter() - t0) * 1000.0

            result = json.loads(resp_bytes.decode("utf-8"))

            choices = result.get("choices", [])
            if not choices:
                raise RuntimeError(f"SoCLaaS returned empty choices in response: {result}")

            reply_content = choices[0].get("message", {}).get("content", "")
            usage = result.get("usage", {})

            token_usage = {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            }

            if conversation_id in self.active_conversations:
                self.active_conversations[conversation_id]["turns"].append(turn_id)

            return ProviderResponse(
                content=reply_content,
                token_usage=token_usage,
                latency_ms=round(latency_ms, 2),
                model_identifier=self.model_identifier,
                raw_metadata={
                    "model": result.get("model", self.model_identifier),
                    "finish_reason": choices[0].get("finish_reason"),
                },
            )

        except urllib.error.HTTPError as http_err:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            error_body = ""
            try:
                error_body = http_err.read().decode("utf-8")
                parsed_err = json.loads(error_body)
                error_body = parsed_err.get("error", {}).get("message", error_body)
            except Exception:
                pass

            if http_err.code == 400 and ("image" in error_body.lower() or "vision" in error_body.lower()):
                raise RuntimeError(
                    f"SoCLaaS HTTP 400 Bad Request: Model '{self.model_identifier}' rejected image input. "
                    f"Ensure you are targeting a multimodal/VLM model on SoCLaaS. Server details: {error_body}"
                ) from http_err

            if http_err.code == 401:
                raise PermissionError(
                    f"SoCLaaS HTTP 401 Unauthorized: Invalid or expired SOCLAAS_API_KEY. Server details: {error_body}"
                ) from http_err

            raise RuntimeError(
                f"SoCLaaS API HTTP Error {http_err.code}: {http_err.reason}. Server details: {error_body}"
            ) from http_err

        except urllib.error.URLError as url_err:
            raise ConnectionError(
                f"Failed to connect to SoCLaaS at {self.base_url} ({url_err.reason}). "
                "If accessing from outside NUS campus, please ensure NUS VPN is active."
            ) from url_err

    def close_conversation(self, conversation_id: str) -> None:
        """Cleans up session tracking for completed or terminated conversations."""
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
