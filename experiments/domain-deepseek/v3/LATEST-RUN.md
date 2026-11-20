# Latest broader-sample run

Completed run: `artifacts/experiment-runs/domain-deepseek-v3/20261115T115925068942Z-dc9f3f`.

20 additional randomly selected agreements, 151 eligible questions, 3,845 provisions, 489 quote-checked unreviewed added relationships. Forty Turtle files: one existing and one expanded graph per agreement. Source-only graph extraction and freeze preceded benchmark question selection. No local Qwen was used.

| Basis | Normal RAG recall | Existing ontology recall | Expanded ontology recall |
|---|---:|---:|---:|
| All 151 questions, failures included | 23.6% | 28.2% | 28.3% |
| Same 51 questions that the graph agent could process | 44.0% | 83.4% | 83.8% |

The unchanged 20,000-character rule-directory limit blocks 11 agreements containing 100 questions. Those questions return no graph evidence and remain in the denominator. The nine remaining agreements are a diagnostic subset, not the overall score. Successfully executed graph retrieval averaged 3.49 seconds existing / 3.29 seconds expanded, plus 1.35 / 1.53 seconds for answer generation. Normal RAG averaged 0.034 seconds for retrieval across the full cohort, excluding model setup.

Added relationships improved recall for two questions and reduced it for one; the remaining scores were unchanged. This does not establish that relationships are useless: it measures these particular unreviewed links and bounded agent tools. The next priority is to search/page the rule directory rather than require the whole index in one context, then rerun the same frozen graphs and questions.

Actual OpenRouter spend: $0.403755662, including $0.112152134 from the interrupted attempt and $0.291603528 from continuation. The first attempt failed on literal tab characters inside model JSON strings. The narrow, logged parser recovery preserves original values and raw responses, applies schema validation, and does not repair other invalid syntax. Continuation reused 120 exact source-only responses. No prompt, model, semantic limit or document selection changed for recovery.

Extraction continuation took 637.7 seconds and used 359 generation observations (including 120 reused responses). Query decisions and answers remain sequential; both graph variants evaluate all 151 questions. Costs, queries, response payloads and latencies are recorded in the run. Software/hardware setup, electricity and labor are not priced.

This is correct-agreement retrieval, not cross-document routing. Recall/precision measure benchmark character overlap, not factual/legal answer correctness. These documents may have appeared in older work and are not independently blind. Source preservation, quote validation and citation existence do not prove semantic completeness or relationship truth.

## Review and rerun

- [Full comparison](../../../artifacts/experiment-comparisons/random20-20261115T115925068942Z-dc9f3f.md)
- [Detailed comparison data](../../../artifacts/experiment-comparisons/random20-20261115T115925068942Z-dc9f3f.json)
- [Saved-output replay verification](../../../artifacts/experiment-comparisons/random20-replay-verification.json)
- [Langfuse, source and graph audit](../../../artifacts/experiment-comparisons/deepseek-inference-audit-20261115T115925068942Z-dc9f3f.json)
- [Existing Turtle files](../../../artifacts/experiment-runs/domain-deepseek-v3/20261115T115925068942Z-dc9f3f/graphs/)
- [Expanded Turtle files](../../../artifacts/experiment-runs/domain-deepseek-v3/20261115T115925068942Z-dc9f3f/variants/expanded/graphs/)

From the project folder:

```powershell
# Fresh inference on these same frozen graphs and questions; paid API calls.
.\.venv\Scripts\python.exe lab.py rerun artifacts/experiment-runs/domain-deepseek-v3/20261115T115925068942Z-dc9f3f

# Recalculate saved-output scores, without new model calls.
.\.venv\Scripts\python.exe lab.py replay artifacts/experiment-runs/domain-deepseek-v3/20261115T115925068942Z-dc9f3f --no-langfuse
```

Replay was executed and reproduced every question's metrics in both variants, with no model calls. The rerun cache-isolation behavior passed a focused regression test; another paid inference rerun was not performed. Archived code/prompt/dependency locks and request/response artifacts remain available. Rerunning requires the original corpus, model/provider availability, pinned Python dependencies and the original PostgreSQL ingestion. Current API output/timing can vary; saved-output replay is the deterministic score check.

Verification passed: 20 graph/source audits; unchanged base facts in every expanded graph; source offsets and quotation/citation existence; archive hashes; 302 cloud query traces and 2,114 scores; all 713 continuation generation observations with exact local/cloud cost reconciliation ($0.291603528, including 120 zero-cost cache observations). No configured API secret was found in archived files or cloud observations. Eight runner tests and four cohort/parser tests passed. These checks do not review semantic/legal correctness.

The archived per-variant `results.md` retains inherited ten-document boilerplate. This comparison and the archived `inputs.json`, `queries.json` and structured metrics describe the actual 20-document cohort. The live v3 renderer has been corrected for future runs; archived code and results were left unchanged.
