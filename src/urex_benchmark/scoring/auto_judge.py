"""Automated LLM-as-a-Judge evaluator that reads and writes directly to scoring CSV files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from urex_benchmark.models import ModelMessage
from urex_benchmark.providers.anthropic import AnthropicProvider
from urex_benchmark.providers.base import BaseProvider
from urex_benchmark.providers.gemini import GeminiProvider
from urex_benchmark.providers.mock import MockProvider
from urex_benchmark.providers.openai import OpenAIProvider
from urex_benchmark.providers.soclaas import SoCLaaSProvider
from urex_benchmark.scoring.template import CSV_HEADER


JUDGE_SYSTEM_PROMPT = """You are an expert engineering professor grading a Vision-Language Model (VLM) teaching assistant on the UREx Engineering Diagrams Benchmark.
You will be given:
1. The engineering diagram shown to the student and model.
2. Any prior conversation turns (for context).
3. The current Turn's Student Question.
4. The Private Ground-Truth Expected Answer Reference.
5. The Model's Response to evaluate.

Rate the Model's Response strictly on a 0, 1, or 2 integer scale across three rubric dimensions:
- technical_correctness (0, 1, or 2):
  * 0 = Incorrect core concept, wrong final answer, or major factual error.
  * 1 = Partially correct; right general idea but has a minor calculation slip or omits part of the expected answer.
  * 2 = Fully accurate across all technical parts compared to the expected answer reference.
- diagram_grounding (0, 1, or 2):
  * 0 = Ignores or contradicts the diagram, or hallucinates unseen values/labels not present in the diagram.
  * 1 = Mostly grounded in the diagram, with minor unstated assumptions or vague visual references.
  * 2 = Explicitly and faithfully grounded in the visual elements of the diagram (and adapts properly if a revised Turn 4 diagram is provided).
- pedagogical_clarity (0, 1, or 2):
  * 0 = Sycophantic (agrees with a false student premise) or off-topic/confusing.
  * 1 = Addresses the question weakly, or is overly verbose/convoluted.
  * 2 = Directly answers the student's question and clearly corrects any student misconceptions.

Respond ONLY with a valid JSON object matching this exact schema (no markdown formatting outside the JSON):
{
  "technical_correctness": 2,
  "diagram_grounding": 2,
  "pedagogical_clarity": 2,
  "evaluator_notes": "Concise 1-2 sentence justification explaining the scores and noting any missed points or strengths."
}"""


def create_judge_provider(
    provider_name: str = "gemini",
    model_id: Optional[str] = None,
    temperature: float = 0.0,
    thinking_level: Optional[str] = None,
) -> BaseProvider:
    """Instantiates a provider configured for rubric evaluation."""
    if provider_name == "mock":
        return MockProvider(model_identifier=model_id or "mock-judge-v1")
    elif provider_name == "gemini":
        settings: Dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": 2048,
            "system_prompt": JUDGE_SYSTEM_PROMPT,
        }
        if thinking_level:
            settings["thinking_level"] = thinking_level
        return GeminiProvider(
            model_identifier=model_id or "gemini-3.1-pro-preview",
            **settings,
        )
    elif provider_name == "openai":
        settings = {
            "temperature": temperature,
            "max_tokens": 2048,
            "system_prompt": JUDGE_SYSTEM_PROMPT,
        }
        if thinking_level:
            settings["reasoning_effort"] = thinking_level
        return OpenAIProvider(
            model_identifier=model_id or "gpt-4o",
            **settings,
        )
    elif provider_name == "anthropic":
        settings = {
            "temperature": temperature,
            "max_tokens": 2048,
            "system_prompt": JUDGE_SYSTEM_PROMPT,
        }
        if thinking_level:
            settings["thinking_level"] = thinking_level
        return AnthropicProvider(
            model_identifier=model_id or "claude-3-5-sonnet-latest",
            **settings,
        )
    elif provider_name == "soclaas":
        return SoCLaaSProvider(
            model_identifier=model_id or "default",
            temperature=temperature,
            max_tokens=2048,
        )
    else:
        raise ValueError(f"Unsupported judge provider: {provider_name}")


def load_scenario_metadata(scenarios_dir: Path | str) -> Dict[str, Dict[str, Any]]:
    """Loads scenario JSON definitions to resolve active diagrams per turn."""
    sc_dir = Path(scenarios_dir)
    scenarios: Dict[str, Dict[str, Any]] = {}
    if not sc_dir.exists():
        return scenarios
    for p in sorted(sc_dir.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            sc_id = data.get("scenario_id", p.stem)
            scenarios[sc_id] = data
        except Exception:
            continue
    return scenarios


def resolve_active_image_for_turn(
    scenario_meta: Optional[Dict[str, Any]],
    turn_id: int,
    row_attached_image: str,
) -> Optional[str]:
    """Determines which diagram image is active at a given turn."""
    if row_attached_image and Path(row_attached_image).is_file():
        return row_attached_image

    if not scenario_meta:
        return None

    active_img = scenario_meta.get("initial_image_path")
    for t in scenario_meta.get("turns", []):
        t_id = int(t.get("turn_id", 0))
        if t_id <= turn_id and t.get("revised_image_path"):
            active_img = t.get("revised_image_path")
    if active_img and Path(active_img).is_file():
        return active_img
    return None


def parse_judge_json(raw_text: str) -> Dict[str, Any]:
    """Extracts and validates the JSON object from the judge's response."""
    cleaned = raw_text.strip()
    # Strip markdown code fences if present
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(1)

    parsed = json.loads(cleaned)

    def clamp_score(val: Any) -> int:
        try:
            v = int(round(float(val)))
            return max(0, min(2, v))
        except Exception:
            return 1

    return {
        "technical_correctness": clamp_score(parsed.get("technical_correctness", 1)),
        "diagram_grounding": clamp_score(parsed.get("diagram_grounding", 1)),
        "pedagogical_clarity": clamp_score(parsed.get("pedagogical_clarity", 1)),
        "evaluator_notes": str(parsed.get("evaluator_notes", "")).strip(),
    }


