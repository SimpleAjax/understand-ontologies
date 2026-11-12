# Twenty-contract retrieval results

Questions: 31 in scope; 16 expiry questions (primary).

Same selected agreement, top-5 vector candidates, maximum 6,000 unique source characters per method. Graph sealed before benchmark unlock.

| Set | Method | Precision | Recall | Mean retrieval | Mean characters | Full recall |
| --- | --- | --- | --- | --- | --- | --- |
| Expiry (primary) | vector | 1.7% | 52.0% | 35.09 ms | 6000 | 7/16 |
| Expiry (primary) | ontology | 14.3% | 95.4% | 0.54 ms | 2315 | 15/16 |
| All in scope | vector | 2.1% | 55.9% | 32.21 ms | 6000 | 16/31 |
| All in scope | ontology | 15.9% | 97.6% | 0.55 ms | 2442 | 30/31 |

## Per-document results

| Document | Questions | Vector recall | Ontology recall |
| --- | --- | --- | --- |
| H01 | 3 | 97.3% | 100.0% |
| H02 | 2 | 100.0% | 100.0% |
| H03 | 0 | N/A | N/A |
| H04 | 1 | 100.0% | 100.0% |
| H05 | 1 | 0.0% | 100.0% |
| H06 | 1 | 100.0% | 100.0% |
| H07 | 0 | N/A | N/A |
| H08 | 3 | 66.7% | 100.0% |
| H09 | 1 | 100.0% | 100.0% |
| H10 | 3 | 33.3% | 100.0% |
| H11 | 3 | 100.0% | 100.0% |
| H12 | 3 | 0.0% | 100.0% |
| H13 | 0 | N/A | N/A |
| H14 | 0 | N/A | N/A |
| H15 | 2 | 50.0% | 100.0% |
| H16 | 3 | 0.0% | 75.6% |
| H17 | 1 | 0.0% | 100.0% |
| H18 | 1 | 40.3% | 100.0% |
| H19 | 1 | 0.0% | 100.0% |
| H20 | 2 | 100.0% | 100.0% |

## Effort and limitations

Protocol-to-graph-seal elapsed time: 6.9 minutes, including coding, extraction and validation. This is not measured human extraction labor. Model loading (17.48 s) is excluded from query timings. Ontology query timing excludes graph parsing and validation; vector timing includes query embedding and SQL search. Source reading, materialization, review and storage costs are not priced. No paid embedding/extraction API used.

- Manual source-only extraction, not independent legal review.
- Available exposure logs do not prove complete historical blinding.
- Programmatic source preparation had previously validated benchmark spans.
- Same-agreement, fixed-topic retrieval; no automatic entity/topic routing.
- Partial contract coverage and benchmark gold may omit qualifications.
- No changes to sealed extraction or retrieval after unlocking.

The graph is unchanged after viewing scores. This batch is now evaluated development material. A new batch is required to evaluate any changes made in response to these results.

Files: [protocol](protocol.md), [selection](selection.json), [Turtle graph](graph.ttl), [source-only records](records.json), [graph seal](graph-lock.json), [unlock record](evaluation-unlock.json), [full results](results.json), [CSV](results.csv).
