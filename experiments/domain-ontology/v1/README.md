# Domain ontology + graph-only agent: ten agreements

This experiment asks: can a source-backed model of actors, actions, permissions, obligations and qualifications retrieve useful evidence without RAG or raw-document search?

## Flow

```text
10 short source agreements (selected without benchmark access)
    Ã¢â€ â€œ fixed local Qwen prompt over every source segment
Provisions + actors/targets + conditions/exceptions + source positions
    Ã¢â€ â€œ source-only pass proposing cross-provision relationships
One TTL graph per agreement, with all source passages preserved
    Ã¢â€ â€œ validate + freeze graph hashes
Choose one benchmark question per agreement using a fixed seed
    Ã¢â€ â€œ correct agreement supplied, matching earlier comparison scope
Qwen chooses provision IDs from the graph directory
    Ã¢â€ â€œ graph tool follows named relationships and returns quotations
Bounded inspect/finish loop, at most 3 agent calls
    Ã¢â€ â€œ common 6,000-character returned evidence budget
Qwen generates a cited answer from returned evidence
    Ã¢â€ â€œ save ALL retrievals and answers
Separate evaluation + fresh normal-RAG comparator
```

## Files

- `pipeline.py`: extraction, graph construction, tools, bounded agent, answer and evaluation.
- `prompt.txt`: general full-domain extraction instructions, no question-specific cues.
- `relations-prompt.txt`: source-backed proposed connections, not topic similarity.
- `search-prompt.txt`: graph-only inspection/selection.
- `answer-prompt.txt`: answer from supplied quotations, with uncertainty.
- `config.json`: model/digest, input/response budgets, agent limits and deterministic sampling.
- `run.py`, dependency locks and tests: independent runnable archived experiment.
- `datasets/domain-10/source-manifest.json`: ten source contracts and selection explanation.

The design follows the PreCheck domain draft but uses the same automatic extraction process for all ten, including PreCheck. It does not import its handcrafted assertions, old category graphs or benchmark answers.

The graph schema distinguishes provisions by modality, actor and target entities, conditions, exceptions, time/scope qualifications, source passages and unresolved references. Relationship types include `qualifies`, `exception_to`, `applies_after`, `requires` and `references`. Labels and action descriptions remain natural language: Qwen maps questions to these labels. No universal action taxonomy or OWL legal inference engine is claimed. Typed entities can be shared within an agreement by exact normalized label/type; cross-document entity resolution is not implemented.

Every non-whitespace source character is retained in graph source passages. That is source-layer coverage, not proof that every meaning or relationship was extracted. Only evidence connected to modeled provisions is exposed by the agent tools. Extracted statements and cross-provision links remain unreviewed.

## Scope and measurement

- Ten shortest sources by word count in the existing 100, excluding the identified amendment C039 and mid-document extract C093. Includes PreCheck. This is development data, not random or held-out.
- One randomly selected question per agreement after graph freeze, seed 20261115. All available benchmark task topics are eligible; no topic filtering for good scores.
- Correct agreement supplied to graph search and vector baseline. Finding the correct agreement across all ten is not measured in this first experiment.
- Graph-only query tools: inspect provision IDs; follow explicit named rule links one hop in either direction; fetch attached conditions and original quotations. No cosine, BM25, grep, raw-file tool or old results as fallback.
- At most 3 graph-agent calls, 5 inspected IDs/call and 6 linked neighbors/seed. A directory or response that exceeds the context cap fails explicitly. Finite graph expansion does not establish completeness.
- Precision, recall, exact returned characters, full-recall count, modeled-evidence coverage ceiling, retrieval time, answer time, extraction time, calls/tokens and actual paid API spend.
- Fresh normal-RAG comparator: same question/agreement, existing BGE+pgvector ingestion, top 5 and 6,000-character budget. It runs only after graph answers have been saved and never feeds the graph agent.
- Answer citation IDs are validated. Benchmark evidence scoring does not grade generated answer accuracy, legal correctness or all exceptions; human review remains necessary.
- Local API spend is zero. Electricity, hardware, labor and review are not priced; no current hosted-cost estimate is asserted.

## Commands

From the project root:

```powershell
& .\scripts\start-local-extractor.ps1
.\.venv\Scripts\python.exe lab.py check domain-ontology-v1
.\.venv\Scripts\python.exe lab.py run domain-ontology-v1 --limit 10
```

Omit `--limit` to use ten agreements. `--limit 1` is a smaller smoke run. The earlier five-question experiments retain their own cap of five.

Fresh runs build and seal new graphs. Archived `rerun` reuses that run's frozen graphs and re-executes querying/answering with its archived prompts and settings; it does not silently re-extract them. Use a fresh run to test extraction variation. `replay` only rescores saved outputs and records no fresh latency.

```powershell
.\.venv\Scripts\python.exe lab.py rerun <completed-run-folder>
.\.venv\Scripts\python.exe lab.py replay <completed-run-folder> --no-langfuse
.\.venv\Scripts\python.exe lab.py compare <matched-run-A> <matched-run-B>
.\.venv\Scripts\python.exe -m unittest discover -s experiments/domain-ontology/v1/tests -v
```

Each new run archives this code, prompts, dependency locks, dataset selection and scorer. Its `graphs/` folder contains TTL and extraction records; `responses/` retains exact requests/responses; `graph-lock.json` freezes extraction before question selection; `audits/` records graph-only access; `results.md` summarizes the comparison. Model identity includes the local runtime version.

Langfuse uses separate extraction and query sessions, one root trace per document/query, with individual generations and graph-tool inputs/results nested below. `--no-langfuse` retains all local artifacts while disabling export.


## Relationship screening

The first source-only smoke graph exposed incorrect cross-provision links from local Qwen despite valid JSON/Turtle. Raw proposed links are retained as review objects. Only links whose source has a predicate-appropriate textual cue and whose endpoints share source evidence or an explicit numbered cross-reference become traversable. An `applies_after` link additionally requires a termination/expiry target description. This conservative screen can reject useful true links and does not prove semantic correctness of accepted ones. Conditions attached directly to a provision remain available independently.

The graph records `traversable` and `screeningStatus` on proposed relationships. Reports separate proposed from traversable link counts. Unsupported links are not silently treated as facts available to the search tool.

`--extraction-cache <prior-local-run-folder>` explicitly reuses only source-only extraction responses after checking exact model request equality. It does not reuse queries, answers or scores. Cache-hit usage is separately recorded. This avoids repeating successful extraction calls after an implementation failure; it is not evidence of faster fresh extraction.

Use `analyze_paths.py <completed-run-folder>` for a no-model-call diagnostic of which additional passages came from relationship expansion. It is not a counterfactual evaluation or proof of causal recall improvement.


## Context/output limits

Dense source extraction uses a 4,096 output-token cap for new calls; exact older successful requests can be reused from the explicit cache. Truncated responses are saved and rejected, with at most one larger-budget attempt. Calls and tokens from failed/truncated attempts remain recorded.

The cross-provision pass first uses full records. Above 30,000 input-data characters it removes repeated actor/target/condition metadata but retains every provision ID/meaning and every original quotation. If the compact data still exceeds that bound, the pass is explicitly skipped and the limitation is recorded; direct provision/condition/source modeling remains available. This is a conservative local-model context bound, not a complete relationship extractor.
