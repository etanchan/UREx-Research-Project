"""Base interface for model providers in UREx Engineering Diagrams benchmark."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from urex_benchmark.models import ModelMessage


@dataclass
class ProviderResponse:
    """Standardized response from any VLM provider."""
    content: str
    token_usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    model_identifier: str = ""
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for vision-language model providers."""

    def __init__(self, model_identifier: str, **settings: Any):
        self.model_identifier = model_identifier
        self.settings = settings

    @abstractmethod
    def start_conversation(self, scenario_id: str) -> str:
        """Initialize a fresh conversation session for a scenario.
        Returns a unique conversation_id.
        """
        pass

    @abstractmethod
    def send_turn(
        self,
        conversation_id: str,
        turn_id: int,
        student_message: str,
        image_path: Optional[str],
        history: List[ModelMessage],
    ) -> ProviderResponse:
        """Send a student turn to the provider.

        Args:
            conversation_id: Unique session ID for the scenario run.
            turn_id: 1-indexed turn number (1 to 5).
            student_message: The fixed student question or follow-up prompt.
            image_path: Path to diagram image (initial diagram on turn 1,
                        or revised diagram on turn with image revision).
                        None if no new image is attached on this turn.
            history: Ordered list of prior student and model messages in this conversation.

        Returns:
            ProviderResponse containing model reply text, token usage, and latency.
        """
        pass

    def close_conversation(self, conversation_id: str) -> None:
        """Optional hook to clean up session state."""
        pass
