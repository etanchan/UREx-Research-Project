"""Data models for UREx Engineering Diagrams benchmark."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional


@dataclass
class Turn:
    """Represents a single student turn in a scenario."""
    turn_id: int
    student_message: str
    revised_image_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Turn:
        return cls(
            turn_id=int(data["turn_id"]),
            student_message=str(data["student_message"]),
            revised_image_path=data.get("revised_image_path"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Scenario:
    """Represents a 5-turn multi-turn benchmark scenario."""
    scenario_id: str
    course: str
    title: str
    status: Literal["draft", "ready"]
    initial_image_path: str
    turns: List[Turn]
    source_reference: Optional[str] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "course": self.course,
            "title": self.title,
            "status": self.status,
            "initial_image_path": self.initial_image_path,
            "source_reference": self.source_reference,
            "notes": self.notes,
            "metadata": self.metadata,
            "turns": [turn.to_dict() for turn in self.turns],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Scenario:
        turns = [Turn.from_dict(t) for t in data.get("turns", [])]
        return cls(
            scenario_id=str(data["scenario_id"]),
            course=str(data.get("course", "Unknown")),
            title=str(data.get("title", "")),
            status=str(data.get("status", "draft")),  # type: ignore
            initial_image_path=str(data.get("initial_image_path", "")),
            turns=turns,
            source_reference=data.get("source_reference"),
            notes=data.get("notes"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json_file(cls, path: Path | str) -> Scenario:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_json_file(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


@dataclass
class AnswerKeyTurn:
    """Researcher expected answer and grading points for one turn."""
    turn_id: int
    expected_answer: str
    key_points: List[str] = field(default_factory=list)
    common_misconceptions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AnswerKeyTurn:
        return cls(
            turn_id=int(data["turn_id"]),
            expected_answer=str(data.get("expected_answer", "")),
            key_points=list(data.get("key_points", [])),
            common_misconceptions=list(data.get("common_misconceptions", [])),
        )


@dataclass
class AnswerKey:
    """Private expected answers for an entire scenario."""
    scenario_id: str
    turns: List[AnswerKeyTurn]
    course: Optional[str] = None
    title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "course": self.course,
            "title": self.title,
            "turns": [t.to_dict() for t in self.turns],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AnswerKey:
        turns = [AnswerKeyTurn.from_dict(t) for t in data.get("turns", [])]
        return cls(
            scenario_id=str(data["scenario_id"]),
            turns=turns,
            course=data.get("course"),
            title=data.get("title"),
        )

    @classmethod
    def from_json_file(cls, path: Path | str) -> AnswerKey:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def to_json_file(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


@dataclass
class ModelMessage:
    """One message in conversation history sent or received."""
    role: Literal["student", "assistant", "system"]
    content: str
    image_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TurnResult:
    """Saved execution record for a single turn."""
    turn_id: int
    student_message: str
    attached_image_path: Optional[str]
    model_response: Optional[str]
    token_usage: Dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScenarioRunResult:
    """Aggregated output for a scenario run, updated after every turn."""
    scenario_id: str
    model_identifier: str
    status: Literal["in_progress", "completed", "failed"]
    turns: List[TurnResult] = field(default_factory=list)
    dataset_version: str = "1.0.0"
    model_settings: Dict[str, Any] = field(default_factory=dict)
    start_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    end_time: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "model_identifier": self.model_identifier,
            "status": self.status,
            "dataset_version": self.dataset_version,
            "model_settings": self.model_settings,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
            "turns": [t.to_dict() for t in self.turns],
        }

    def save_to_file(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        temp_path.replace(path)
