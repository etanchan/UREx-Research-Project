"""Validator for UREx Engineering Diagrams benchmark scenarios and answer keys."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple

from urex_benchmark.models import AnswerKey, Scenario


@dataclass
class ValidationIssue:
    level: str  # "ERROR", "WARNING", "INFO"
    scenario_id: str
    message: str


@dataclass
class ValidationReport:
    total_scenarios: int = 0
    ready_count: int = 0
    draft_count: int = 0
    passed_ready_count: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.level == "ERROR" for issue in self.issues)

    def add_error(self, scenario_id: str, msg: str) -> None:
        self.issues.append(ValidationIssue("ERROR", scenario_id, msg))

    def add_warning(self, scenario_id: str, msg: str) -> None:
        self.issues.append(ValidationIssue("WARNING", scenario_id, msg))

    def add_info(self, scenario_id: str, msg: str) -> None:
        self.issues.append(ValidationIssue("INFO", scenario_id, msg))


class BenchmarkValidator:
    """Validates benchmark scenarios, referenced images, and matching answer keys."""

    def __init__(
        self,
        base_dir: Optional[Path | str] = None,
        require_all_ready: bool = False,
    ):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.require_all_ready = require_all_ready

    def resolve_path(self, rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (self.base_dir / p).resolve()

    def validate_scenarios(
        self,
        scenarios_dir: Path | str,
        keys_dir: Optional[Path | str] = None,
    ) -> ValidationReport:
        scenarios_path = Path(scenarios_dir)
        keys_path = Path(keys_dir) if keys_dir else None

        report = ValidationReport()
        scenario_files = sorted(scenarios_path.glob("*.json"))
        if not scenario_files:
            report.add_error("GLOBAL", f"No JSON scenario files found in {scenarios_path}")
            return report

        seen_scenario_ids: Dict[str, Path] = {}

        for s_file in scenario_files:
            report.total_scenarios += 1
            try:
                with open(s_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
            except Exception as e:
                report.add_error(s_file.stem, f"Malformed JSON in {s_file.name}: {e}")
                continue

            scenario_id = raw_data.get("scenario_id")
            if not scenario_id:
                report.add_error(s_file.stem, "Missing required field: 'scenario_id'")
                continue

            if scenario_id in seen_scenario_ids:
                report.add_error(
                    scenario_id,
                    f"Duplicate scenario_id '{scenario_id}' in {s_file.name} (already in {seen_scenario_ids[scenario_id].name})"
                )
            else:
                seen_scenario_ids[scenario_id] = s_file

            status = raw_data.get("status", "draft")
            if status not in ("draft", "ready"):
                report.add_error(scenario_id, f"Invalid status '{status}'. Must be 'draft' or 'ready'.")

            if status == "ready":
                report.ready_count += 1
            else:
                report.draft_count += 1

            if self.require_all_ready and status == "draft":
                report.add_error(scenario_id, "Scenario is marked 'draft' but --strict mode requires all to be 'ready'.")

            # Check required fields
            for req in ("course", "title", "initial_image_path", "turns"):
                if req not in raw_data or raw_data[req] is None:
                    report.add_error(scenario_id, f"Missing required top-level field: '{req}'")

            turns = raw_data.get("turns", [])
            if not isinstance(turns, list):
                report.add_error(scenario_id, f"'turns' must be a list, got {type(turns).__name__}")
                continue

            if len(turns) != 5:
                report.add_error(scenario_id, f"Scenario must have exactly 5 turns, found {len(turns)}")

            for idx, turn in enumerate(turns, start=1):
                if not isinstance(turn, dict):
                    report.add_error(scenario_id, f"Turn {idx} is not an object")
                    continue
                turn_id = turn.get("turn_id")
                if turn_id != idx:
                    report.add_error(scenario_id, f"Turn at index {idx} has invalid turn_id '{turn_id}'. Expected {idx}.")
                student_msg = turn.get("student_message", "")
                if not isinstance(student_msg, str) or not student_msg.strip():
                    report.add_error(scenario_id, f"Turn {idx} has empty or non-string 'student_message'")

                revised_img = turn.get("revised_image_path")
                if revised_img:
                    img_path = self.resolve_path(revised_img)
                    if not img_path.exists():
                        if status == "ready":
                            report.add_error(scenario_id, f"Turn {idx} revised image not found: {revised_img}")
                        else:
                            report.add_info(scenario_id, f"Draft pending revised image crop: {revised_img}")

            # Check initial image
            initial_img = raw_data.get("initial_image_path", "")
            if initial_img:
                img_path = self.resolve_path(initial_img)
                if not img_path.exists():
                    if status == "ready":
                        report.add_error(scenario_id, f"Initial image file not found on disk: {initial_img}")
                    else:
                        report.add_info(scenario_id, f"Draft pending initial image crop: {initial_img}")

            # Check matching answer key if keys_dir is provided
            if keys_path:
                key_file = keys_path / f"{scenario_id}.json"
                if not key_file.exists():
                    # Fallback check by file stem
                    key_file = keys_path / s_file.name

                if not key_file.exists():
                    if status == "ready":
                        report.add_error(scenario_id, f"Missing matching answer key file: {scenario_id}.json in {keys_path}")
                    else:
                        report.add_info(scenario_id, f"Draft pending answer key: {scenario_id}.json")
                else:
                    self._validate_answer_key(scenario_id, key_file, status, report)

            # If this is ready and has no errors so far for this scenario
            scenario_errors = [iss for iss in report.issues if iss.scenario_id == scenario_id and iss.level == "ERROR"]
            if status == "ready" and not scenario_errors:
                report.passed_ready_count += 1

        return report

    def _validate_answer_key(
        self,
        scenario_id: str,
        key_file: Path,
        scenario_status: str,
        report: ValidationReport,
    ) -> None:
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                key_data = json.load(f)
        except Exception as e:
            report.add_error(scenario_id, f"Malformed answer key JSON in {key_file.name}: {e}")
            return

        key_scenario_id = key_data.get("scenario_id")
        if key_scenario_id != scenario_id:
            report.add_error(
                scenario_id,
                f"Answer key scenario_id mismatch: key has '{key_scenario_id}', expected '{scenario_id}'"
            )

        key_turns = key_data.get("turns", [])
        if len(key_turns) != 5:
            if scenario_status == "ready":
                report.add_error(scenario_id, f"Answer key must have exactly 5 turns, found {len(key_turns)}")
            else:
                report.add_info(scenario_id, f"Draft answer key has {len(key_turns)}/5 turns")

        for idx, kturn in enumerate(key_turns, start=1):
            if not isinstance(kturn, dict):
                continue
            if kturn.get("turn_id") != idx:
                report.add_error(scenario_id, f"Answer key turn at index {idx} has turn_id '{kturn.get('turn_id')}', expected {idx}")
            ans = kturn.get("expected_answer", "")
            if not str(ans).strip():
                if scenario_status == "ready":
                    report.add_error(scenario_id, f"Answer key turn {idx} has empty expected_answer")
                else:
                    report.add_info(scenario_id, f"Draft answer key turn {idx} pending expected_answer")


def print_report(report: ValidationReport, verbose: bool = False) -> None:
    print("=" * 60)
    print("UREx Benchmark Validation Summary")
    print("=" * 60)
    print(f"Total Scenarios Found : {report.total_scenarios}")
    print(f"Ready Scenarios       : {report.ready_count} ({report.passed_ready_count} passed)")
    print(f"Draft Scenarios       : {report.draft_count} (work-in-progress)")
    print("-" * 60)

    errors = [i for i in report.issues if i.level == "ERROR"]
    warnings = [i for i in report.issues if i.level == "WARNING"]
    infos = [i for i in report.issues if i.level == "INFO"]

    if errors:
        print(f"\n[!] ERRORS ({len(errors)}):")
        for err in errors:
            print(f"  - [{err.scenario_id}] {err.message}")

    if warnings:
        print(f"\n[*] WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - [{w.scenario_id}] {w.message}")

    if verbose and infos:
        print(f"\n[i] DRAFT PENDING ITEMS ({len(infos)}):")
        for info in infos:
            print(f"  - [{info.scenario_id}] {info.message}")
    elif infos and not verbose:
        print(f"\n[i] {len(infos)} draft pending item(s) detected. Use --verbose to view all.")

    print("=" * 60)
    if report.has_errors:
        print("RESULT: FAILED (Errors detected)")
    else:
        print("RESULT: PASSED (All ready scenarios valid; drafts formatted properly)")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate UREx Benchmark scenarios and answer keys.")
    parser.add_argument(
        "--scenarios-dir",
        type=str,
        default="data/scenarios",
        help="Path to scenarios directory",
    )
    parser.add_argument(
        "--keys-dir",
        type=str,
        default="data/answer_keys",
        help="Path to private answer keys directory",
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=".",
        help="Base directory for resolving relative image paths",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any scenario is marked 'draft'",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print verbose details including all draft pending notices",
    )

    args = parser.parse_args()

    validator = BenchmarkValidator(
        base_dir=args.base_dir,
        require_all_ready=args.strict,
    )
    report = validator.validate_scenarios(
        scenarios_dir=args.scenarios_dir,
        keys_dir=args.keys_dir,
    )
    print_report(report, verbose=args.verbose)

    if report.has_errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
