# Five-contract ontology sample

Start with [v0.1/five-contracts.ttl](v0.1/five-contracts.ttl). This single Turtle file contains both our vocabulary and the five agreement examples from section 10 of `ontology-design.md`.

- `ct:` names our shared types and fields, such as `ct:Rule` and `ct:subject_to`.
- `ex:` names individual objects, such as `ex:A10` and `ex:Renewal10`.
- `a ct:Rule` means “this object is a Rule.”
- Multiple objects after `ct:has_rule` are the agreement's list of rules.
- `ct:kind` uses controlled string values. Conditions retain readable descriptions and source links; they are not executable legal logic.
- `ct:supported_by` points to a passage with its exact text, corpus-relative path, source-file SHA-256, and start/end character positions.
- `ct:resolved_to` means a passage is linked, not that every referenced provision or dependency has been resolved. `UNRESOLVED` references have no linked passage yet.

For example: `ex:A10` has `ex:InitialTerm10`; that rule is supported by `ex:P10a`. Rules such as `ex:Renewal10` point back to the initial rule using `ct:qualifies`, so retrieval must also follow incoming qualification links.

## What is included

Five agreements, ten named parties, thirteen term/renewal/termination rules, their conditions and references, and sixteen source passages. Eleven passages support rules; five opening passages support party identities. Each agreement is explicitly marked as a partial sample.

This is manually curated development data, not a full-contract extraction. Some definitions and other termination grounds are not modelled. Calendar dates are not fabricated for redacted or event-dependent terms. We record contract provisions, not whether a renewal, breach, termination, or other event actually happened. No PROV-O agent/activity model, graph database, or PostgreSQL changes are included.

## Rebuild or check

From the project folder, after installing `requirements.txt`:

```powershell
# Validate the saved Turtle and its evidence against the local source files.
.venv/Scripts/python.exe scripts/build_sample_ontology.py --check

# Regenerate Turtle from the manually curated records in this script.
.venv/Scripts/python.exe scripts/build_sample_ontology.py
```

The script is the editable source for this first sample; rebuilding overwrites the Turtle. It reads the five source documents directly, not benchmark answers. Validation checks graph types, rule ownership, source hashes, exact source slices, and redacted durations. It does not establish legal correctness or completeness.

## Try retrieval

The local workbench at http://127.0.0.1:8768 now has a **RAG vs ontology · 5 samples** mode. It retrieves the selected agreement's initial rule and incoming qualification links, then fetches original evidence. Inspect its paths, conditions, unresolved references, and passages beside the vector results. Both use the same selected agreement and unique-character cap. See the project README for comparison limits and saved results.
