# Score and failure audit

Independent interval-intersection calculation matched precision and recall on all 417 method/question results. Every result respected the 6,000-character cap; all sealed graph hashes still match.

Ontology had incomplete recall on 30 questions. Causes below can overlap:

- gold_not_fully_present_in_extracted_evidence: 6 questions
- ranking_top5_or_character_budget_loses_available_gold: 22 questions
- topic_kind_filter_removes_gold_evidence: 7 questions

These labels compare gold spans against available source evidence after scoring; they do not change retrieval or validate legal interpretations. See [detailed diagnostics](score-audit.json).
