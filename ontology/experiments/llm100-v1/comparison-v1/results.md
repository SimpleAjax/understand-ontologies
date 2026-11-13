# Three-way retrieval comparison

139 in-scope questions across 85 contracts. All 100 graphs remain unchanged.

**Scope:** the benchmark supplies the correct contract to every method. This is not a test of finding the contract across the corpus. Top 5 seeds/candidates, at most 6,000 unique source characters each. No answer-generation model is scored.

| Set | Method | Precision | Recall | Mean latency | Mean characters | Full recall |
|---|---|---:|---:|---:|---:|---:|
| all_in_scope | vector | 1.9% | 43.3% | 25.76 ms | 6000 | 56/139 |
| all_in_scope | catalogue | 7.3% | 66.7% | 23.37 ms | 3253 | 91/139 |
| all_in_scope | ontology | 11.2% | 80.9% | 24.10 ms | 3036 | 109/139 |
| expiry_primary | vector | 1.7% | 44.5% | 26.29 ms | 6000 | 36/84 |
| expiry_primary | catalogue | 6.8% | 68.0% | 23.47 ms | 3304 | 56/84 |
| expiry_primary | ontology | 9.7% | 78.1% | 24.18 ms | 3184 | 64/84 |
| development | vector | 1.7% | 39.9% | 25.51 ms | 6000 | 18/50 |
| development | catalogue | 7.0% | 66.2% | 22.64 ms | 3329 | 33/50 |
| development | ontology | 10.2% | 75.5% | 23.33 ms | 3175 | 37/50 |
| development_expiry | vector | 1.5% | 36.9% | 26.27 ms | 6000 | 9/28 |
| development_expiry | catalogue | 7.3% | 71.7% | 22.51 ms | 3332 | 20/28 |
| development_expiry | ontology | 8.1% | 68.1% | 23.32 ms | 3253 | 19/28 |
| not_in_known_exposure_artifacts | vector | 2.0% | 45.2% | 25.90 ms | 6000 | 38/89 |
| not_in_known_exposure_artifacts | catalogue | 7.4% | 67.0% | 23.78 ms | 3210 | 58/89 |
| not_in_known_exposure_artifacts | ontology | 11.8% | 84.0% | 24.53 ms | 2958 | 72/89 |
| not_in_known_exposure_artifacts_expiry | vector | 1.8% | 48.4% | 26.30 ms | 6000 | 27/56 |
| not_in_known_exposure_artifacts_expiry | catalogue | 6.5% | 66.2% | 23.95 ms | 3290 | 36/56 |
| not_in_known_exposure_artifacts_expiry | ontology | 10.5% | 83.1% | 24.62 ms | 3149 | 45/56 |

## What this establishes

Vector searches original chunks. Catalogue searches the extracted passages without graph semantics. Ontology first filters rule kinds from the question topic, ranks their evidence and follows supported condition/reference links.
Relationship traversal added evidence on 0 questions. An ontology gain here may come from category filtering, not multi-hop reasoning.

Precision and recall measure character overlap with benchmark evidence, not legal answer accuracy. Extra useful context can lower precision. Previously inspected documents are development; other documents are only absent from known exposure logs, not proven blind.

Cold setup excluded from query timings: graph parsing 1.13s; BGE loading 44.07s; extracted-passage embeddings 40.50s. 1 extracted passages exceeded the embedding model limit and were truncated for embedding only (original evidence retained). Query embedding is charged equally to all three methods; scoring and diagnostics are excluded. Single warm run, no significance claim.

Paid inference/embedding API spend: $0. Hardware, electricity, labor, extraction and review costs are not priced. The catalogue and ontology both require the same previously generated extraction; vector uses the existing ingestion. Extraction responses/metrics remain in artifacts/llm100-v1.

[Full question-level results](results.json) · [CSV](results.csv) · [Frozen protocol](protocol.json)

## Per-question inspection

