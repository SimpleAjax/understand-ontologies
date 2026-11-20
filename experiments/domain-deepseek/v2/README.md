# Current domain inference: DeepSeek only

Use this version for graph querying and answer generation. Both use OpenRouter `deepseek/deepseek-v4.1-flash-1017`, pinned to `wafer/us`. No local Qwen server or model is required. The existing BGE/pgvector CPU path is only a comparison baseline.

This experiment reuses the ten frozen existing/expanded graph pairs from the previous DeepSeek extraction run. It does not pay for extraction again. Query prompts, graph facts, questions and navigation policy remain fixed; only the inference adapter/model and API output budget change.

```powershell
.\.venv\Scripts\python.exe lab.py run domain-deepseek-v2 --limit 10
```

[Latest results](../../../artifacts/experiment-comparisons/deepseek-only-inference-20261115.md): recall 87.9% on both graph sets, versus 67.9% with the previous local agent. Total reported inference cost across 20 question executions: $0.007437188. These are development results; see the report for precision, timing and limits.

Completed run: `artifacts/experiment-runs/domain-deepseek-v2/20261115T102230594077Z-4ac540`.

```powershell
# Re-execute API querying using frozen graphs and archived code.
.\.venv\Scripts\python.exe lab.py rerun artifacts/experiment-runs/domain-deepseek-v2/20261115T102230594077Z-4ac540

# Only reproduce saved scores, without API calls.
.\.venv\Scripts\python.exe lab.py replay artifacts/experiment-runs/domain-deepseek-v2/20261115T102230594077Z-4ac540 --no-langfuse
```

API credentials are loaded from ignored .env and never archived. Requests/responses and OpenRouter-reported usage/cost are preserved. Langfuse traces identify the API model and provider. Prior local-agent versions remain historical comparisons.
