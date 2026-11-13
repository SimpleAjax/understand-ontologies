# One local-LLM Turtle file per contract

Scope: the same 100 CUAD source documents already embedded in PostgreSQL. Extract contract term, renewal, termination and related qualifications; this is not a complete representation of every contract topic.

Unlike the earlier hand-curated examples, every document uses the same Qwen3 4B Instruct local extraction prompt, JSON schema, source segmentation, cue pattern and generation settings. The model runs through portable Ollama bound to `127.0.0.1:18765`. Runtime and downloaded models stay in ignored `artifacts/ollama/`. No contract text is sent to a cloud inference API.

## Files

- `manifest.json`: all 100 source paths/hashes, stable C001–C100 IDs, progress, errors and previous-exposure groups.
- `config.json`: model digest, frozen code/prompt/schema hashes and settings.
- `graphs/C001.ttl` … `graphs/C100.ttl`: one independently readable Turtle file per source document, including vocabulary, proposed rules/conditions/references and exact original passages.
- `records/C001.json` …: accepted model proposals and rejected outputs with reasons.
- `extraction-instructions.txt`, `response-schema.json`, `schema.ttl`: the fixed extraction inputs.
- `graph-lock.json`: generated only after all 100 files complete and validate, before a new evaluation.
- `artifacts/llm100-v1/responses/` and `metrics/`: resumable raw responses and generation timings/token counts. These are outside this folder and ignored by Git.

All generated rules and conditions are **UNREVIEWED**. Exact-text validation establishes that quoted evidence exists; it does not prove that the model correctly interpreted the text or included every exception. This first automatic version is a lightweight clause ontology: the model assigns rule categories and condition evidence IDs, while Python copies source passages and detects explicit section-reference strings. It does not generate interpreted date/duration/scope facts or free-form legal summaries. Those values remain in the original passages. Section references remain explicitly unresolved. No blanket qualification links are manufactured between rules.

## How source text reaches the model

The code scans the entire document for a frozen set of term/renewal/termination cues. Each matching source unit is sent in a separate model call, using its source ID rather than benchmark evidence positions. The single-unit approach prevents the model from assigning one passage's details to a different passage in a shared batch. It also limits context: relevant clauses with unfamiliar wording or dependencies spanning units can be missed. Per-document coverage counts describe text inspected, not semantic accuracy. Exhibit and service-specific terms are included in the instructions; their scope remains in their original text.

The process blocks opens of benchmark/question files during extraction. It rejects unknown evidence IDs; the response schema does not allow model-written dates or quoted fact fields. Python copies the exact source text itself and checks the resulting Turtle offsets and file hashes. Responses are cached using model digest and request content. Completed files are not regenerated on resume. A frozen `code-snapshot.py` preserves the exact implementation alongside its hash.

## Run and inspect

From the project root, with portable Ollama and the model downloaded:

```powershell
& scripts/start-local-extractor.ps1
.venv/Scripts/python.exe scripts/local_ontology.py init
.venv/Scripts/python.exe scripts/local_ontology.py extract
.venv/Scripts/python.exe scripts/local_ontology.py status
.venv/Scripts/python.exe scripts/local_ontology.py validate
.venv/Scripts/python.exe scripts/local_ontology.py seal
```

The separate `llm100-pilot*` runs document source-only smoke tests on an already inspected development contract. The 3B/large-batch variants were not accepted for production. The final single-unit Qwen3 4B pilot recovered the main term, optional renewal and continuation passages and ignored the inspected marketing and periodic-payment examples. This is a limited source/behavior check, not full legal validation. Any prompt/settings changes happen before production initialization; later changes require a new version.

The manifest marks documents used in earlier curated graphs or saved search artifacts as development. Other documents are only “not found in known exposure artifacts”; this does not prove complete historical blinding or rule out public-data exposure during model training. Evaluate those groups separately. Previously evaluated examples must not be reported as a fresh unseen test.

No new benchmark evaluation is part of generating these files. Once they are complete and sealed, compare vector RAG, a flat passage catalogue, and question-directed graph retrieval; include extraction effort, precision, recall and end-to-end time. Keep the earlier frozen experiment unchanged.