| Source ID | Contract | Topic | Vector recall | Catalogue recall | Ontology recall |
|---|---|---|---:|---:|---:|
| 10 | C034 | expiry | 0.0% | 100.0% | 100.0% |
| 11 | C034 | renewal | 0.0% | 100.0% | 100.0% |
| 12 | C034 | renewal_notice | 0.0% | 100.0% | 100.0% |
| 30 | C040 | expiry | 0.0% | 100.0% | 100.0% |
| 31 | C040 | renewal | 0.0% | 100.0% | 100.0% |
| 32 | C040 | renewal_notice | 64.7% | 100.0% | 100.0% |
| 129 | C033 | expiry | 100.0% | 100.0% | 100.0% |
| 192 | C050 | expiry | 0.0% | 100.0% | 100.0% |
| 268 | C067 | expiry | 0.0% | 100.0% | 100.0% |
| 269 | C067 | renewal | 0.0% | 0.0% | 65.9% |
| 373 | C091 | expiry | 0.0% | 100.0% | 100.0% |
| 404 | C048 | expiry | 100.0% | 100.0% | 100.0% |
| 424 | C052 | expiry | 0.0% | 0.0% | 100.0% |
| 425 | C052 | renewal | 0.0% | 0.0% | 100.0% |
| 426 | C052 | renewal_notice | 0.0% | 0.0% | 100.0% |
| 512 | C037 | renewal | 100.0% | 100.0% | 100.0% |
| 513 | C037 | renewal_notice | 100.0% | 100.0% | 100.0% |
| 644 | C041 | expiry | 0.0% | 0.0% | 0.0% |
| 663 | C075 | expiry | 40.3% | 100.0% | 100.0% |
| 682 | C008 | expiry | 100.0% | 100.0% | 100.0% |
| 713 | C038 | expiry | 100.0% | 100.0% | 100.0% |
| 733 | C096 | expiry | 0.0% | 100.0% | 0.0% |
| 758 | C055 | expiry | 0.0% | 100.0% | 100.0% |
| 793 | C073 | expiry | 0.0% | 100.0% | 100.0% |
| 794 | C073 | renewal | 0.0% | 100.0% | 0.0% |
| 795 | C073 | renewal_notice | 0.0% | 100.0% | 100.0% |
| 838 | C047 | expiry | 100.0% | 100.0% | 100.0% |
| 889 | C056 | expiry | 100.0% | 100.0% | 100.0% |
| 890 | C056 | renewal | 100.0% | 100.0% | 100.0% |
| 976 | C024 | expiry | 100.0% | 100.0% | 100.0% |
| 982 | C029 | expiry | 100.0% | 0.0% | 0.0% |
| 1018 | C083 | expiry | 100.0% | 100.0% | 100.0% |
| 1019 | C083 | renewal | 0.0% | 100.0% | 100.0% |
| 1026 | C087 | expiry | 0.0% | 100.0% | 100.0% |
| 1048 | C088 | expiry | 100.0% | 100.0% | 100.0% |
| 1049 | C088 | renewal | 100.0% | 100.0% | 100.0% |
| 1050 | C088 | renewal_notice | 75.9% | 100.0% | 100.0% |
| 1071 | C018 | expiry | 100.0% | 100.0% | 100.0% |
| 1137 | C009 | expiry | 100.0% | 100.0% | 100.0% |
| 1138 | C009 | renewal | 100.0% | 100.0% | 100.0% |
| 1173 | C023 | expiry | 0.0% | 0.0% | 0.0% |
| 1174 | C023 | renewal | 0.0% | 0.0% | 100.0% |
| 1295 | C069 | expiry | 0.0% | 0.0% | 100.0% |
| 1375 | C028 | expiry | 91.9% | 8.1% | 8.1% |
| 1376 | C028 | renewal | 100.0% | 0.0% | 100.0% |
| 1377 | C028 | renewal_notice | 100.0% | 0.0% | 100.0% |
| 1393 | C049 | expiry | 0.0% | 100.0% | 100.0% |
| 1413 | C066 | expiry | 0.0% | 100.0% | 100.0% |
| 1414 | C066 | renewal | 0.0% | 100.0% | 100.0% |
| 1415 | C066 | renewal_notice | 100.0% | 100.0% | 100.0% |
| 1430 | C074 | expiry | 0.0% | 0.0% | 0.0% |
| 1431 | C074 | renewal | 100.0% | 100.0% | 100.0% |
| 1444 | C099 | expiry | 0.0% | 0.0% | 0.0% |
| 1445 | C099 | renewal | 0.0% | 100.0% | 100.0% |
| 1448 | C095 | expiry | 100.0% | 100.0% | 100.0% |
| 1456 | C082 | expiry | 100.0% | 100.0% | 100.0% |
| 1457 | C070 | expiry | 100.0% | 100.0% | 100.0% |
| 1567 | C068 | expiry | 100.0% | 100.0% | 100.0% |
| 1568 | C068 | renewal | 100.0% | 100.0% | 100.0% |
| 1619 | C078 | expiry | 100.0% | 100.0% | 100.0% |
| 1633 | C079 | expiry | 100.0% | 100.0% | 100.0% |
| 1634 | C079 | renewal | 0.0% | 100.0% | 100.0% |
| 1635 | C079 | renewal_notice | 100.0% | 100.0% | 100.0% |
| 1658 | C025 | expiry | 100.0% | 100.0% | 100.0% |
| 1686 | C022 | expiry | 0.0% | 100.0% | 100.0% |
| 1738 | C027 | expiry | 0.0% | 0.0% | 100.0% |
| 1739 | C027 | renewal | 0.0% | 100.0% | 100.0% |
| 1817 | C060 | expiry | 0.0% | 0.0% | 100.0% |
| 1823 | C063 | expiry | 100.0% | 100.0% | 100.0% |
| 1841 | C064 | expiry | 100.0% | 100.0% | 100.0% |
| 1861 | C094 | expiry | 0.0% | 0.0% | 0.0% |
| 1866 | C015 | expiry | 100.0% | 100.0% | 100.0% |
| 1875 | C072 | expiry | 100.0% | 100.0% | 100.0% |
| 1876 | C072 | renewal | 100.0% | 100.0% | 100.0% |
| 1995 | C046 | expiry | 100.0% | 100.0% | 100.0% |
| 2019 | C090 | expiry | 0.0% | 100.0% | 100.0% |
| 2035 | C017 | expiry | 0.0% | 0.0% | 100.0% |
| 2036 | C017 | renewal | 0.0% | 0.0% | 100.0% |
| 2037 | C017 | renewal_notice | 0.0% | 100.0% | 100.0% |
| 2059 | C030 | expiry | 100.0% | 100.0% | 100.0% |
| 2060 | C030 | renewal | 100.0% | 100.0% | 100.0% |
| 2159 | C007 | expiry | 100.0% | 100.0% | 100.0% |
| 2160 | C007 | renewal | 0.0% | 0.0% | 100.0% |
| 2161 | C007 | renewal_notice | 100.0% | 100.0% | 100.0% |
| 2198 | C011 | expiry | 0.0% | 100.0% | 100.0% |
| 2292 | C026 | expiry | 100.0% | 0.0% | 100.0% |
| 2316 | C020 | expiry | 100.0% | 0.0% | 58.5% |
| 2317 | C020 | renewal_notice | 100.0% | 0.0% | 55.2% |
| 2388 | C006 | expiry | 100.0% | 100.0% | 100.0% |
| 2429 | C077 | expiry | 100.0% | 100.0% | 100.0% |
| 2430 | C077 | renewal | 100.0% | 100.0% | 100.0% |
| 2431 | C077 | renewal_notice | 100.0% | 100.0% | 100.0% |
| 2437 | C005 | expiry | 100.0% | 100.0% | 100.0% |
| 2440 | C097 | expiry | 0.0% | 100.0% | 100.0% |
| 2562 | C035 | expiry | 100.0% | 100.0% | 100.0% |
| 2589 | C059 | expiry | 0.0% | 100.0% | 100.0% |
| 2590 | C059 | renewal | 0.0% | 100.0% | 100.0% |
| 2614 | C031 | expiry | 0.0% | 0.0% | 0.0% |
| 2615 | C031 | renewal | 0.0% | 0.0% | 100.0% |
| 2616 | C031 | renewal_notice | 0.0% | 0.0% | 100.0% |
| 2646 | C051 | expiry | 100.0% | 100.0% | 100.0% |
| 2647 | C051 | renewal | 0.0% | 100.0% | 100.0% |
| 2648 | C051 | renewal_notice | 100.0% | 0.0% | 0.0% |
| 2696 | C012 | expiry | 0.0% | 100.0% | 0.0% |
| 2736 | C021 | expiry | 0.0% | 100.0% | 100.0% |
| 2869 | C065 | expiry | 0.0% | 0.0% | 0.0% |
| 2870 | C065 | renewal | 0.0% | 100.0% | 100.0% |
| 2871 | C065 | renewal_notice | 0.0% | 100.0% | 100.0% |
| 2909 | C086 | expiry | 0.0% | 100.0% | 100.0% |
| 2910 | C086 | renewal | 100.0% | 100.0% | 100.0% |
| 2988 | C036 | expiry | 0.0% | 0.0% | 0.0% |
| 3042 | C019 | expiry | 0.0% | 0.0% | 0.0% |
| 3086 | C100 | expiry | 0.0% | 100.0% | 100.0% |
| 3104 | C001 | expiry | 0.0% | 100.0% | 100.0% |
| 3112 | C016 | expiry | 100.0% | 100.0% | 100.0% |
| 3113 | C016 | renewal | 100.0% | 100.0% | 100.0% |
| 3148 | C032 | expiry | 7.9% | 7.9% | 0.0% |
| 3149 | C032 | renewal | 0.0% | 100.0% | 100.0% |
| 3150 | C032 | renewal_notice | 0.0% | 0.0% | 0.0% |
| 3208 | C057 | expiry | 100.0% | 0.0% | 100.0% |
| 3209 | C057 | renewal | 0.0% | 0.0% | 100.0% |
| 3305 | C044 | expiry | 100.0% | 97.4% | 94.3% |
| 3336 | C084 | expiry | 0.0% | 0.0% | 100.0% |
| 3385 | C085 | expiry | 0.0% | 0.0% | 0.0% |
| 3393 | C002 | expiry | 0.0% | 0.0% | 0.0% |
| 3394 | C002 | renewal | 66.0% | 29.8% | 41.3% |
| 3473 | C014 | expiry | 0.0% | 0.0% | 0.0% |
| 3627 | C076 | expiry | 0.0% | 100.0% | 100.0% |
| 3746 | C043 | expiry | 0.0% | 0.0% | 0.0% |
| 3747 | C043 | renewal | 0.0% | 0.0% | 0.0% |
| 3748 | C043 | renewal_notice | 0.0% | 0.0% | 0.0% |
| 3893 | C013 | expiry | 0.0% | 100.0% | 100.0% |
| 3894 | C013 | renewal | 0.0% | 100.0% | 100.0% |
| 3895 | C013 | renewal_notice | 69.3% | 0.0% | 0.0% |
| 3933 | C089 | expiry | 0.0% | 100.0% | 100.0% |
| 3965 | C042 | expiry | 0.0% | 0.0% | 100.0% |
| 3966 | C042 | renewal | 0.0% | 28.5% | 28.5% |
| 3996 | C058 | expiry | 0.0% | 0.0% | 100.0% |
| 3997 | C058 | renewal | 0.0% | 0.0% | 100.0% |

## Independent score checks and remaining misses

An independent interval-overlap calculation matched all **417 method/question scores**, and every result respected the character budget. The frozen graph hashes still match. [Score audit](score-audit.md).

Ontology recall was incomplete on 30 questions. In 6, the extracted evidence did not contain all gold text; in 7, topic filtering removed relevant available evidence; in 22, ranking/top-5 or the character cap lost otherwise available evidence. These causes overlap. Do not change the extraction or retrieval using these scores and still call the same questions unseen.

The current result supports **extracting and categorizing useful passages**, with a measured gain over the original chunks. It does not demonstrate an advantage from graph relationship traversal: that added zero evidence. A category-filtered SQL catalogue could implement this measured behavior.
