"""Summarizes completed human scoring sheets by turn position and by scenario."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional


CRITERIA = [
    "technical_correctness",
    "diagram_grounding",
    "misconception_handling",
    "relevance",
    "appropriate_uncertainty",
]


def mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    if len(values) < 2:
        return round(m, 2), 0.0
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return round(m, 2), round(math.sqrt(var), 2)


def load_scoring_data(filepath: Path | str) -> List[Dict[str, Any]]:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Scores file not found: {path}")

    rows: List[Dict[str, Any]] = []
    if path.suffix.lower() == ".json":
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            rows = raw if isinstance(raw, list) else []
    else:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                rows.append(r)

    parsed_rows = []
    for r in rows:
        row_dict: Dict[str, Any] = {
            "model_id": r.get("model_id", "unknown"),
            "scenario_id": r.get("scenario_id", "unknown"),
            "turn_id": int(r.get("turn_id", 0)),
        }
        for crit in CRITERIA:
            val = r.get(crit, "")
            if val is not None and str(val).strip() != "":
                try:
                    num_val = float(val)
                    if 1.0 <= num_val <= 5.0:
                        row_dict[crit] = num_val
                    else:
                        row_dict[crit] = None
                except ValueError:
                    row_dict[crit] = None
            else:
                row_dict[crit] = None
        parsed_rows.append(row_dict)

    return parsed_rows


def compute_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Group by model
    models = sorted(list(set(r["model_id"] for r in rows)))

    summary: Dict[str, Any] = {
        "total_rated_turns": len(rows),
        "models": {},
    }

    for m in models:
        m_rows = [r for r in rows if r["model_id"] == m]
        scenarios = sorted(list(set(r["scenario_id"] for r in m_rows)))

        # 1. By Turn Position (1 to 5)
        by_turn: Dict[int, Dict[str, Any]] = {}
        for t in range(1, 6):
            t_rows = [r for r in m_rows if r["turn_id"] == t]
            turn_crit_stats: Dict[str, Any] = {}
            all_turn_values: List[float] = []
            for crit in CRITERIA:
                vals = [r[crit] for r in t_rows if r.get(crit) is not None]
                all_turn_values.extend(vals)
                avg, sd = mean_std(vals)
                turn_crit_stats[crit] = {"mean": avg, "std": sd, "count": len(vals)}

            t_avg, t_sd = mean_std(all_turn_values)
            turn_crit_stats["overall"] = {"mean": t_avg, "std": t_sd, "count": len(all_turn_values)}
            by_turn[t] = turn_crit_stats

        # 2. By Scenario
        by_scenario: Dict[str, Dict[str, Any]] = {}
        scenario_overall_means: List[float] = []

        for sc_id in scenarios:
            sc_rows = [r for r in m_rows if r["scenario_id"] == sc_id]
            sc_crit_stats: Dict[str, Any] = {}
            all_sc_values: List[float] = []
            for crit in CRITERIA:
                vals = [r[crit] for r in sc_rows if r.get(crit) is not None]
                all_sc_values.extend(vals)
                avg, sd = mean_std(vals)
                sc_crit_stats[crit] = {"mean": avg, "std": sd, "count": len(vals)}

            sc_avg, sc_sd = mean_std(all_sc_values)
            sc_crit_stats["overall"] = {"mean": sc_avg, "std": sc_sd, "count": len(all_sc_values)}
            by_scenario[sc_id] = sc_crit_stats
            if all_sc_values:
                scenario_overall_means.append(sc_avg)

        # Macro scenario mean
        macro_sc_avg, macro_sc_sd = mean_std(scenario_overall_means)

        summary["models"][m] = {
            "scenario_count": len(scenarios),
            "macro_scenario_score": {"mean": macro_sc_avg, "std": macro_sc_sd},
            "by_turn_position": by_turn,
            "by_scenario": by_scenario,
        }

    return summary


def print_summary_table(summary: Dict[str, Any]) -> None:
    print("=" * 80)
    print("UREx Engineering Diagrams - Benchmark Score Analysis")
    print("=" * 80)
    print(f"Total Rated Turns Evaluated: {summary['total_rated_turns']}")
    print("Note: Aggregations preserve conversation structure by analyzing")
    print("      (a) progression across turns 1-5, and (b) averages per scenario.")
    print("-" * 80)

    for model_id, m_data in summary["models"].items():
        print(f"\nMODEL: {model_id} (Evaluated on {m_data['scenario_count']} scenario(s))")
        macro = m_data["macro_scenario_score"]
        print(f"Macro Scenario Average Score: {macro['mean']} ± {macro['std']} (Scale: 1.0 - 5.0)")
        print("\n--- 1. Breakdown by Turn Position (Turns 1 to 5) ---")
        headers = ["Turn", "Correctness", "Grounding", "Misconception", "Relevance", "Uncertainty", "Turn Avg"]
        print(f"{headers[0]:<6} | {headers[1]:<11} | {headers[2]:<10} | {headers[3]:<13} | {headers[4]:<10} | {headers[5]:<11} | {headers[6]:<9}")
        print("-" * 82)

        for t in range(1, 6):
            t_data = m_data["by_turn_position"].get(t, {})
            c_vals = [
                f"{t_data.get(c, {}).get('mean', 0.0):.2f}" if t_data.get(c, {}).get('count', 0) > 0 else "N/A"
                for c in CRITERIA
            ]
            overall = f"{t_data.get('overall', {}).get('mean', 0.0):.2f}" if t_data.get("overall", {}).get("count", 0) > 0 else "N/A"
            print(f"Turn {t:<1} | {c_vals[0]:<11} | {c_vals[1]:<10} | {c_vals[2]:<13} | {c_vals[3]:<10} | {c_vals[4]:<11} | {overall:<9}")

        print("\n--- 2. Breakdown by Scenario ---")
        sc_headers = ["Scenario ID", "Turns Rated", "Scenario Mean Score"]
        print(f"{sc_headers[0]:<35} | {sc_headers[1]:<12} | {sc_headers[2]:<20}")
        print("-" * 75)
        for sc_id, sc_data in m_data["by_scenario"].items():
            cnt = sc_data.get("overall", {}).get("count", 0)
            avg = sc_data.get("overall", {}).get("mean", 0.0)
            sd = sc_data.get("overall", {}).get("std", 0.0)
            score_str = f"{avg:.2f} ± {sd:.2f}" if cnt > 0 else "No ratings"
            print(f"{sc_id:<35} | {cnt:<12} | {score_str:<20}")

    print("\n" + "=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize human scoring sheets.")
    parser.add_argument(
        "--scores-file",
        type=str,
        required=True,
        help="Path to filled scoring CSV or JSON",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default=None,
        help="Optional path to export summary JSON",
    )

    args = parser.parse_args()
    rows = load_scoring_data(args.scores_file)
    summary = compute_summary(rows)
    print_summary_table(summary)

    if args.output_json:
        out_p = Path(args.output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary saved to: {out_p}")


if __name__ == "__main__":
    main()
