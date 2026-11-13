# Retrieval improvements: five-sample pilot

This pilot tries to recover evidence that hard category filtering, one-shot ranking or missing section links can lose. It searches the same known contract and keeps the previous 6,000-character output cap.

## What is implemented

1. Search both original vector chunks and previously extracted passages. Combine semantic ranking with BM25-style keyword ranking. A matching rule category adds a small preference; other categories remain eligible.
2. Collect up to 20 candidates. Ask the already installed local Qwen3 4B model to rank them. Give it nearby text for context, while keeping returned evidence tied to the original candidate span.
3. Follow references to uniquely identified numbered sections in the same document. Fetch bounded source windows; follow at most two reference levels and add at most four reference passages. Missing or ambiguous references stay explicit.
4. Ask what evidence is still missing. Allow up to two follow-up rounds with at most two distinct queries each. Stop on repeated/no queries, unchanged evidence, the round limit or the model reporting sufficiency. Model-reported sufficiency is not verified completeness.

Full original text remains available to search. This is a query-time improvement, **not** re-extraction or a rebuild of the 100 Turtle files. Cross-document amendments, legal precedence and general cross-reference resolution are not implemented.

## Run boundary

The runner supports exactly five fixed, known development questions: 733, 269, 1375, 2316 and 10. They were chosen to include a category-filter failure, three multiple-snippet cases and a successful control. They are not a random or unseen sample. It has no whole-benchmark command.

The initial preflight attempt stopped before any Qwen ranking or scoring because pgvector returned a wrapper requiring `to_numpy()`. That attempt is preserved in `ontology/experiments/retrieval-v2-pilot5/`. A focused regression test covers the conversion. The corrected frozen run is `ontology/experiments/retrieval-v2-pilot5-r1/`.

## Files and commands

- `scripts/retrieval_v2.py`: retrieval code; no benchmark-answer access.
- `scripts/pilot_retrieval_v2.py`: freeze the five-sample protocol, retrieve, then score saved outputs.
- `scripts/test_retrieval_v2.py`: focused checks for vector conversion, soft filtering, reference links, ambiguity and stopping rules.
- `ontology/experiments/retrieval-v2-pilot5-r1/`: protocol, source-only traces, scored results and hashes.
- `artifacts/retrieval-v2-pilot5/responses/`: cached local model responses, including token counts.

```powershell
# Already prepared for the current pilot; do not re-initialize it.
& scripts/start-local-extractor.ps1
.venv/Scripts/python.exe scripts/pilot_retrieval_v2.py retrieve
.venv/Scripts/python.exe scripts/pilot_retrieval_v2.py evaluate
```

Completed retrieval/scoring commands refuse to overwrite their first outputs. Frozen code and source hashes must match. All five source-only retrieval traces are saved before the separate scoring process opens benchmark answers. A runtime audit guard rejects benchmark-question and prior-score reads during retrieval.

The existing model is reused; nothing new is downloaded. No paid model API is called. Query time includes local LLM work. Cold embedding-model loading and passage embedding are reported separately. Full-benchmark performance and generated legal-answer correctness remain untested.
