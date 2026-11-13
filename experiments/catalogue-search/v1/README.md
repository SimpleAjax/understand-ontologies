# catalogue-v1

Extracted passages, BGE search, top five; no category filtering.

From the project root:

```powershell
.\.venv\Scripts\python.exe lab.py run catalogue-v1 --limit 5
```

This creates a new archived code bundle before running. Future behavior changes belong in a new version folder.

See `config.json`, `pipeline.py`, `prompt.txt` and `requirements.lock`. Shared implementation is explicitly pinned to `shared/v1`.
