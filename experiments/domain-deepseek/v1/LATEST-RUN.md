# Completed DeepSeek comparison

Run: `20261115T095703165091Z-08ab55`.

[Full A/B/C report](../../../artifacts/experiment-comparisons/deepseek-domain-20261115.md).

B: precision 41.0%, recall 67.9%. C: precision 38.0%, recall 67.9%. Prior A: precision 42.4%, recall 70.0%. API extraction cost $0.04877 plus $0.00083 canary. Both sets contain ten TTL files; the expanded set preserves all base nodes/facts. See report for caching, misses and limitations.

```powershell
# Rerun querying on frozen graphs, using archived code (local GPU).
& .\scripts\start-local-extractor.ps1
.\.venv\Scripts\python.exe lab.py rerun artifacts/experiment-runs/domain-deepseek-v1/20261115T095703165091Z-08ab55

# Replay saved scores only: no local inference or API extraction.
.\.venv\Scripts\python.exe lab.py replay artifacts/experiment-runs/domain-deepseek-v1/20261115T095703165091Z-08ab55 --no-langfuse
```

Verified no-model replay: `20261115T100618496415Z-68cf52`.
