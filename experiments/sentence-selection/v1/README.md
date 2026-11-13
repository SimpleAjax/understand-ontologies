# sentence-selection-v1

Select exact sentence/clauses from FIXED saved agentic evidence, reading full paragraph context.

From the project root:

```powershell
.\.venv\Scripts\python.exe lab.py run sentence-selection-v1 --limit 5
```

This creates a new archived code bundle before running. Future behavior changes belong in a new version folder.

See `config.json`, `pipeline.py`, `prompt.txt` and `requirements.lock`. Shared implementation is explicitly pinned to `shared/v1`.

## General supporting-evidence prompt test — 2026-11-13

Updated v1 in place at the user's request. The prompt now asks for the direct answer plus useful supporting context across all supplied passages, without question-specific instructions. Earlier run snapshots remain unchanged.

Fresh test on the same five saved retrievals returned exactly the same passages: precision 59.3%, recall 80.4%, versus original untrimmed retrieval recall 98.8%. Source 1375 still loses the separate term clause. This prompt change did not fix the failure; no additional tuning was performed.

[Comparison report](../../../artifacts/experiment-comparisons/sentence-selection-v1-general-prompt-20261113/comparison.md).

Langfuse session: `sentence-selection-v1-20261113T115935817843Z-f44455`. Cloud readback verified five updated-prompt generations and 35 scores.
