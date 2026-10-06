"""Deterministic Mock Provider for local testing and validation without API keys."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
import uuid

from urex_benchmark.models import ModelMessage
from urex_benchmark.providers.base import BaseProvider, ProviderResponse


class MockProvider(BaseProvider):
    """Mock vision-language model provider that simulates multi-turn conversations."""

    def __init__(self, model_identifier: str = "mock-vlm-v1", **settings: Any):
        super().__init__(model_identifier, **settings)
        self.active_conversations: Dict[str, Dict[str, Any]] = {}
        # Support injecting simulated errors for testing resilience
        self.fail_scenario: Optional[str] = settings.get("fail_scenario")
        self.fail_turn: Optional[int] = settings.get("fail_turn")

    def start_conversation(self, scenario_id: str) -> str:
        conv_id = f"mock-session-{scenario_id}-{uuid.uuid4().hex[:8]}"
        self.active_conversations[conv_id] = {
            "scenario_id": scenario_id,
            "turns_received": [],
            "images_received": [],
        }
        return conv_id

    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        t0 = time.perf_counter()

        if conversation_id not in self.active_conversations:
            raise RuntimeError(f"Unknown conversation_id: {conversation_id}")

        session = self.active_conversations[conversation_id]
        scenario_id = session["scenario_id"]

        # Check for simulated failures
        if self.fail_scenario == scenario_id and self.fail_turn == turn_id:
            raise ConnectionError(f"Simulated network/provider error at turn {turn_id} for {scenario_id}")

        session["turns_received"].append(turn_id)
        if image_path:
            session["images_received"].append((turn_id, image_path))

        # Build mock response acknowledging turn context and history length
        prior_turns_count = len([m for m in history if m.role == "student"])
        response_parts = []

        if turn_id == 1:
            response_parts.append(
                f"[Mock Assistant] Analyzing initial diagram '{image_path}'. "
                f"Regarding your first question: '{student_message[:50]}...': "
                f"The diagram illustrates the core components and signal flow for {scenario_id}."
            )
        else:
            if image_path:
                response_parts.append(
                    f"[Mock Assistant] Acknowledged revised diagram update '{image_path}' at turn {turn_id}. "
                )
            response_parts.append(
                f"[Mock Assistant] Building upon our previous {prior_turns_count} conversation turn(s). "
                f"Regarding: '{student_message[:50]}...': "
                f"Tracing the signals based on our earlier discussion confirms the expected behavior."
            )

        content = " ".join(response_parts)
        latency_ms = (time.perf_counter() - t0) * 1000.0 + 15.0  # slight simulated latency

        # Calculate simulated tokens
        prompt_chars = len(student_message) + sum(len(m.content) for m in history) + (500 if image_path else 0)
        prompt_tokens = max(10, prompt_chars // 4)
        completion_tokens = max(10, len(content) // 4)

        return ProviderResponse(
            content=content,
            token_usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            latency_ms=round(latency_ms, 2),
            model_identifier=self.model_identifier,
            raw_metadata={"simulated": True, "turn_id": turn_id},
        )

    def close_conversation(self, conversation_id: str) -> None:
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
