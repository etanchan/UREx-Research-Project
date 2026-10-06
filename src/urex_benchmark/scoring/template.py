"""Generates human-scoring sheets from raw model run outputs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


CRITERIA_COLUMNS = [
    "technical_correctness",     # 1-5 Likert scale
    "diagram_grounding",         # 1-5 Likert scale
    "misconception_handling",    # 1-5 Likert scale
    "relevance",                 # 1-5 Likert scale
    "appropriate_uncertainty",   # 1-5 Likert scale
    "evaluator_notes",           # Free text
]

CSV_HEADER = [
    "model_id",
    "scenario_id",
    "turn_id",
    "student_message",
    "attached_image_path",
    "model_response",
    "expected_answer_reference",
    *CRITERIA_COLUMNS,
]


def load_answer_key(keys_dir: Optional[Path | str], scenario_id: str) -> Dict[int, str]:
    if not keys_dir:
        return {}
    keys_path = Path(keys_dir)
    key_file = keys_path / f"{scenario_id}.json"
    if not key_file.exists():
        return {}
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            int(t["turn_id"]): str(t.get("expected_answer", ""))
            for t in data.get("turns", [])
        }
    except Exception:
        return {}


def generate_scoring_rows(
    run_dir: Path | str,
    keys_dir: Optional[Path | str] = None,
) -> List[Dict[str, Any]]:
    run_path = Path(run_dir)
    scenario_run_files = sorted(run_path.glob("*.json"))

    rows: List[Dict[str, Any]] = []

    for srf in scenario_run_files:
        if srf.name == "manifest.json":
            continue

        with open(srf, "r", encoding="utf-8") as f:
            run_data = json.load(f)

        scenario_id = run_data.get("scenario_id", srf.stem)
        model_id = run_data.get("model_identifier", "unknown_model")
        answer_key_turns = load_answer_key(keys_dir, scenario_id)

        turns = run_data.get("turns", [])
        for t in turns:
            turn_id = int(t.get("turn_id", 0))
            expected_ref = answer_key_turns.get(turn_id, "")
            row = {
                "model_id": model_id,
                "scenario_id": scenario_id,
                "turn_id": turn_id,
                "student_message": t.get("student_message", ""),
                "attached_image_path": t.get("attached_image_path", "") or "",
                "model_response": t.get("model_response", "") or "",
                "expected_answer_reference": expected_ref,
                "technical_correctness": "",
                "diagram_grounding": "",
                "misconception_handling": "",
                "relevance": "",
                "appropriate_uncertainty": "",
                "evaluator_notes": "",
            }
            rows.append(row)

    return rows


def export_template(
    run_dir: Path | str,
    output_file: Path | str,
    keys_dir: Optional[Path | str] = None,
) -> None:
    rows = generate_scoring_rows(run_dir, keys_dir=keys_dir)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.suffix.lower() == ".json":
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
    else:
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

    print(f"Exported human scoring template with {len(rows)} turn rows to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export human-scoring template from model run results.")
    parser.add_argument(
        "--run-dir",
        type=str,
        required=True,
        help="Path to raw model run results directory",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="scores/scoring_sheet.csv",
        help="Path to output CSV or JSON scoring sheet",
    )
    parser.add_argument(
        "--keys-dir",
        type=str,
        default=None,
        help="Optional path to private answer keys directory to embed reference answer for human rater",
    )

    args = parser.parse_args()
    export_template(
        run_dir=args.run_dir,
        output_file=args.output_file,
        keys_dir=args.keys_dir,
    )


if __name__ == "__main__":
    main()
