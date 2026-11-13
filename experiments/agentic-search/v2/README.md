# agentic-v2

Fresh hybrid search, soft categories, Qwen reranking, section lookup and bounded follow-up.

From the project root:

```powershell
.\.venv\Scripts\python.exe lab.py run agentic-v2 --limit 5
```

This creates a new archived code bundle before running. Future behavior changes belong in a new version folder.

See `config.json`, `pipeline.py`, `prompt.txt` and `requirements.lock`. Shared implementation is explicitly pinned to `shared/v1`.
