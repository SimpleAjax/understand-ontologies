# Local vector search

## Try it in your browser

From this project folder, run:

```powershell
.venv/Scripts/python scripts/workbench.py
```

Open **http://127.0.0.1:8768**. Browse or search the 826 questions, optionally filter by contract, select a question, and click **Run this question**. Choose how many passages to retrieve (1–20). Each search uses all 100 contracts.

The workbench shows the exact BGE input, model/search settings, retrieved passages and source positions, expected evidence, precision/recall, and timings. Relevant portions are highlighted in green. Expected evidence is not passed into retrieval. Expand **Full request and result** or download the JSON to inspect a run. Results are saved under `artifacts/<ingestion_id>/workbench/`.

The server loads the pinned local model from its downloaded cache in the background at startup. The UI shows elapsed loading time and enables search when ready, using `/api/status`; searches reuse the model. Workbench loading uses `local_files_only=True`, so it does not wait for online model checks. A missing cache produces a visible readiness error; use the ingestion setup to download the model first. Startup model time is recorded separately from retrieval. This is a local tool bound to 127.0.0.1. Stop its terminal with Ctrl+C. A search scores just the selected question; it does not automatically run the question bank.

The workbench uses dark mode by default. After a search, **Where did the expected evidence rank?** shows the first overlapping chunk's position across the full ingestion, plus every chunk overlapping each marked passage. Each entry includes cosine distance, cosine similarity (`1 - distance`), evidence coverage, and whether it was returned inside your top-k limit. Expand an entry to read that indexed chunk. Ranking uses the same query vector and distance/ID ordering as retrieval; expected passages identify overlaps only after ranking. The diagnostic query's time is reported separately and does not change retrieval scores or the returned top-k chunks.

The implementation is in `scripts/pipeline.py`. It reads the frozen 100-document selection, makes source-preserving chunks, embeds them with local BGE on CPU, and saves them in PostgreSQL with pgvector.

## Setup

Use Python 3.12. From this folder in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set your local database password in `.env`. If `.env` is already configured, keep it. Credentials and generated data are ignored by Git.

