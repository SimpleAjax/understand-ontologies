# Our first 100 documents

We will ingest **100 CUAD contracts** and search across all of them for each question.

CUAD gives us a varied set of contracts with existing questions and marked answer passages. The downloaded collection has 462 documents and 4,042 questions. ContractNLI has only 95 documents; MAUD has 134 local files; PrivacyQA has only 7. CUAD is a straightforward place to start our 100-document experiment.

## How we chose them

Randomly choose 100 from the sorted CUAD document list, using seed `42`. This makes the choice repeatable. We did not choose documents based on retrieval scores or cherry-pick easy questions.

The selection gives us **826 questions**, with all their expected passages inside these documents. The documents contain **5,318,316 characters** in total. These are pilot results to be measured later, not a representative score for all legal documents.

## What was checked

Every expected passage in all 4,042 CUAD questions matches its source text and character positions. One benchmark filename uses a different Unicode spelling of an accented letter; the selection script resolves it without renaming files or changing text. That document is outside this selected set.

## Files

- `selection.json`: the exact 100 document paths, file checksums, and selection settings.
- `questions.json`: the 826 matching questions and expected passages. `source_index` is the question's zero-based position in the original CUAD benchmark.
- `../../scripts/select_documents.py`: recreates the selection from the downloaded data.

From the project folder, run `python scripts/select_documents.py` to reproduce it. Treat the saved manifest as the fixed input for comparisons.

## Next

Read these 100 files directly from `data/corpus/cuad/`, split them into passages, and save their embeddings in PostgreSQL with pgvector. There is no need to copy or flatten the documents. No ingestion or embedding calls have been run yet. Before tuning retrieval settings, separate practice questions from the final test by document.
