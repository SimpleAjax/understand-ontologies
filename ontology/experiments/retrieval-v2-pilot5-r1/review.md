# What the five-sample pilot tells us

**Implemented and tested on exactly five known development examples. The full benchmark was not run.**

The new pipeline searches original text as well as the catalogue, treats categories as preferences, lets local Qwen rerank a broader candidate set with surrounding context, resolves some section references and allows up to two follow-up retrieval rounds.

| Stage on these same five examples | Average evidence recall |
|---|---:|
| Previous ontology retrieval | 46.5% |
| Broader candidates, before Qwen reranking | 40.0% |
| After Qwen reranking | 78.8% |
| After section-link expansion | 78.8% |
| After bounded follow-up retrieval | 98.8% |

The descriptive stage scores show that simply collecting broader candidates did not help by itself. Reranking and the subsequent retrieval loop improved the final evidence coverage on these examples. Several changes are combined, so this is not a controlled estimate of each feature's isolated effect.

Four examples recovered all expected evidence. The fifth, source 2316, recovered 299 of 318 required characters: its first snippet was complete and its second was 85.6% covered. Three examples have multiple expected snippets; that alone does not establish genuine multi-hop reasoning.

The section resolver recorded 11 resolved and 19 unresolved reference occurrences across rounds, including repeated references. Those are not counts of unique links or useful evidence. Section-link expansion produced no recall improvement at the measured initial stage. Unique numbered headings can be resolved; other layouts, cross-document references and amendment precedence remain limited or unsupported.

## The cost of the improvement

Mean recorded new retrieval time was about **34 seconds per question**, including local Qwen work. This is much slower than the earlier embedding-only searches. The five samples involved 14 selector calls, one reused from cache after a retry, and 103,285 prompt-plus-output tokens as recorded across those calls. No paid API was used; local compute and labor are not priced.

These times exclude the failed GPU attempt. Cold setup numbers in `results.md` describe the final resumed process only. They are not complete end-to-end elapsed project time or a production latency benchmark.

One preflight attempt failed on conversion of a pgvector wrapper; it was corrected and regression-tested before any sample scoring. The final sample hit a GPU memory error; retrying the unchanged request with a fresh model runner succeeded, reusing the four saved samples and cached response. The model was unloaded afterward; downloaded weights were retained. See [runtime events](runtime-events.json).

## Validation and boundaries

- Seven focused tests passed, including actual pgvector wrapper conversion, soft filtering, two-hop section expansion, ambiguity and stopping limits.
- An independent overlap calculation matched all 20 new stage/question scores. Every output stayed within 6,000 unique source characters.
- All five retrievals were saved before the separate scoring command opened benchmark answers. Retrieval has a runtime guard against reading those answers and prior scored results.
- Original graph seals, frozen pilot code hashes, saved retrieval hashes and outcome hashes were verified.
- These five examples were chosen from known failures and a successful control. They are not random or unseen. Do not compare their 98.8% directly with the older 139-question average.
- Recall is evidence overlap, not correct legal answers. Final precision was 11.1%; extra context is still substantial. Qwen's sufficiency flag cannot establish that no hidden exception exists.
- Existing Turtle files were not rebuilt. The added surrounding context is used during query-time selection, not a new extraction run.

The implementation is promising for recovering missed evidence, but the current local LLM latency is expensive. Before a broader rollout, use fresh evaluation examples and test whether fewer or smaller selection calls preserve the gain. No broader run has been started.

[Per-sample results and queries](results.md) · [Full scored results](results.json) · [Independent audit](audit.json) · [Implementation guide](../../../retrieval-v2.md)
