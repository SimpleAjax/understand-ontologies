# Running and keeping our experiments

Each experiment now has its own version folder. Every run saves an executable copy of that version **and its shared code**, before doing any search.

Think of a run folder as a recipe, ingredients list and result kept together. Changing today's recipe does not change yesterday's saved copy.

## Where things live

```text
understand-ontologies/
  lab.py                         One command to run, rerun, replay or compare
  experiments/
    registry.json                Names of available versions
    vector-rag/v1/
    catalogue-search/v1/
    category-search/v1/
    agentic-search/v2/
    sentence-selection/v1/
      run.py                     Start this version
      pipeline.py                Its behavior or selected shared engine
      config.json                Settings and pinned shared/scorer versions
      prompt.txt                 Exact prompt; baseline has no LLM prompt
      requirements.lock          58 exact dependency versions
      environment.lock.json      Python, platform and dependency checks
      tests/                     Tests belonging to this version
      README.md
  shared/v1/                     Versioned retrieval, model, database and tracing code
  evaluation/v1/scorer.py         Shared character-overlap scoring
  datasets/pilot-5/
    questions.json               Questions and routing metadata; no expected answers
    expected-evidence.json       Correct passages; opened after retrieval for scoring
    source-manifest.json         Document names, hashes and development-set warning
  tests/test_lab.py               Archive, isolation and tamper checks
  artifacts/experiment-runs/     A separate folder for every execution
```

Shared code avoids copying the same database/model helpers into five pipelines. A version's config pins its shared implementation. A historical run also saves its own copy of that implementation.

## The five experiments

| ID | What runs |
|---|---|
| `vector-v1` | Original chunks, BGE cosine search, top five |
| `catalogue-v1` | BGE search over extracted passages, without category filtering |
| `category-v1` | Earlier strict category filtering and stored evidence links |
| `agentic-v2` | Hybrid search, soft categories, Qwen ranking, section lookup and follow-up |
| `sentence-selection-v1` | Qwen selects exact sentences from fixed saved agentic evidence |

Sentence selection keeps the original R1 evidence as its input. It does not silently use a later retrieval run. Its timing measures **additional sentence selection only**. Baseline/agentic timings measure retrieval, excluding setup/model initialization outside their timed stage. Whole-process startup time is longer.

These are five previously inspected development examples, with the correct contract already supplied. They are not a held-out test or a whole-corpus document-finding test. Precision and recall measure exact character overlap, not whether a legal answer is complete.

## Commands

Run from this project folder, using its current Python environment:

```powershell
.\.venv\Scripts\python.exe lab.py list

# Run a current version. Use --limit 1 for one sample, up to 5.
.\.venv\Scripts\python.exe lab.py run vector-v1 --limit 5 --no-langfuse

# Check any version without executing retrieval or calling a model.
.\.venv\Scripts\python.exe lab.py check agentic-v2 --no-langfuse

# Re-execute OLD CODE with its saved inputs in a NEW output folder.
.\.venv\Scripts\python.exe lab.py rerun <saved-run-folder> --no-langfuse

# Only rescore saved outputs. No retrieval or model calls.
.\.venv\Scripts\python.exe lab.py replay <saved-run-folder> --no-langfuse

# Compare two matching runs, including different experiment versions.
.\.venv\Scripts\python.exe lab.py compare <run-A-folder> <run-B-folder>
```

Replace placeholders with real paths. Paths containing spaces need quotes. Each run prints its new folder and report location.

For Qwen experiments, start the existing local service first:

```powershell
& .\scripts\start-local-extractor.ps1
.\.venv\Scripts\python.exe lab.py run sentence-selection-v1 --limit 5
.\.venv\Scripts\python.exe lab.py run agentic-v2 --limit 5
```

Baselines and sentence selection use Langfuse when configured, unless `--no-langfuse` is supplied. The existing agentic-v2 tracing engine requires Langfuse. This restructuring does not add paid model API calls or download models.

Directly executing `experiments/<family>/<version>/run.py --limit 1` delegates to `lab.py`, so it also archives the implementation before execution.

## What every new run keeps

```text
artifacts/experiment-runs/<experiment>/<unique-run>/
  code/
    experiment/                 Exact selected version, prompt, config, locks and tests
    shared/v1/                  Exact shared implementation used
    evaluation/v1/              Exact scorer
    datasets/pilot-5/           Exact dataset snapshot
    upstream.json               Pinned LegalBenchRAG commit
    graph-lock.json             Identity of the sealed ontology inputs
  bundle-lock.json              Hash of every archived file and inputs.json
  inputs.json                   Exact questions, documents and fixed evidence if applicable
  config.json                   Mode and resolved version config
  model.json                    BGE revision or Qwen digest/settings
  database.json                 Indexed chunk/vector fingerprint for search runs
  execution-proof.json          Imported archive module paths and hashes
  output-<source>.json           Retrieved text, offsets, timing and trace links
  responses/                    Selection requests/responses, when applicable
  agentic-details/              Agentic requests/responses/traces, when applicable
  results.json / results.md      Metrics and readable report
  manifest.json                 Complete, validated or failed
  run-lock.json                 Saved run file hashes
```

