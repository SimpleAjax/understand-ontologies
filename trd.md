# Technical plan: our first vector search

Status: Pipeline implemented in `scripts/pipeline.py`; pgvector 0.8.7 is installed and enabled in the project database. See `README.md` for commands.

## What we are building

Prepare our selected **100 CUAD contracts** for local search. They already have **826 matching test questions**. Read the document list from `experiments/cuad-100/selection.json`; keep that selection fixed. It supersedes the PRD's earlier suggestion to take the first 100 sorted files.

```mermaid
flowchart LR
    A[100 selected contracts] --> B[Split into chunks]
    B --> C[Local BGE embedding model]
    C --> D[(PostgreSQL with pgvector)]
    classDef source fill:#153728,stroke:#4ADE80,color:#FFFFFF
    classDef process fill:#142D50,stroke:#60A5FA,color:#FFFFFF
    classDef storage fill:#3C3014,stroke:#FBBF24,color:#FFFFFF
    class A source
    class B,C process
    class D storage
```

## 1. Chunking: fixed rules in Python

**Decision:** use recursive splitting. Prefer paragraph breaks, then sentence boundaries where possible, then smaller pieces when necessary.

| Setting | Starting choice |
| --- | --- |
| Maximum chunk text | 480 tokens, including any repeated overlap |
| Overlap | Target about 50 tokens from the previous chunk |
| Token counting | Use the embedding model's own tokenizer |
| Source text | Preserve it; save each chunk's original start/end character positions |

The 480-token cap replaces our earlier 512-token suggestion. Our embedding model accepts 512 tokens total, so this leaves room for special tokens. Check the final encoded length rather than silently cutting off text.

Overlap repeats a little text so a boundary is less likely to separate useful context. It is a starting setting to test, not a proven optimum.

No LLM is needed for splitting. With the same text, tokenizer, rules, and settings, the chunk boundaries should repeat exactly. Use an existing splitter where it preserves exact source spans; check that every chunk equals its original text slice. Read UTF-8 with the same newline handling used in our selection script.

Reference: [recursive splitting guide](https://docs.langchain.com/oss/python/integrations/splitters/recursive_text_splitter).

## 2. Embeddings: run BGE locally

**Decision:** `BAAI/bge-small-en-v1.5`, using Python's Sentence Transformers library on CPU first.

Why: it supports English retrieval, is lightweight enough to start on CPU, and produces **384 numbers per chunk**. Once the model is downloaded, embedding runs locally without an embedding API charge. Local processing still consumes machine time and electricity.

Embed in batches and save the results so restarting does not require embedding completed chunks again. Record the exact model revision and library versions. Normalize vectors consistently and use the same model and settings for questions. Follow the model's documented query formatting when adding search.

This is our baseline model; we have not measured its accuracy on these contracts yet.

Reference: [BGE model documentation](https://huggingface.co/BAAI/bge-small-en-v1.5).

## 3. Storage: PostgreSQL with pgvector

**Decision:** use a local PostgreSQL database with the pgvector extension. Store each embedding in a `vector(384)` column.

For each chunk, save:

- A repeatable chunk ID and the ingestion version it belongs to.
- Original document path, chunk text, and start/end character positions.
- Embedding, model revision, and chunking settings.

Repeating the same ingestion must reuse or update those chunk records rather than duplicate them. Keep different chunking/model experiments separate so search cannot mix their vectors.

**Search starts with exact cosine-distance search**, returning five chunks from all 100 documents. Later, compare HNSW indexing against this reference. HNSW can make searching faster while missing some nearest vectors; it does not require regenerating unchanged embeddings.

Reference: [pgvector indexing documentation](https://github.com/pgvector/pgvector#indexing).

## 4. First implementation order

1. Set up an isolated Python environment, download the model, and make PostgreSQL with pgvector available.
2. Preview chunks from a few contracts. Check boundaries, token limits, source positions, and full text coverage before embedding all 100.
3. Run one contract through chunking, embedding, and saving. Restart it and check that no duplicate rows appear.
4. Process all 100 documents. Record document/chunk counts, preparation time, failures, and database size.
5. Embed one question and return five passages with their source locations.

That completes the first searchable vector space. Benchmark scoring comes next, using the saved questions. Before tuning settings, separate practice and final-test questions by document. Langfuse can be added for viewing timings and results; it is not required to build the vector space.
