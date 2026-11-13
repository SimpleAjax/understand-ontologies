# Inspect retrieval in Langfuse

The project uses Langfuse Cloud in the US region. Credentials are read from the ignored `.env` file; never put them in Python, documentation or commits.

## What you can inspect

One question is one trace. A batch groups its traces in one session. The trace contains:

- Contract and catalogue loading, with document identity and source hash.
- Every initial/follow-up query, BGE embedding, meaning-search ranking, keyword-search ranking and combined shortlist.
- The soft category preference and selected original passages.
- Every Qwen generation, including the exact system/user messages, response schema, model settings, parsed response and raw response text.
- Qwen input/output token counts and its reported input-reading, generation and loading durations.
- Explicit section resolutions, unresolved references, output character budget, stop reason and final source text.
- Precision, recall, full-evidence coverage, earlier ontology recall, intermediate-stage recalls and retrieval seconds as scores attached after retrieval completes.

The Langfuse dataset `cuad-retrieval-development-5` stores these five inputs and their expected evidence, linked to their source traces. They are known development examples, not fresh held-out results. No final legal answer is generated or judged.

## Cost labels

Generation cost is **actual paid model API spend**, explicitly $0 for local Ollama. Hardware and electricity are not priced. The separate `hosted_equivalent_estimate_usd` score and generation metadata estimate what the recorded tokens would cost at the documented hosted rate, without cache discounts. This is not an actual bill. The rate and its source are recorded alongside the estimate.

A full application-response cache hit consumes no new model tokens, so actual token usage is recorded as zero; the previous call's token counts/timings remain clearly labelled as source metadata. Fresh traced runs use a new response-cache directory to collect live timings.

## Run

Install the tracing SDK separately, preserving the older sealed requirements file:

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-langfuse.txt
& scripts/start-local-extractor.ps1
.venv/Scripts/python.exe scripts/run_langfuse_pilot.py --limit 5
```

The runner supports one to five of the existing pilot examples; it has no full-benchmark mode. It creates a timestamped ignored folder under `artifacts/langfuse-pilot5-*` with a Markdown report containing trace links. The local Qwen runner is unloaded between questions to limit GPU-memory growth, so load time can be part of each query. Existing source graphs and frozen retrieval code stay unchanged.

Before imports, the SDK loads these environment variables from `.env`:

```dotenv
LANGFUSE_SECRET_KEY=replace-locally
LANGFUSE_PUBLIC_KEY=replace-locally
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_HOST=https://us.cloud.langfuse.com
```

The SDK is pinned to `langfuse==5.2.0`. Integration files are `scripts/langfuse_retrieval.py` and `scripts/run_langfuse_pilot.py`. Meaning/keyword ranking is mirrored with tracing around each operation; a focused regression check verifies ranking parity. Every recorded Qwen payload is checked against the actual request fingerprint produced by the frozen selector.

## Verify the live export

Read the cloud data back using the Langfuse CLI:

```powershell
.venv/Scripts/python.exe scripts/audit_langfuse_pilot.py --run artifacts/<run-folder>
```

The audit checks every trace's hierarchy, question/final evidence, exact Qwen messages, model, tokens, explicit zero actual API cost, expected steps and scores. The report/readbacks are saved in the ignored run folder. Traces are private to the supplied project; this integration does not make them public.

Requests and passage text from these public benchmark contracts are sent to Langfuse for inspection; local model inference still runs on this machine. Secret credentials are excluded and masked. Langfuse's SDK adds the non-secret public project key to its own scope metadata; it is not application input/output. If keys have been shared in chat, rotate them in Langfuse and update `.env` locally.

## First verified live run

The first instrumented batch is [here](artifacts/langfuse-pilot5-20261113T081922Z/results.md). Its live readback verified 5 traces, 107 observations and 45 scores. The five-question development dataset was also read back successfully.

Fresh recall averaged 92.0%, versus 98.8% in the earlier frozen pilot. Source 269 changed from 100% to 65.9%. The first model request fingerprint was identical, but Qwen's response differed; the model was reset between questions in the new run. Both results are retained. This is observed repeatability variation, not proof that adding tracing caused the score change.
