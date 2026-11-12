# Frozen 20-contract retrieval experiment, v1

Scope: contract term, expiry, renewal, and termination qualifications. This is not a full-contract ontology or automated legal reasoning.

## Before selection and extraction

Freeze the existing six classes and relationship/property vocabulary from the five-contract model. Freeze this protocol before random selection. Use a random sample of 20 from the existing 100, seed 20261112, sorted candidate paths. Exclude every document path appearing anywhere in saved workbench/evaluation/comparison results and the five original examples. This exclusion audit reads paths only, not question or answer content. The log cannot prove that no person previously saw an unsaved question; call this previously unexposed according to available local artifacts, not independently blinded.

## Extraction instructions (document text only)

Read original contract text, using a document-wide topic scan and surrounding clauses to locate term, renewal, ending conditions, definitions and cross-references. Do not open benchmark question/answer files or use expected evidence positions. The coding assistant manually curates records from source-only previews; it is not a trained extraction model or independent legal review.

Use only Agreement, Party, Rule, Condition, Reference, SourcePassage and the frozen properties. Give each relevant provision a Rule with kind INITIAL_TERM, OPTIONAL_RENEWAL, AUTOMATIC_RENEWAL, POST_EXPIRY_CONTINUATION, TERMINATION or CONDITIONAL_REFERENCED_TERM. Represent different termination grounds as separately evidenced rules when practical. Preserve complex qualifications as exact source-backed descriptions rather than inventing executable logic. Evidence may span multiple sentences/paragraphs. Date and duration fields are optional: add them only when explicitly and unambiguously stated. No calculated end dates, guessed events, or facts derived from filing dates. Mark redactions, unresolved references and partial coverage. Party extraction is optional; do not guess identities from filenames. All modelled rules have exact source slices and file hashes. Link conditions and resolved references only when supported; do not imply that clauses are legally exhaustive.

Inspect document-wide topic hits before choosing passages. Topic scanning is an extraction aid, not proof of complete document understanding. Keep review notes and source-only previews. Do not revise ontology, extraction records, or selection after evaluation unlocks. Validate source hashes, offsets, quoted text, relationship types, and rule ownership. Seal graph, records, extraction code and retrieval code with SHA-256 hashes before reading test questions.

## Frozen retrieval and evaluation

The agreement and topic are explicitly provided, equally to both methods. Vector: original benchmark query plus existing BGE prefix, pinned local model, exact cosine within that agreement, top 5 candidates. Ontology: retrieve all term/renewal/termination rules attached to that agreement, their conditions and resolved section evidence, with INITIAL_TERM first and remaining rules in source order; no question-driven graph editing, LLM query routing or gold-based traversal. Both deduplicate source ranges then cap unique returned source text at 6000 Python characters, with possible mid-clause truncation reported. No answer-writing LLM.

After graph sealing only, unlock all questions for selected documents matching these predeclared topics: expiration date; renewal term; notice period required to terminate renewal. Do not cherry-pick questions by their outcomes. Report expiry as primary and all matched topics as secondary, per-question and per-document macro precision/recall, returned characters, retrieval time, and graph build/review effort. Score with unchanged pinned LegalBench-RAG character overlap on merged ranges. Gold may omit useful qualifications. Report excluded/unmatched questions and documents with no in-scope questions. Do not measure broad legal accuracy from these metrics.

The existing 100-document source preparation programmatically validated benchmark spans earlier; this experiment prevents answer content from entering new extraction, not a claim the benchmark files have never been processed. All twenty become evaluated development material after results are viewed; future tuning requires another batch for a fresh test.