A rerun verifies the original saved files, copies its archived code and inputs, and executes that copy in a separate isolated Python process. It checks dependency versions, source hashes, sealed graph identity and model identity. Search reruns also check the saved database chunk/vector fingerprint. It does not import the current `scripts/` implementation.

A replay uses the archived scorer and saved outputs. It records no fresh inference latency. Comparison refuses different sample/document versions, expected evidence, scorer or upstream scoring versions.

## How we make the next improvement

1. Copy the relevant version folder to the next version, for example `sentence-selection/v2`.
2. Change that version's pipeline, prompt or config. If shared behavior changes, create `shared/v2` and point the new config to it.
3. Add the new ID and folder to `experiments/registry.json`.
4. Run it on the same five samples, then compare the reports.

Preserve earlier versions. Saved run bundles provide an extra independent copy even if somebody later edits a version folder by mistake. Git is still useful for tracking changes; nothing has been committed or pushed by this task.

Dependency locks pin Python 3.12.8 and Windows AMD64 plus the installed transitive package versions. A mismatch stops execution. To restore a run's environment, create a Python 3.12.8 virtual environment and install its saved `code/experiment/requirements.lock`, then invoke this project's `lab.py` with that environment's Python. Packages, model weights and PostgreSQL/Ollama services are not bundled. The original corpus, sealed Turtle files, clean pinned vendor checkout and relevant database ingestion must remain available. Rerunning identical code can still yield different Qwen outputs and timings because local inference is not guaranteed bit-for-bit deterministic.

`lock_lab_environment.py <new-version-folder>` can generate locks for a new version without existing lock files. It refuses to replace an existing version's locks.

## Existing results

Older reports and `scripts/experiment_lab.py` remain untouched. Those earlier runs kept partial code snapshots; they cannot honestly be treated as complete executable bundles. The new `rerun` command explains this if given an old folder. Its guarantee starts with the new `lab.py` runs.

## Verification of this change

- Seven archive/runner tests and eight experiment tests passed.
- All five versions passed archived import/config/source validation without new Qwen inference.
- One real vector-search sample was run, then rerun from its archived bundle. Retrieved passages and metrics matched; execution proofs show isolated archived imports.
- Saved-output replay reproduced the scores without model calls, and matched comparison produced a report.
- No full benchmark, new extraction or new Qwen experiment was executed for this restructuring.

Verified comparison: `artifacts/experiment-comparisons/compare-e3bd1b8c.md`.


## Domain ontology experiment (ten agreements)

A separate `domain-ontology-v1` experiment builds richer source-linked graphs before selecting one evaluation question per agreement. It uses graph-only agent tools and produces a cited answer; a normal-RAG comparator runs separately afterward. Its agreement cap is ten; the earlier experiments retain their five-question cap.

See [its design and commands](experiments/domain-ontology/v1/README.md). Unlike `agentic-v2`, it has no vector or keyword fallback. This first evaluation supplies the correct agreement to both methods and does not evaluate cross-document routing. Full source preservation is not proof of full semantic extraction, and generated answers need human review.


## Current domain inference model

Use [domain-deepseek-v2](experiments/domain-deepseek/v2/README.md) for new domain-query experiments: all LLM inference is DeepSeek via OpenRouter, with no local Qwen dependency. It reuses frozen graph pairs to isolate inference changes. Historical local versions remain available for comparison.

## Broader document validation

[domain-deepseek-v3](experiments/domain-deepseek/v3/README.md) selects 20 additional agreements uniformly from the remaining 90 using seed 20261115. It rebuilds both graph variants from source with the same DeepSeek prompts and semantic limits, freezes them, then evaluates every eligible question. It compares normal RAG, existing ontology and additive expanded relationships. Size/validation failures stay in the denominator. This tests applicability to longer, more varied agreements; it does not test cross-document routing or legal-answer correctness.

Run with `.\.venv\Scripts\python.exe lab.py run domain-deepseek-v3 --limit 20`. Use `--extraction-cache <prior-run>` to recover exact matching source-only API responses after interruption; their original raw responses and provenance remain recorded. `rerun` executes the completed run's archived code against its frozen graphs; `replay --no-langfuse` rescoring makes no new model calls. Include interrupted-attempt spend when reporting recovery costs.