def judge_single_turn(
    provider: BaseProvider,
    row: Dict[str, Any],
    prior_rows: List[Dict[str, Any]],
    active_image_path: Optional[str],
) -> Dict[str, Any]:
    """Evaluates a single CSV row using the given judge provider."""
    if isinstance(provider, MockProvider):
        return {
            "technical_correctness": 2,
            "diagram_grounding": 2,
            "pedagogical_clarity": 2,
            "evaluator_notes": "[AI Judge: mock] Accurate explanation grounded in the diagram.",
        }

    scenario_id = row.get("scenario_id", "unknown")
    turn_id = int(row.get("turn_id", 1))
    student_msg = row.get("student_message", "")
    expected_ref = row.get("expected_answer_reference", "")
    model_resp = row.get("model_response", "")

    history_lines: List[str] = []
    for pr in prior_rows:
        p_turn = pr.get("turn_id")
        p_q = pr.get("student_message", "")
        p_a = pr.get("model_response", "")
        # Keep prior model responses concise so context stays focused on current turn
        if len(p_a) > 800:
            p_a = p_a[:800] + "... [truncated]"
        history_lines.append(f"Turn {p_turn} Student: {p_q}\nTurn {p_turn} Model: {p_a}")

    history_block = "\n\n".join(history_lines) if history_lines else "None (This is Turn 1)."

    prompt = (
        f"{JUDGE_SYSTEM_PROMPT}\n\n"
        f"=== SCENARIO: {scenario_id} | TURN {turn_id} of 5 ===\n\n"
        f"--- PRIOR CONVERSATION CONTEXT ---\n{history_block}\n\n"
        f"--- CURRENT TURN {turn_id} STUDENT QUESTION ---\n{student_msg}\n\n"
        f"--- PRIVATE EXPECTED ANSWER REFERENCE (GROUND TRUTH) ---\n{expected_ref}\n\n"
        f"--- MODEL RESPONSE TO GRADE ---\n{model_resp}\n\n"
        f"Return ONLY the JSON evaluation object with integer scores (0, 1, or 2) for "
        f"technical_correctness, diagram_grounding, pedagogical_clarity, and a concise evaluator_notes string."
    )

    conv_id = provider.start_conversation(f"judge_{scenario_id}_t{turn_id}")
    try:
        resp = provider.send_turn(
            conversation_id=conv_id,
            turn_id=1,
            student_message=prompt,
            image_path=active_image_path,
            history=[],
        )
        result = parse_judge_json(resp.content)
        note = result["evaluator_notes"]
        prefix = f"[AI Judge: {provider.model_identifier}] "
        if not note.startswith("[AI Judge"):
            result["evaluator_notes"] = prefix + note
        return result
    finally:
        provider.close_conversation(conv_id)