PostgreSQL must have the **server extension** pgvector installed. Installing the Python `pgvector` package alone does not install that extension. See [Windows installation instructions](https://github.com/pgvector/pgvector#windows). pgvector 0.8.7 is now installed and enabled in the local project database, with the `rag_lab` tables ready. For another Windows installation, `scripts/install-pgvector.ps1` copies the compiled files from `artifacts/pgvector-v0.8.7/` and initializes the database; it requires Administrator PowerShell.

## Run

```powershell
# Preview chunks from one contract without writing to PostgreSQL:
.venv/Scripts/python scripts/pipeline.py preview --limit 1

# Create the dedicated database, extension, and project tables:
.venv/Scripts/python scripts/pipeline.py init-db

# Embed and save one document, then the full selected collection:
.venv/Scripts/python scripts/pipeline.py ingest --limit 1
.venv/Scripts/python scripts/pipeline.py ingest

# Use the ingestion_id printed by ingest:
.venv/Scripts/python scripts/pipeline.py search "When can the agreement be terminated?" --ingestion YOUR_ID
```

The initial run downloads BGE from Hugging Face. It then performs embedding on this computer. Model revision and installed library versions are saved in `artifacts/<ingestion_id>/config.json`. Pass `--revision REVISION` to explicitly reuse a downloaded model revision. Resolving an unspecified revision checks Hugging Face online.

Preview and ingestion save readable `chunks.jsonl` files and time/count reports. Changing the model revision, splitter settings, library versions, or manifest creates a separate ingestion ID. Each batch is committed; rerunning skips embeddings already saved under that ingestion. Keep the same settings and revision when resuming. Run only one ingestion process per configuration at a time.

Chunks contain at most 480 model tokens, with roughly 50 tokens of overlap. Splits prefer paragraph boundaries, then sentence boundaries, and fall back to token boundaries. The saved text is an exact source slice. Search uses normalized 384-dimensional vectors and exact cosine distance across the selected ingestion.

Search is available after partial ingestion for development; finish all 100 documents before comparing quality. The ingestion commands do not calculate benchmark precision/recall or send Langfuse traces. Local compute costs are recorded as unpriced; embedding API cost is zero.

## Score retrieval with LegalBench-RAG

The upstream source is pinned in `experiments/legalbenchrag-source.json`. Its checkout is ignored by this project's Git; recreate it with:

```powershell
git clone https://github.com/ZeroEntropy-AI/legalbenchrag.git vendor/legalbenchrag
git -C vendor/legalbenchrag checkout 431bc8f2488a81569ab7259fa633dcc50ab77f9a
```

The connector imports upstream `QAResult` directly, using our existing embeddings. It needs only upstream scoring dependencies, not the repo's full provider stack. It checks the checkout revision, source hashes, selected documents, and returned passage text before scoring.

Run **one question** (also the default):

```powershell
.venv/Scripts/python scripts/evaluate.py --ingestion d891bfe3634a5bf21d97 --limit 1
```

Use `--offset N` to choose a different question by its position in the saved selection. A future full run must explicitly use `--limit 0`; it is not run automatically.

Results go to `artifacts/<ingestion_id>/evaluations/<timestamp>/results.json` and `results.csv`. JSON includes the expected text, five raw retrieved chunks, merged source ranges used for scoring, upstream commit, precision/recall, and timings. Model load time is separate from query embedding and database search. Overlapping retrieved ranges are merged before passing them to the unchanged upstream scorer; this avoids counting the same evidence twice and is an explicit adaptation of its raw-chunk evaluation. One-question scores only confirm the connection works; they do not establish overall retrieval quality.

## Compare RAG with the small ontology

Open **http://127.0.0.1:8768**. The default mode is **RAG vs ontology · 20-contract batch**, exposing its 31 in-scope questions across 16 of the 20 selected contracts. Select a question, choose vector candidate count and character budget, then run a live comparison against the sealed graph. The UI also shows the first frozen run's recall for that question. Exploratory results go to `artifacts/<ingestion_id>/holdout20-live/`; they do not replace the first evaluation or alter the graph.

**RAG vs ontology · 5 original samples** retains the earlier pilot. **Original RAG · all questions** preserves the existing 826-question, 100-contract search and ranking diagnostics.

Comparison mode searches the same explicitly selected agreement with both methods:

- Vector RAG embeds the original question and retrieves cosine-ranked candidate chunks within that agreement.
- Ontology retrieval starts from its initial-term rule and follows incoming `qualifies` links to renewal, continuation, or termination rules. It collects their conditions, source passages, and linked section evidence. There is no LLM question router: the topic is explicitly fixed to term/expiry and linked qualifications.
- Both remove overlapping returned text and use the same maximum number of unique source characters. Vector ordering follows rank; graph ordering follows the initial rule and its qualification traversal. The last passage can be cut mid-clause by the budget, which the UI flags. This is a character cap, not a token cap; unused budget is not padded.

The UI shows collapsible source evidence, character precision/recall, retrieval time, text size, graph rules/paths, and unresolved references. Expected evidence is used only after retrieval for scoring and highlighting. Graph and model loading are outside query timings; scoring and formatting are excluded too. Ontology graph paths describe all candidates before budgeting, not a claim that every candidate passage was returned.

These five contracts were manually curated using development examples. Results demonstrate behavior, not general accuracy; useful qualifications may be absent from benchmark gold and reduce benchmark precision. No automatic qualification-completeness score or answer generation is included.

The server loads the five-example graph and verifies the twenty-contract experiment seal at startup. Five-example comparison JSON is saved under `artifacts/<ingestion_id>/comparisons/`, including graph hash, source ranges, settings, paths, and upstream scoring commit. The API is `POST /api/compare` with `question_index`, `top_k`, `character_budget` (500–20000), and `comparison_batch` (`holdout20` or `sample5`; defaults to `sample5` for existing callers). The question bank API exposes the eligible source IDs for both batches; unsupported questions are rejected. The sealed batch's extraction and original retrieval/evaluation code are unchanged; `holdout_workbench.py` adapts that graph for live exploration and display.

Focused graph/budget checks, without model inference:

```powershell
.venv/Scripts/python.exe -m unittest discover -s scripts -p test_compare_retrieval.py -v
```

## Frozen twenty-contract experiment

The first new batch is complete under [ontology/experiments/holdout20-v1/](ontology/experiments/holdout20-v1/). Start with [results.md](ontology/experiments/holdout20-v1/results.md) and the [first-run observations](ontology/experiments/holdout20-v1/analysis.md). The batch contains 20 randomly selected contracts and 53 rules. Its 31 in-scope questions come from 16 contracts; four selected contracts had no questions in the predeclared topic filter and were retained without replacement.

The vocabulary/instructions were frozen before selection; source-only extraction was built with benchmark-file reads blocked, then the graph and retrieval code were sealed before evaluation. Source records, exact quotations, protocol, selection/exclusion audit, graph hashes, unlock timestamp, JSON and CSV results are saved together. This is manual source-only curation, not automatic extraction or independently reviewed legal truth. Available saved exposure logs cannot establish complete historical blinding.

Primary expiry recall was 95.4% for ontology retrieval versus 52.0% for vector retrieval at the fixed top-5 / 6,000-character settings. Read the report for precision, speed, coverage, and the omitted Quality Agreement clause. The sealed graph is unchanged after viewing scores. The batch is now the workbench's default interactive comparison mode, with adjustable top-k/budget for separately saved exploratory runs.

Validate the stored graph and source-only traversal without reopening test questions:

```powershell
.venv/Scripts/python.exe scripts/holdout20.py validate
.venv/Scripts/python.exe -m unittest discover -s scripts -p test_holdout20.py -v
```

`scripts/holdout20.py` enforces build → seal → evaluation ordering, rejects rebuilding a sealed graph, and rejects a second evaluation of this experiment. Preserve these artifacts; use a new version/batch for future changes.
