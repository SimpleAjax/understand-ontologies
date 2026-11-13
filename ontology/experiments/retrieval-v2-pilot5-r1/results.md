# Five-sample retrieval pilot

**Five known development examples only. No whole-benchmark run. No changes to the 100 sealed graphs.**

We combined original-text vector search and keyword search, made categories preferences, used local Qwen for reranking with surrounding context, followed conservatively resolved section references and allowed two bounded follow-up search rounds. This tests query-time recovery; it does not rebuild the ontology.

| Stage | Mean precision | Mean recall | Full recall | Mean characters |
|---|---:|---:|---:|---:|
| previous_vector | 2.0% | 38.4% | 1/5 | 6000 |
| previous_catalogue | 1.8% | 41.6% | 2/5 | 2660 |
| previous_ontology | 9.8% | 46.5% | 1/5 | 2219 |
| soft_candidates | 2.0% | 40.0% | 2/5 | 6000 |
| llm_reranked | 10.5% | 78.8% | 3/5 | 4369 |
| section_links | 10.5% | 78.8% | 3/5 | 4369 |
| iterative | 11.1% | 98.8% | 4/5 | 3991 |

New retrieval mean: 34.41 seconds, including local LLM calls. Baseline timings are from an older run and not directly compared. Setup: 17.25s model loading; 0.68s passage embeddings. No paid API calls; local hardware and review costs are not priced.

| Source ID | Evidence snippets | Previous ontology recall | New final recall | New precision | Time |
|---|---:|---:|---:|---:|---:|
| 733 | 1 | 0.0% | 100.0% | 0.6% | 52.7s |
| 269 | 2 | 65.9% | 100.0% | 8.4% | 53.3s |
| 1375 | 2 | 8.1% | 100.0% | 34.5% | 15.5s |
| 2316 | 2 | 58.5% | 94.0% | 5.8% | 34.3s |
| 10 | 1 | 100.0% | 100.0% | 6.3% | 16.3s |

## Per-sample evidence and follow-up searches

### Source 733 (C096)

Consider the Global Master Supply Agreement between ExxonMobil Chemical Company and West Pharmaceutical Services, Inc.; What is the expiration date of this contract?

Final per-snippet coverage: 100.0%.
Stop: `no_new_queries` (model sufficiency is not verified).

- Round 0: Initial retrieval.
- Round 1: What is the specific expiration date or term end year mentioned in the Global Master Supply Agreement between ExxonMobil Chemical Company and West Pharmaceutical Services, Inc.? | Is there a defined term or period in the contract that specifies the end date of the 2019-2023 Global Master Supply Agreement?

[Source-only retrieval trace](sample-733-retrieval.json)

### Source 269 (C067)

Consider the Hosting Agreement between T-Mobile Netherlands B.V. and Elephant Talk Communication Holding AG; What is the renewal term for this contract?

Final per-snippet coverage: 100.0%, 100.0%.
Stop: `round_limit` (model sufficiency is not verified).

- Round 0: Initial retrieval.
  - Reference 18: resolved; selected span [54698, 54729]
  - Reference 17: unresolved
  - Reference 17.1: unresolved
  - Reference 19.3: resolved; selected span [58023, 59623]
  - Reference 3: unresolved
  - Reference 11: unresolved
  - Reference 15: resolved; selected span [48049, 48086]
  - Reference 18.1: resolved; selected span [54729, 55338]
  - Reference 11: unresolved
  - Reference 17: unresolved
  - Reference 9.2: unresolved
- Round 1: What is the duration of the initial term as defined in article 17.1 of the Hosting Agreement between T-Mobile Netherlands B.V. and Elephant Talk Communication Holding AG? | What is the length of the automatic extension period specified in the renewal clause of article 17.2 of the Hosting Agreement?
  - Reference 11: unresolved
  - Reference 17.1: unresolved
  - Reference 19.3: resolved; selected span [58023, 59623]
  - Reference 3: unresolved
  - Reference 17.1: unresolved
  - Reference 11: unresolved
  - Reference 11: unresolved
- Round 2: What is the specific duration of the automatic extension periods mentioned in article 17.2 of the Hosting Agreement between T-Mobile Netherlands B.V. and Elephant Talk Communication Holding AG? | What is the definition of the initial term as referenced in article 17.1 of the Hosting Agreement between T-Mobile Netherlands B.V. and Elephant Talk Communication Holding AG?
  - Reference 18: resolved; selected span [54698, 54729]
  - Reference 17: unresolved
  - Reference 17: unresolved
  - Reference 9.1.2: resolved; selected span [30038, 30324]
  - Reference 4.5: resolved; selected span [24205, 25164]
  - Reference 9.2.1: unresolved
  - Reference 9.2.2: resolved; selected span [31252, 31648]
  - Reference 17.1: unresolved
  - Reference 9.2: unresolved
  - Reference 4.4: unresolved
  - Reference 9.1.2: resolved
  - Reference 4.5: resolved

[Source-only retrieval trace](sample-269-retrieval.json)

### Source 1375 (C028)

Consider the Content Licensing Agreement between Data Call Technologies, Inc. and PLAN_B MEDIA AG; What is the expiration date of this contract?

Final per-snippet coverage: 100.0%, 100.0%.
Stop: `model_reports_sufficient_not_verified` (model sufficiency is not verified).

- Round 0: Initial retrieval.

[Source-only retrieval trace](sample-1375-retrieval.json)

### Source 2316 (C020)

Consider the Transportation Contract between JSC NOC KazakhOil and JSC Karakudukmunay for Crude Oil Export; What is the expiration date of this contract?

Final per-snippet coverage: 100.0%, 85.6%.
Stop: `no_new_queries` (model sufficiency is not verified).

- Round 0: Initial retrieval.
- Round 1: What is the Effective Date of the Offtake Agreement referenced in the contract? | What is the specific date of the fifth anniversary of the Offtake Agreement Effective Date?

[Source-only retrieval trace](sample-2316-retrieval.json)

### Source 10 (C034)

Consider the Video-on-Demand Content License Agreement between Rogers Cable Communications Inc. and EuroMedia Holdings Corp.; What is the expiration date of this contract?

Final per-snippet coverage: 100.0%.
Stop: `model_reports_sufficient_not_verified` (model sufficiency is not verified).

- Round 0: Initial retrieval.

[Source-only retrieval trace](sample-10-retrieval.json)

## Limits

- Five purposively selected known examples cannot establish general improvement. These scores are development feedback.
- Multiple gold snippets are not automatically multi-hop reasoning. No final legal answers were generated or scored.
- Reranking previews can be shortened. Full returned evidence always uses original text and offsets.
- Section resolution supports unique numbered headings. Ambiguous/missing references remain unresolved; cross-document amendments and precedence are not implemented.
- A model claiming evidence sufficiency does not prove all exceptions were found.
- Changes are combined; descriptive stage scores are not a controlled causal attribution.

[Full scored results](results.json) · [Frozen protocol](protocol.json) · [Sample selection](samples.json)
