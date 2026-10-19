"""Unit tests for the local grading studio and AI auto-judge CSV synchronization."""

import tempfile
import unittest
from pathlib import Path

from urex_benchmark.scoring.auto_judge import (
    auto_grade_csv,
    create_judge_provider,
    parse_judge_json,
    read_csv_rows,
)
from urex_benchmark.scoring.studio import StudioState
from urex_benchmark.scoring.template import export_template


class TestScoringStudioAndJudge(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.scores_dir = Path(self.temp_dir.name) / "scores"
        self.scores_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.scores_dir / "test_scoring.csv"

        # Export template from demo_test or end_to_end_test if present, else create a synthetic CSV
        export_template(
            run_dir="runs/demo_test",
            output_file=self.csv_path,
            keys_dir="data/fixtures/answer_keys",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_studio_save_row_updates_csv_directly(self) -> None:
        state = StudioState(
            repo_root=Path.cwd(),
            scores_dir=self.scores_dir,
            scenarios_dir=Path("data/scenarios"),
        )
        res = state.save_row_score(
            filename="test_scoring.csv",
            scenario_id="demo_counter",
            turn_id=1,
            technical_correctness="2",
            diagram_grounding="1",
            pedagogical_clarity="2",
            evaluator_notes="Good answer, minor grounding note.",
        )
        self.assertEqual(res["status"], "ok")

        _, rows = read_csv_rows(self.csv_path)
        turn1 = next(r for r in rows if r["scenario_id"] == "demo_counter" and int(r["turn_id"]) == 1)
        self.assertEqual(turn1["technical_correctness"], "2")
        self.assertEqual(turn1["diagram_grounding"], "1")
        self.assertEqual(turn1["pedagogical_clarity"], "2")
        self.assertEqual(turn1["evaluator_notes"], "Good answer, minor grounding note.")

    def test_auto_judge_mock_populates_csv_directly(self) -> None:
        judge = create_judge_provider("mock")
        res = auto_grade_csv(
            csv_file=self.csv_path,
            provider=judge,
            scenarios_dir="data/fixtures/scenarios",
            turn_filter=2,
            overwrite=True,
        )
        self.assertEqual(res["graded"], 1)

        _, rows = read_csv_rows(self.csv_path)
        turn2 = next(r for r in rows if r["scenario_id"] == "demo_counter" and int(r["turn_id"]) == 2)
        self.assertEqual(turn2["technical_correctness"], "2")
        self.assertEqual(turn2["diagram_grounding"], "2")
        self.assertEqual(turn2["pedagogical_clarity"], "2")
        self.assertIn("[AI Judge: mock]", turn2["evaluator_notes"])

    def test_parse_judge_json_handles_fenced_output(self) -> None:
        raw = '```json\n{"technical_correctness": 2, "diagram_grounding": 1, "pedagogical_clarity": 0, "evaluator_notes": "Missed carry."}\n```'
        parsed = parse_judge_json(raw)
        self.assertEqual(parsed["technical_correctness"], 2)
        self.assertEqual(parsed["diagram_grounding"], 1)
        self.assertEqual(parsed["pedagogical_clarity"], 0)
        self.assertEqual(parsed["evaluator_notes"], "Missed carry.")


if __name__ == "__main__":
    unittest.main()