def read_csv_rows(csv_path: Path) -> Tuple[List[str], List[Dict[str, Any]]]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or CSV_HEADER)
        rows = list(reader)
    return fieldnames, rows


def write_csv_rows(csv_path: Path, fieldnames: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def auto_grade_csv(
    csv_file: Path | str,
    provider: BaseProvider,
    scenarios_dir: Path | str = "data/scenarios",
    scenario_filter: Optional[str] = None,
    turn_filter: Optional[int] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Grades rows in a scoring CSV file and writes results directly back to the CSV."""
    csv_path = Path(csv_file)
    if not csv_path.exists():
        raise FileNotFoundError(f"Scoring CSV not found: {csv_path}")

    fieldnames, rows = read_csv_rows(csv_path)
    scenarios_meta = load_scenario_metadata(scenarios_dir)

    graded_count = 0
    skipped_count = 0
    errors: List[str] = []

    for idx, row in enumerate(rows):
        sc_id = row.get("scenario_id", "")
        t_id = int(row.get("turn_id", 0))

        if scenario_filter and sc_id != scenario_filter:
            continue
        if turn_filter is not None and t_id != turn_filter:
            continue

        already_filled = all(
            str(row.get(c, "")).strip() != ""
            for c in ("technical_correctness", "diagram_grounding", "pedagogical_clarity")
        )
        if already_filled and not overwrite:
            skipped_count += 1
            continue

        prior_rows = [
            r for r in rows
            if r.get("scenario_id") == sc_id and int(r.get("turn_id", 0)) < t_id
        ]
        active_img = resolve_active_image_for_turn(
            scenarios_meta.get(sc_id),
            t_id,
            row.get("attached_image_path", ""),
        )

        try:
            eval_res = judge_single_turn(
                provider=provider,
                row=row,
                prior_rows=prior_rows,
                active_image_path=active_img,
            )
            row["technical_correctness"] = str(eval_res["technical_correctness"])
            row["diagram_grounding"] = str(eval_res["diagram_grounding"])
            row["pedagogical_clarity"] = str(eval_res["pedagogical_clarity"])
            row["evaluator_notes"] = eval_res["evaluator_notes"]
            graded_count += 1

            # Flush immediately back to CSV so Excel / Studio sees live progress
            write_csv_rows(csv_path, fieldnames, rows)
            print(
                f"  [Graded] {sc_id} Turn {t_id} -> "
                f"TC={row['technical_correctness']}, DG={row['diagram_grounding']}, PC={row['pedagogical_clarity']}"
            )
        except Exception as exc:
            err_msg = f"{sc_id} Turn {t_id}: {exc}"
            errors.append(err_msg)
            print(f"  [Error] {err_msg}")

    return {
        "csv_file": str(csv_path),
        "graded": graded_count,
        "skipped": skipped_count,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Auto-Judge: Grade scoring CSV sheets directly using an LLM judge."
    )
    parser.add_argument(
        "--scores-file",
        type=str,
        required=True,
        help="Path to the scoring CSV file in scores/ to fill in-place",
    )
    parser.add_argument(
        "--scenarios-dir",
        type=str,
        default="data/scenarios",
        help="Path to scenarios directory (to resolve diagram images on turns 2, 3, 5)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["gemini", "openai", "anthropic", "soclaas", "mock"],
        default="gemini",
        help="Judge provider to use (default: gemini)",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default="gemini-2.5-flash",
        help="Judge model ID (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--scenario-id",
        type=str,
        default=None,
        help="Optional: grade only a specific scenario_id",
    )
    parser.add_argument(
        "--turn-id",
        type=int,
        default=None,
        help="Optional: grade only a specific turn_id (1-5)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite rows that already have scores filled in",
    )

    args = parser.parse_args()
    provider = create_judge_provider(
        provider_name=args.provider,
        model_id=args.model_id,
    )
    print(f"Starting AI Auto-Judge on {args.scores_file} using {args.provider} ({provider.model_identifier})...")
    res = auto_grade_csv(
        csv_file=args.scores_file,
        provider=provider,
        scenarios_dir=args.scenarios_dir,
        scenario_filter=args.scenario_id,
        turn_filter=args.turn_id,
        overwrite=args.overwrite,
    )
    print(
        f"Done! Graded {res['graded']} turn(s), skipped {res['skipped']} already-graded turn(s), "
        f"errors: {len(res['errors'])}."
    )


if __name__ == "__main__":
    main()
