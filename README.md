# UREx Engineering Diagrams Benchmark

A multi-turn benchmark evaluating Vision-Language Models (VLMs) on pedagogical explanations of engineering diagrams across sequential student follow-up questions.

The benchmark spans 20 curated scenarios drawn from core NUS electrical and computer engineering / computer science curricula:
- **CG3207: Computer Architecture** (Scenarios 01–12)
- **CG2271: Real-Time Operating Systems** (Scenarios 13–17)
- **CS2113: Software Engineering & Object-Oriented Programming** (Scenarios 18–20)

Each scenario represents **one coherent 5-turn conversation**, not five independent questions. The model receives an initial diagram and sequential student queries while retaining its own conversational history. Select turns attach a revised diagram to test visual updating.

---

## Repository Architecture & Layout

```
.
├── .gitignore                      # Excludes API keys, virtualenvs, cache, and raw runs
├── pyproject.toml                  # Python package configuration
├── README.md                       # Benchmark documentation and runbook
├── data/
│   ├── scenarios/                  # 20 benchmark scenario JSON definitions (status: "ready")
│   ├── answer_keys/                # Private researcher expected answers and rubrics
│   ├── images/                     # 23 prepared PNG stimuli, including 3 turn-4 variants
│   ├── image_sources/              # Editable SVGs, two slide exports, provenance and review gallery
│   └── fixtures/                   # Self-contained synthetic test fixtures
│       ├── scenarios/              # demo_counter.json (status: "ready")
│       ├── answer_keys/            # demo_counter.json
│       └── images/                 # demo_diagram_turn1.png, demo_diagram_turn4.png
├── src/
│   └── urex_benchmark/
│       ├── models.py               # Data models for scenarios, turns, runs, scores
│       ├── validator.py            # Integrity and readiness validator CLI
│       ├── runner.py               # 5-turn stateful conversation orchestrator
│       ├── providers/
│       │   ├── base.py             # Provider-neutral BaseProvider interface
│       │   └── mock.py             # Deterministic MockProvider for offline testing
│       └── scoring/
│           ├── template.py         # Human-scoring sheet exporter (CSV/JSON)
│           └── summary.py          # Score aggregation by turn position & scenario
├── runs/                           # (Git-ignored) Saved evaluation runs with immediate per-turn flush
├── scores/                         # Human evaluation score sheets
├── analysis/                       # Aggregated benchmark analysis outputs
├── scripts/
│   └── seed_question_bank.py       # Source ingestion script from question bank
└── tests/                          # Automated test suite (isolation, order, zero-leakage)
```

---

## Version Control Policy

| Input / Artifact | In Version Control? | Policy & Rationale |
| :--- | :--- | :--- |
| `data/scenarios/*.json` | **YES** | Public benchmark definition containing scenario metadata and student questions. |
| `data/images/*` | **YES** | Benchmark visual stimuli required for experimental reproducibility. |
| `data/answer_keys/*.json` | **YES (Private)** | Private researcher ground truth. Kept strictly isolated from runner prompts. |
| `data/fixtures/*` | **YES** | Synthetic fixture ensuring CI/CD and tests run out-of-the-box. |
| `runs/` | **NO** | Raw model evaluation transcripts (voluminous output; git-ignored). |
| `scores/` | **YES (Final only)** | Finalized human evaluation sheets for publication (drafts git-ignored). |
| `.env`, `*key*.json` | **NEVER** | API keys and credentials are strictly excluded via `.gitignore`. |

---

## Data Schema & Format

### 1. Scenario Definition (`data/scenarios/<scenario_id>.json`)
```json
{
  "scenario_id": "scenario_01",
  "course": "CG3207",
  "title": "What do the two adder outputs mean?",
  "status": "draft",
  "initial_image_path": "data/images/cg3207_01_adder_symbols.png",
  "source_reference": "Week 6/Chapter 4 Arithmetic for Computers.pdf, p.3",
  "notes": "Draft pending final image crop",
  "turns": [
    {
      "turn_id": 1,
      "student_message": "What do A, B, Cin, S and Cout represent on these two symbols?...",
      "revised_image_path": null
    },
    ...
    {
      "turn_id": 4,
      "student_message": "If I had to add two two-bit numbers...",
      "revised_image_path": "data/images/cg3207_01_ripple_chain_unanswered.png"
    }
  ]
}
```

### 2. Private Answer Key (`data/answer_keys/<scenario_id>.json`)
Physically decoupled from scenario files to prevent prompt contamination:
```json
{
  "scenario_id": "scenario_01",
  "turns": [
    {
      "turn_id": 1,
      "expected_answer": "A and B are the one-bit operands. S is the sum bit...",
      "key_points": ["Operand bits", "Sum bit", "Carry bit"],
      "common_misconceptions": ["Confusing Cout with overflow"]
    }
  ]
}
```

---

## Setup & Quickstart

### Prerequisites
- Python 3.10+ (Standard library only; zero mandatory third-party dependencies).

```bash
git clone <repo-url>
cd "UREx Repository"
```

