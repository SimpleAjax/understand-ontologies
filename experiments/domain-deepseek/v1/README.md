# DeepSeek extraction: controlled model and relationship comparison

Three conditions share the same ten short development agreements and ten fixed questions:

| Condition | Extraction | Graph design | Query/answer agent |
|---|---|---|---|
| A, saved baseline | Local quantized Qwen 4B | Existing domain graph | Local Qwen 4B |
| B, `graphs/` | DeepSeek V4.1 Flash 1017 through OpenRouter | Same extraction prompts, source segmentation, provision schema and old link screen | Same local Qwen 4B |
| C, `variants/expanded/graphs/` | Reuses B's exact base nodes and facts | Additional source-supported relationships | Same local Qwen 4B |

B versus A measures the extraction-model/provider change under the existing design. C versus B measures the expanded relationship-building package: extra predicates, a whole-document linking pass, exact-quotation screening and traversal of those additional links. It does not isolate the effect of each individual predicate or prove the semantic truth of a relationship. C never re-extracts or changes B's provisions, actors, targets, conditions or quotations; only graph edges and relationship-review metadata are added. Missing business nodes remain explicit limitations.

New relationships cover conditions, exceptions, preventing renewal, notice applicability, amendments, survival and incorporation. The original graph remains a subset of C. Exact quotes validate source traceability, not the interpretation of the relationship; proposed edges remain unreviewed.

## Provider and cost

`deepseek/deepseek-v4.1-flash-1017`, pinned to `wafer/us`, with provider fallback disabled and structured JSON output required. Reasoning is disabled. Exact requests/responses, provider name, generation IDs, input/output tokens and OpenRouter-reported cost are preserved. The credential is read from ignored `.env`, never copied into the archived code or model request artifacts. The per-run reservation ceiling is $2; actual costs are read from responses. The separate canary is not included in run build totals.

Three source documents run concurrently in a thread pool. A single source-only file-access guard covers the pool. Each worker has its own call log and document trace. Both B and C are built and frozen before any benchmark read. The ten questions must match the saved A cohort exactly. No question-specific extraction prompts or score-based fallbacks are used.

The local query agent is intentionally unchanged. API extraction does not use the local GPU; querying/answering still does. Queries run sequentially on the single GPU. B and C share an exact-request local response cache: identical requests reuse the same response, helping control model variation. C's elapsed times can therefore include cache hits and must not be presented as fresh-inference speed improvements. Per-call cache flags and actual Langfuse usage are recorded. Query caps, evidence budget, prompts and graph tools remain fixed except for additional relationships exposed in C.

## Run and reproduce

```powershell
& .\scripts\start-local-extractor.ps1
.\.venv\Scripts\python.exe lab.py run domain-deepseek-v1 --limit 10
.\.venv\Scripts\python.exe -m unittest discover -s experiments/domain-deepseek/v1/tests -v
```

Fresh run rebuilds both variants. Completed-run `lab.py rerun <run-folder>` uses the original archived code and frozen B/C graphs, re-executing local queries without paid extraction. `lab.py replay <run-folder> --no-langfuse` copies the saved run and uses its archived engine and scorer to recompute B/C metrics without any inference. The replay driver itself is copied into the new run and hashed in its run lock. Earlier runs remain intact.

Artifacts include code/dependency snapshots, B/C graphs, source hashes, graph locks, extraction access audit, per-document API usage, exact requests/responses, local agent graph steps and answers, Langfuse traces, individual metrics and `comparison.json`. Evidence metrics are character overlap; generated legal-answer correctness requires separate review. Correct agreement is supplied, so this experiment does not test corpus-wide document routing. Source layer coverage is not proof of extraction completeness.
