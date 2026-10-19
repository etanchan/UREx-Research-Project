"""Local Web Grading Studio server that reads and writes directly to scores/*.csv."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, List
import urllib.parse
import webbrowser

from urex_benchmark.scoring.auto_judge import (
    auto_grade_csv,
    create_judge_provider,
    load_scenario_metadata,
    read_csv_rows,
    write_csv_rows,
)
from urex_benchmark.scoring.summary import compute_summary, load_scoring_data


class StudioState:
    def __init__(
        self,
        repo_root: Path,
        scores_dir: Path,
        scenarios_dir: Path,
    ):
        self.repo_root = repo_root.resolve()
        self.scores_dir = scores_dir.resolve()
        self.scenarios_dir = scenarios_dir.resolve()

    def get_all_scenarios_meta(self) -> Dict[str, Dict[str, Any]]:
        meta = load_scenario_metadata(self.scenarios_dir)
        fixtures_dir = self.repo_root / "data" / "fixtures" / "scenarios"
        if fixtures_dir.exists():
            for k, v in load_scenario_metadata(fixtures_dir).items():
                if k not in meta:
                    meta[k] = v
        return meta

    def load_all_sheets(self) -> Dict[str, Any]:
        self.scores_dir.mkdir(parents=True, exist_ok=True)
        csv_files = sorted(self.scores_dir.glob("*.csv"))
        sheets: List[Dict[str, Any]] = []
        all_parsed_rows: List[Dict[str, Any]] = []

        for p in csv_files:
            try:
                fieldnames, rows = read_csv_rows(p)
            except Exception:
                continue

            filled_count = sum(
                1
                for r in rows
                if all(
                    str(r.get(c, "")).strip() != ""
                    for c in ("technical_correctness", "diagram_grounding", "pedagogical_clarity")
                )
            )
            model_id = rows[0].get("model_id", p.stem) if rows else p.stem
            sheets.append(
                {
                    "filename": p.name,
                    "model_id": model_id,
                    "total_rows": len(rows),
                    "filled_rows": filled_count,
                    "rows": rows,
                }
            )
            try:
                parsed = load_scoring_data(p)
                for pr in parsed:
                    pr["model_id"] = f"{model_id} ({p.name})"
                all_parsed_rows.extend(parsed)
            except Exception:
                pass

        summary = compute_summary(all_parsed_rows) if all_parsed_rows else {"total_rated_turns": 0, "models": {}}
        return {
            "sheets": sheets,
            "scenarios": self.get_all_scenarios_meta(),
            "summary": summary,
        }

    def save_row_score(
        self,
        filename: str,
        scenario_id: str,
        turn_id: int,
        technical_correctness: str,
        diagram_grounding: str,
        pedagogical_clarity: str,
        evaluator_notes: str,
    ) -> Dict[str, Any]:
        csv_path = (self.scores_dir / Path(filename).name).resolve()
        if not csv_path.exists() or csv_path.parent != self.scores_dir:
            raise FileNotFoundError(f"Invalid CSV file: {filename}")

        fieldnames, rows = read_csv_rows(csv_path)
        updated = False
        for r in rows:
            if r.get("scenario_id") == scenario_id and int(r.get("turn_id", 0)) == int(turn_id):
                r["technical_correctness"] = str(technical_correctness).strip()
                r["diagram_grounding"] = str(diagram_grounding).strip()
                r["pedagogical_clarity"] = str(pedagogical_clarity).strip()
                r["evaluator_notes"] = str(evaluator_notes)
                updated = True
                break

        if not updated:
            raise ValueError(f"Row not found for {scenario_id} turn {turn_id} in {filename}")

        write_csv_rows(csv_path, fieldnames, rows)
        return {"status": "ok", "filename": filename, "scenario_id": scenario_id, "turn_id": turn_id}


def make_handler(state: StudioState):
    ui_html_path = Path(__file__).parent / "studio_ui.html"

    class StudioRequestHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send_json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = urllib.parse.unquote(parsed.path)

            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if path in ("/", "/index.html"):
                if not ui_html_path.exists():
                    self.send_error(HTTPStatus.NOT_FOUND, "studio_ui.html not found")
                    return
                html_str = ui_html_path.read_text(encoding="utf-8")
                # Embed initial state directly so Safari renders all CSVs and scenarios on frame 1
                init_json = json.dumps(state.load_all_sheets(), ensure_ascii=False)
                # Escape '</script>' inside JSON strings so it never breaks the script tag
                init_json_safe = init_json.replace("</", "<\\/")
                html_str = html_str.replace(
                    "/*__EMBEDDED_INITIAL_STATE__*/",
                    f"window.__INITIAL_STATE__ = {init_json_safe};",
                )
                content = html_str.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
                return

            if path == "/api/state":
                self._send_json(state.load_all_sheets())
                return

            if path.startswith("/data/"):
                rel_path = path.lstrip("/")
                target = (state.repo_root / rel_path).resolve()
                data_root = (state.repo_root / "data").resolve()
                if not str(target).startswith(str(data_root)) or not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
                    return
                mime_type, _ = mimetypes.guess_type(str(target))
                raw = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mime_type or "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(raw)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length) if length > 0 else b"{}"

            try:
                body = json.loads(raw_body.decode("utf-8"))
            except Exception as exc:
                self._send_json({"error": f"Invalid JSON: {exc}"}, status=400)
                return

            if path == "/api/save_score":
                try:
                    res = state.save_row_score(
                        filename=body["filename"],
                        scenario_id=body["scenario_id"],
                        turn_id=int(body["turn_id"]),
                        technical_correctness=str(body.get("technical_correctness", "")),
                        diagram_grounding=str(body.get("diagram_grounding", "")),
                        pedagogical_clarity=str(body.get("pedagogical_clarity", "")),
                        evaluator_notes=str(body.get("evaluator_notes", "")),
                    )
                    self._send_json(res)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=400)
                return

            if path == "/api/auto_judge":
                try:
                    filenames = body.get("filenames") or []
                    scenario_id = body.get("scenario_id")
                    turn_id = body.get("turn_id")
                    if turn_id is not None:
                        turn_id = int(turn_id)
                    provider_name = body.get("provider", "gemini")
                    model_id = body.get("model_id", "gemini-2.5-flash")
                    overwrite = bool(body.get("overwrite", True))

                    provider = create_judge_provider(
                        provider_name=provider_name,
                        model_id=model_id,
                    )
                    results = []
                    for fn in filenames:
                        csv_path = (state.scores_dir / Path(fn).name).resolve()
                        if csv_path.exists() and csv_path.parent == state.scores_dir:
                            r = auto_grade_csv(
                                csv_file=csv_path,
                                provider=provider,
                                scenarios_dir=state.scenarios_dir,
                                scenario_filter=scenario_id,
                                turn_filter=turn_id,
                                overwrite=overwrite,
                            )
                            results.append(r)
                    self._send_json({"status": "ok", "results": results, "state": state.load_all_sheets()})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=500)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    return StudioRequestHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the UREx Local Web Grading Studio.")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve the local studio on (default: 8765)")
    parser.add_argument("--scores-dir", type=str, default="scores", help="Directory containing scoring CSV files")
    parser.add_argument("--scenarios-dir", type=str, default="data/scenarios", help="Directory containing scenario JSONs")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser tab")
    args = parser.parse_args()

    repo_root = Path.cwd()
    state = StudioState(
        repo_root=repo_root,
        scores_dir=repo_root / args.scores_dir,
        scenarios_dir=repo_root / args.scenarios_dir,
    )

    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    url = f"http://127.0.0.1:{args.port}"
    print("=" * 72)
    print(f"  UREx Evaluation Studio running at: {url}")
    print(f"  Reading & writing CSVs directly in: {(repo_root / args.scores_dir).resolve()}")
    print("  Press Ctrl+C to stop the server.")
    print("=" * 72)

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down UREx Evaluation Studio.")
        server.server_close()


if __name__ == "__main__":
    main()
