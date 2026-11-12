# First-run observations — graph unchanged

These observations were written after evaluation. They do not alter the sealed graph, source records, protocol, or retrieval implementation.

## What ran

Twenty contracts were sampled with seed 20261112 from 88 candidates after excluding 12 paths found in existing development/search artifacts. The graph contains 20 agreement objects and 53 source-backed rules. Four selected contracts (H03, H07, H13, H14) have no questions matching the predeclared expiry/renewal/renewal-notice filter. They remain in the graph and selection; no replacement documents were drawn. The first evaluation scored 31 questions across the other 16 contracts, with 16 expiry questions as the primary set. Another 129 questions for these documents were outside the declared topic.

## The partial miss: H16 / Hemispherx

Expiry question 3746 requires two marked passages:

- Main agreement term, characters 15450–15583: three years with automatic two-year extensions.
- Quality Agreement term, characters 43785–44150: effective from the execution reference and continuing until termination or replacement by a revised Quality Agreement.

The source-only extraction included the first provision but omitted the Quality Agreement term in the exhibit. Ontology retrieval therefore covered 133 of 498 expected characters: **26.7% recall**. It returned all its candidate evidence within the budget, so this was an extraction/coverage omission rather than budget truncation. The source-only scan had surfaced the Quality Agreement wording, but it was not selected into the curated graph. That distinction matters: scanning a passage is not the same as modelling it.

A future development version could represent multiple agreement scopes within one source file and ensure exhibit terms are considered. This finding is now known, so fixing it and rerunning the same batch would be development progress, not a new unseen evaluation. No such fix has been made here.

## Why the high recall needs context

- All 31 vector outputs reached the 6,000-character cap. Three ontology outputs reached it, all for H12. These numbers depend on the chosen candidate count, ordering and text budget; a different budget is another experiment.
- H12's marked evidence was found even though some longer termination/wind-down evidence was cut off. Full benchmark recall does not prove that all useful qualifications reached the caller.
- Graph retrieval receives the selected agreement and a fixed term topic. It is a small, precomputed lookup, not arbitrary natural-language graph search. Vector retrieval receives the same agreement scope but must embed the question and rank chunks.
- Mean retrieval time excludes model/graph startup, source extraction, semantic review and materialization. Manual curation effort has not been priced or independently measured. The recorded protocol-to-seal wall time includes coding and validation.
- Source hashes and quotation checks establish traceability, not legal correctness. There has been no independent domain-expert review of these 53 rules.

## Leakage controls and their boundary

The protocol and schema were frozen before selection. Extraction read document text only. A Python audit-hook build blocked opens of question-bank and benchmark files and recorded zero attempted accesses. The graph, source records and retrieval code were hashed before `evaluation-unlock.json` was created, and their hashes still match after evaluation.

The exposure audit is based on available local saved results. It cannot prove that a user never previously viewed an unsaved question. Earlier corpus preparation also programmatically validated gold spans for the existing 100 documents. This is a source-only extraction test with an auditable ordering of steps, not a claim of an independently administered blind study.

See [results.md](results.md) for the measured scores, [graph.ttl](graph.ttl) for the unchanged graph, and [graph-lock.json](graph-lock.json) for the sealed inputs.
