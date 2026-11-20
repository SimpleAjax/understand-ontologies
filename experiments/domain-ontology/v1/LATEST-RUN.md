# Completed ten-agreement run

Run: `20261115T064313020578Z-3ffb82`.

[Results and limitations](../../../artifacts/experiment-comparisons/domain-conclusions-20261115.md) · [Ten Turtle files](../../../artifacts/experiment-runs/domain-ontology-v1/20261115T064313020578Z-3ffb82/graphs/).

Graph precision 42.4%, recall 70.0%; normal-RAG precision 2.1%, recall 72.6%. One question per short development agreement; correct agreement supplied. No evidence yet of added multi-hop benefit. See the conclusions for misses, build costs and verified boundaries.

```powershell
# Fresh graph-only queries/answers using this run's FROZEN graphs and code.
& .\scripts\start-local-extractor.ps1
.\.venv\Scripts\python.exe lab.py rerun artifacts/experiment-runs/domain-ontology-v1/20261115T064313020578Z-3ffb82

# Reproduce only the saved evidence scores; no GPU inference.
.\.venv\Scripts\python.exe lab.py replay artifacts/experiment-runs/domain-ontology-v1/20261115T064313020578Z-3ffb82 --no-langfuse
```

A new `run domain-ontology-v1 --limit 10` also rebuilds graphs. All versions preserve their own prompts and implementation snapshots.
