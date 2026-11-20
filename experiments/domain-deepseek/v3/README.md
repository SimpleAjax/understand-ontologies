# Broader-sample validation: 20 additional random agreements

Completed results, limitations and rerun commands: [LATEST-RUN.md](LATEST-RUN.md).

The model, provider, extraction/query prompts, source segmentation, provision schema, relationship design, query rounds, directory/neighbor/context limits and output budgets are frozen from DeepSeek-only v2. This run changes the document/question cohort, not the semantic pipeline.

Selection: seed 20261115, uniform sample of 20 from the 90 remaining documents in the existing 100-document corpus. The previous ten are excluded. Selection used IDs only before opening evaluation questions. No document replacement, length filter or score-based exclusion. These documents may have appeared in older work; this is new to this experiment, not an independently blind study.

All source-only graphs (existing + expanded) are built and frozen before opening benchmark questions. Every eligible question whose evidence is in one selected agreement is evaluated, without task-topic filtering. Correct agreement is supplied to all three methods; document routing is not measured.

Three document workers use OpenRouter DeepSeek V4.1 Flash 1017 via pinned wafer/us. All query decisions and answers also use that API. No local Qwen is used. BGE/pgvector is only the separate CPU retrieval comparator. Actual costs and failures are retained; configured per-run API reservation ceiling is $2.

Longer documents can exceed the unchanged 20,000-character provision-directory or other context limits. Such query validation/limit errors are recorded with empty evidence and included as zero-recall/zero-precision outcomes, not silently removed or replaced. Network/authentication errors stop the run. Model schema errors during querying are similarly retained; no score-driven retry/tuning is performed. This operational handling is required to measure the current pipeline's applicability to larger documents; results must report its failure rate separately from successfully executed queries.

```powershell
.\.venv\Scripts\python.exe lab.py run domain-deepseek-v3 --limit 20
.\.venv\Scripts\python.exe -m unittest discover -s experiments/domain-deepseek/v3/tests -v
```

Each run archives code, prompts, dataset manifest, locks, exact API requests/responses, per-document/per-question usage, graph steps, original quotations, answers and scoring. Earlier experiments remain available for comparison. Completed-run rerun uses frozen graphs; replay reproduces saved scores without inference. Source-layer text preservation and quotation checks do not prove semantic completeness, relationship truth or legal-answer correctness.

Operational recovery: the first attempt stopped after 120 calls ($0.112152134) because two model JSON strings contained unescaped literal tab characters. The continuation reuses exact matching source-only responses, including expanded-link responses. A narrow parser fallback accepts literal string control characters, preserves the original response and values, and still applies the same schema validation. Other invalid JSON fails. Parse recovery is logged beside the raw response. No prompts, semantic settings, document choices or evaluation queries were changed for this recovery. Report original attempt spend plus newly paid continuation spend; cached generations cost zero in the continuation.
