# Two useful readings for graph search

Read these in order. The first makes graph querying concrete; the second shows how a system can search again for more evidence.

## 1. Start here: turn a question into a graph query

[Neo4j: Effortless RAG with Text2CypherRetriever](https://neo4j.com/blog/developer/effortless-rag-text2cypherretriever/)

The tutorial asks which movies Hugo Weaving acted in. It gives the LLM a **schema**: the kinds of things and relationships the graph contains, such as `Person`, `Movie` and `ACTED_IN`. The LLM produces a database query; the database executes it and returns matching movie records. The article includes code, the generated query and example results. It is a worked demonstration, not a measured recall benchmark. [Source](https://neo4j.com/blog/developer/effortless-rag-text2cypherretriever/)

```text
Question + description of graph structure
    → LLM writes graph query
    → database finds matching records
    → LLM explains the returned information
```

**What to notice:** describing the graph's structure is different from sending every individual rule or record to the LLM.

## 2. Then read: search again when more evidence is needed

[Microsoft Research: Introducing DRIFT Search](https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/), October 31, 2024.

DRIFT first finds relevant summaries of groups of graph information. It uses those summaries to generate follow-up questions, runs more focused searches and combines the findings. The article includes a process diagram and an example comparing the details found by different search methods. [Source](https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/)

**Reported result:** on more than 5,000 Associated Press news articles and 50 generated local questions, an LLM judge preferred DRIFT over GraphRAG Local Search for comprehensiveness 78% of the time and diversity 81% of the time. These are answer-preference results, not 78% recall or legal accuracy, and are not directly comparable to our contract experiment. [Source](https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/)

## A direction for our experiment

My interpretation: first test the simple question-to-query pattern on one contract, then consider follow-up searches. Neo4j uses Cypher; for our RDF/Turtle graphs, SPARQL is the analogous query language to investigate. That is a proposed direction, not an approach we have tested here, and it does not itself require migrating to Neo4j.
