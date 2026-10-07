"""Multi-turn conversation runner for UREx Engineering Diagrams benchmark."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from urex_benchmark.models import ModelMessage, Scenario, ScenarioRunResult, TurnResult
from urex_benchmark.providers.base import BaseProvider
from urex_benchmark.providers.gemini import GeminiProvider
from urex_benchmark.providers.mock import MockProvider
from urex_benchmark.providers.soclaas import SoCLaaSProvider


class ConversationRunner:
    """Orchestrates 5-turn sequential conversations across benchmark scenarios."""

    def __init__(
        self,
        provider: BaseProvider,
        output_dir: Path | str,
        dataset_version: str = "1.0.0",
        delay_between_turns: float = 0.0,
    ):
        self.provider = provider
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dataset_version = dataset_version
        self.delay_between_turns = delay_between_turns

    def run_scenario(self, scenario: Scenario) -> ScenarioRunResult:
        """Executes a single scenario through 5 sequential turns with immediate persistence."""
        start_iso = datetime.now(timezone.utc).isoformat()
        scenario_run = ScenarioRunResult(
            scenario_id=scenario.scenario_id,
            model_identifier=self.provider.model_identifier,
            status="in_progress",
            dataset_version=self.dataset_version,
            model_settings=self.provider.settings,
            start_time=start_iso,
            turns=[],
        )

        scenario_file = self.output_dir / f"{scenario.scenario_id}.json"
        scenario_run.save_to_file(scenario_file)

        conversation_id = self.provider.start_conversation(scenario.scenario_id)
        history: List[ModelMessage] = []

        try:
            for turn in scenario.turns:
                k = turn.turn_id
                # Determine image to attach
                if k == 1:
                    attached_image = scenario.initial_image_path
                elif turn.revised_image_path:
                    attached_image = turn.revised_image_path
                else:
                    attached_image = None

                turn_start_iso = datetime.now(timezone.utc).isoformat()

                try:
                    resp = self.provider.send_turn(
                        conversation_id=conversation_id,
                        turn_id=k,
                        student_message=turn.student_message,
                        image_path=attached_image,
                        history=list(history),  # pass shallow copy
                    )

                    turn_result = TurnResult(
                        turn_id=k,
                        student_message=turn.student_message,
                        attached_image_path=attached_image,
                        model_response=resp.content,
                        token_usage=resp.token_usage,
                        latency_ms=resp.latency_ms,
                        timestamp=turn_start_iso,
                        error=None,
                    )
                    scenario_run.turns.append(turn_result)

                    # Update conversation history with model's actual response
                    history.append(
                        ModelMessage(
                            role="student",
                            content=turn.student_message,
                            image_path=attached_image,
                        )
                    )
                    history.append(
                        ModelMessage(
                            role="assistant",
                            content=resp.content,
                        )
                    )

                    # Save immediately after each turn
                    scenario_run.save_to_file(scenario_file)

                    if self.delay_between_turns > 0:
                        time.sleep(self.delay_between_turns)

                except Exception as turn_err:
                    turn_result = TurnResult(
                        turn_id=k,
                        student_message=turn.student_message,
                        attached_image_path=attached_image,
                        model_response=None,
                        timestamp=turn_start_iso,
                        error=f"Turn {k} error: {str(turn_err)}",
                    )
                    scenario_run.turns.append(turn_result)
                    scenario_run.status = "failed"
                    scenario_run.error = f"Failed at turn {k}: {str(turn_err)}"
                    scenario_run.end_time = datetime.now(timezone.utc).isoformat()
                    scenario_run.save_to_file(scenario_file)
                    # Break out of turns loop for this scenario
                    return scenario_run

            # All turns completed successfully
            scenario_run.status = "completed"
            scenario_run.end_time = datetime.now(timezone.utc).isoformat()
            scenario_run.save_to_file(scenario_file)
            return scenario_run

        finally:
            self.provider.close_conversation(conversation_id)

    def run_all(
        self,
        scenarios: List[Scenario],
        skip_drafts: bool = True,
    ) -> Dict[str, Any]:
        """Runs a collection of scenarios, isolating failures and generating a run manifest."""
        manifest: Dict[str, Any] = {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "model_identifier": self.provider.model_identifier,
            "dataset_version": self.dataset_version,
            "total_submitted": len(scenarios),
            "completed": 0,
            "failed": 0,
            "skipped_drafts": 0,
            "results": {},
        }

        for scenario in scenarios:
            if skip_drafts and scenario.status == "draft":
                manifest["skipped_drafts"] += 1
                continue

            print(f"--> Running Scenario: {scenario.scenario_id} [{scenario.title[:40]}...]")
            res = self.run_scenario(scenario)
            manifest["results"][scenario.scenario_id] = {
                "status": res.status,
                "turns_completed": len([t for t in res.turns if t.error is None]),
                "error": res.error,
            }
            if res.status == "completed":
                manifest["completed"] += 1
                print(f"    [OK] Completed all 5 turns.")
            else:
                manifest["failed"] += 1
                print(f"    [FAIL] Failed: {res.error}")

        # Save manifest
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UREx Engineering Diagrams benchmark evaluation.")
    parser.add_argument(
        "--scenarios-dir",
        type=str,
        default="data/fixtures/scenarios",
        help="Directory containing scenario JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="runs/latest",
        help="Directory to save run results",
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["mock", "soclaas", "gemini"],
        default="mock",
        help="Model provider to execute ('mock', 'soclaas', or 'gemini')",
    )
    parser.add_argument(
        "--model-id",
        type=str,
        default=None,
        help="Model identifier (defaults: mock-vlm-v1 for mock, default for soclaas, gemini-flash-latest for gemini)",
    )
    parser.add_argument(
        "--api-base",
        type=str,
        default=None,
        help="Custom API base URL (optional, defaults to SOCLAAS_BASE_URL env or standard endpoint)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature (default: 0.2)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Max generation tokens per turn (default: 2048)",
    )
    parser.add_argument(
        "--thinking-level",
        type=str,
        default=None,
        choices=["minimal", "low", "medium", "high"],
        help="Reasoning thinking level for models supporting thinkingConfig (e.g. Gemini 3.x)",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Attempt running scenarios marked as 'draft'",
    )
    parser.add_argument(
        "--scenario-id",
        type=str,
        default=None,
        help="Run only a specific scenario ID",
    )

    args = parser.parse_args()

    scenarios_path = Path(args.scenarios_dir)
    scenario_files = sorted(scenarios_path.glob("*.json"))

    scenarios: List[Scenario] = []
    for sf in scenario_files:
        sc = Scenario.from_json_file(sf)
        if args.scenario_id and sc.scenario_id != args.scenario_id:
            continue
        scenarios.append(sc)

    if not scenarios:
        print(f"No matching scenarios found in {scenarios_path}")
        sys.exit(1)

    provider: BaseProvider
    if args.provider == "mock":
        model_id = args.model_id or "mock-vlm-v1"
        provider = MockProvider(model_identifier=model_id)
    elif args.provider == "soclaas":
        model_id = args.model_id or "default"
        settings: Dict[str, Any] = {
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }
        if args.api_base:
            settings["base_url"] = args.api_base
        provider = SoCLaaSProvider(model_identifier=model_id, **settings)
    elif args.provider == "gemini":
        model_id = args.model_id or "gemini-flash-latest"
        gemini_settings: Dict[str, Any] = {
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }
        if args.thinking_level:
            gemini_settings["thinking_level"] = args.thinking_level
        provider = GeminiProvider(model_identifier=model_id, **gemini_settings)
    else:
        raise ValueError(f"Unknown provider: {args.provider}")

    runner = ConversationRunner(
        provider=provider,
        output_dir=args.output_dir,
    )

    print(f"Starting benchmark evaluation with provider: {args.provider} ({provider.model_identifier})")
    print(f"Output directory: {args.output_dir}")
    manifest = runner.run_all(scenarios, skip_drafts=not args.include_drafts)

    print("\n" + "=" * 50)
    print("Execution Summary:")
    print(f"  Total Scenarios : {manifest['total_submitted']}")
    print(f"  Completed       : {manifest['completed']}")
    print(f"  Failed          : {manifest['failed']}")
    print(f"  Skipped Drafts  : {manifest['skipped_drafts']}")
    print(f"  Manifest saved  : {Path(args.output_dir) / 'manifest.json'}")
    print("=" * 50)


if __name__ == "__main__":
    main()