### 1. Validate Benchmark Data
Check scenarios, turn counts, image file references, and answer-key alignment:
```bash
# Validate runnable fixtures (passes)
PYTHONPATH=src python3 -m urex_benchmark.validator \
  --scenarios-dir data/fixtures/scenarios \
  --keys-dir data/fixtures/answer_keys

# Validate all 20 prepared scenarios and their image references
PYTHONPATH=src python3 -m urex_benchmark.validator \
  --scenarios-dir data/scenarios \
  --keys-dir data/answer_keys --strict
```

The 23 prepared images can be inspected in [the local review gallery](data/image_sources/review.html).
Click an image to open it at full resolution. [The manifest](data/image_sources/manifest.json)
records source paths, page/slide numbers, preparation steps, dimensions and SHA-256 checksums.

Most images preserve the original course diagrams. Crops exclude worked answers and surrounding
teaching prose; the pipeline timelines also omit answer arrows/shading, and cache diagrams omit
worked mappings and mapping colors. The branch diagram, unanswered ripple chain and UART frame
have editable SVG sources. The revised page table updates both its entry and physical frame placement;
the architecture variant adds only the direct UI-to-File association. Existing CS2113 PNGs retain
their native resolution. No extra detail is inferred from upscaling them.

To rebuild the images, use a separate environment with the optional preparation tools:

```bash
python3 -m venv /tmp/urex-image-tools
/tmp/urex-image-tools/bin/pip install -r scripts/image-requirements.txt
/tmp/urex-image-tools/bin/python scripts/prepare_images.py
```

The build reads local `referenceFiles` and the editable sources. Two single-slide PDF exports
(CG2271 lecture 8 slide 7 and lecture 6 slide 19) are retained under `data/image_sources` to
preserve PowerPoint's rendering without requiring Office during rebuilds. These are preparation
inputs, not model attachments. The build reads no answer keys and does not change scenario readiness.
Readiness means images are prepared and structurally valid; it does not represent model evaluation results.
The original `seed_question_bank.py` remains a draft-data initialization script and will reset
scenario status if rerun; it is not needed for image rebuilding.

### 2. Run the Mock Provider (No API Key Required)
Run the stateful 5-turn conversation runner locally:
```bash
PYTHONPATH=src python3 -m urex_benchmark.runner \
  --scenarios-dir data/fixtures/scenarios \
  --provider mock \
  --model-id mock-vlm-v1 \
  --output-dir runs/mock_pilot
```
*Results are saved immediately after each turn to `runs/mock_pilot/` with latency, token usage, and history tracking.*

### 3. Export Human Scoring Sheet
Generate an evaluation template keyed by `(model_id, scenario_id, turn_id)`. Includes rubric columns and optional private expected answers as grader reference:
```bash
PYTHONPATH=src python3 -m urex_benchmark.scoring.template \
  --run-dir runs/mock_pilot \
  --keys-dir data/fixtures/answer_keys \
  --output-file scores/mock_pilot_scoring.csv
```

### 4. Summarize Completed Ratings
Analyze completed ratings broken down by **turn position (Turns 1 to 5)** and **by scenario** (avoiding treating 100 turns as independent):
```bash
PYTHONPATH=src python3 -m urex_benchmark.scoring.summary \
  --scores-file scores/mock_pilot_scoring.csv
```

### 5. Run the Automated Test Suite
Verify conversation isolation, turn ordering, revised-image handling, and zero leakage of answer keys:
```bash
PYTHONPATH=src python3 -m unittest discover -s tests -p "test_*.py" -v
```

---

## Human Scoring Rubric

Human evaluators rate each turn on a 1–5 Likert scale across five dimensions:
1. **Technical Correctness**: Factual and conceptual accuracy of engineering details.
2. **Diagram Grounding**: Explicit and faithful attribution to visual elements in the diagram.
3. **Misconception Handling**: Detection and pedagogical correction of student fallacies.
4. **Relevance**: Direct focus on student query without extraneous verbosity.
5. **Appropriate Uncertainty**: Correct calibration when diagram lacks specific parameters.

---

## Adding a Real Model Provider

To add a real vision-language model (e.g., Google Gemini, OpenAI GPT-4o, Anthropic Claude, or local Ollama/vLLM):

1. Create a provider file in `src/urex_benchmark/providers/`, subclassing `BaseProvider`:
```python
from urex_benchmark.providers.base import BaseProvider, ProviderResponse

class GeminiProvider(BaseProvider):
    def __init__(self, model_identifier: str = "gemini-1.5-pro", api_key: str = None, **settings):
        super().__init__(model_identifier, **settings)
        # Initialize Google GenAI client here

    def start_conversation(self, scenario_id: str) -> str:
        # Create and return a unique session or chat session ID
        return f"gemini-{scenario_id}"

    def send_turn(self, conversation_id, turn_id, student_message, image_path, history) -> ProviderResponse:
        # 1. Format history and current student message for the provider API
        # 2. Attach image bytes if image_path is not None
        # 3. Call model API and measure latency
        # 4. Return ProviderResponse(content=reply_text, token_usage=usage_dict, latency_ms=ms)
        ...
```
2. Register the provider in `src/urex_benchmark/runner.py` under the `--provider` argument.
3. Never pass `data/answer_keys` paths into the runner or provider.
