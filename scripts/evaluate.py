"""Score existing pgvector retrieval with LegalBench-RAG. Defaults to ONE question."""

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

from pgvector.psycopg import register_vector
from pipeline import ROOT, MODEL, QUERY_PREFIX, connect, digest, load_model


def upstream():
    lock = json.loads((ROOT / 'experiments/legalbenchrag-source.json').read_text())
    path = ROOT / lock['checkout']
    if not path.is_dir():
        raise RuntimeError('Clone the pinned LegalBench-RAG checkout first; see README.md.')
    commit = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != lock['commit']:
        raise RuntimeError('Upstream checkout differs from experiments/legalbenchrag-source.json')
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Upstream checkout has local changes; use the clean pinned source.')
    sys.path.insert(0, str(path))
    from legalbenchrag.benchmark_types import QAGroundTruth, RetrievedSnippet, sort_and_merge_spans
    from legalbenchrag.run_benchmark import QAResult
    return lock, QAGroundTruth, RetrievedSnippet, sort_and_merge_spans, QAResult


def evaluate_question(conn, model, question, source_texts, ingestion, top_k, types, diagnose=False):
    _, GroundTruth, Retrieved, merge, QAResult = types
    started = time.perf_counter()
    query = QUERY_PREFIX + question['query']
    if len(model.tokenizer.encode(query)) > model.max_seq_length:
        raise ValueError('Question exceeds model token limit')
    vector = model.encode(query, normalize_embeddings=True)
    embedded_at = time.perf_counter()
    rows = conn.execute('''SELECT file_path,start_char,end_char,content,
        embedding <=> %s AS distance FROM rag_lab.chunks
        WHERE ingestion_id=%s ORDER BY distance,id LIMIT %s''',
        (vector, ingestion, top_k)).fetchall()
    searched_at = time.perf_counter()
    raw = []
    grouped = defaultdict(list)
    for file_path, start, end, text, distance in rows:
        if not 0 <= start < end <= len(source_texts[file_path]) or source_texts[file_path][start:end] != text:
            raise ValueError('Retrieved passage does not match original source')
        raw.append(dict(file_path=file_path, span=[start,end], text=text, distance=distance))
        grouped[file_path].append((start,end))
    # Merge only touching/overlapping ranges within the same document.
    # Otherwise the upstream recall calculation can count overlap twice.
    spans = [Retrieved(file_path=path, span=span, score=0.0)
             for path, ranges in sorted(grouped.items()) for span in merge(ranges)]
    expected = []
    for snippet in question['snippets']:
        start, end = snippet['span']
        source = source_texts[snippet['file_path']]
        if not 0 <= start < end <= len(source) or source[start:end] != snippet['answer']:
            raise ValueError('Expected passage does not match original source')
        expected.append({'file_path': snippet['file_path'], 'span': [start,end], 'text': source[start:end]})
    ground_truth = GroundTruth(query=question['query'], snippets=question['snippets'])
    scored = QAResult(qa_gt=ground_truth, retrieved_snippets=spans)
    # Do not model_dump upstream Snippet: its computed answer property
    # reopens paths using the process cwd and platform-default encoding.
    result = dict(source_index=question['source_index'], question=question['query'],
                  precision=scored.precision, recall=scored.recall,
                  embedding_seconds=embedded_at-started, search_seconds=searched_at-embedded_at,
                  retrieval_seconds=searched_at-started,
                  expected=expected, retrieved=raw,
                  scored_spans=[{'file_path': s.file_path, 'span': list(s.span)} for s in spans])
    result["embedding_input"] = query
    if diagnose:
        diagnostic_started = time.perf_counter()
        # Rank every chunk before looking at gold evidence. Same vector, cosine
        # distance and ID tie-break as the top-k query; no gold-based filtering.
        ranked = conn.execute('''SELECT file_path,start_char,end_char,
            embedding <=> %s AS distance FROM rag_lab.chunks
            WHERE ingestion_id=%s ORDER BY distance,id''', (vector, ingestion)).fetchall()
        diagnostics = []
        for item in expected:
            matches = []
            a, b = item['span']
            for rank, (path, start, end, distance) in enumerate(ranked, 1):
                overlap = max(0, min(b, end) - max(a, start)) if path == item['file_path'] else 0
                if overlap:
                    matches.append(dict(rank=rank, distance=distance, cosine_similarity=1-distance,
                                        span=[start, end], overlap_characters=overlap,
                                        evidence_coverage=overlap/(b-a), returned=rank <= top_k,
                                        text=source_texts[path][start:end]))
            diagnostics.append(dict(file_path=item['file_path'], span=item['span'], chunks=matches))
        first_rank = min((c['rank'] for e in diagnostics for c in e['chunks']), default=None)
        result['ranking_diagnostic'] = dict(total_chunks=len(ranked), first_relevant_rank=first_rank,
                                            evidence=diagnostics,
                                            seconds=time.perf_counter()-diagnostic_started)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingestion', required=True)
    parser.add_argument('--limit', type=int, default=1, help='Number of questions; 0 explicitly runs all')
    parser.add_argument('--offset', type=int, default=0, help='Zero-based position in selected questions')
    parser.add_argument('--top-k', type=int, default=5)
    args = parser.parse_args()
    if args.limit < 0 or args.offset < 0 or args.top_k < 1:
        parser.error('limit/offset must be nonnegative and top-k must be positive')
    lock, GroundTruth, Retrieved, merge, QAResult = upstream()
    manifest_bytes = (ROOT / 'experiments/cuad-100/selection.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    question_bytes = (ROOT / 'experiments/cuad-100/questions.json').read_bytes()
    questions = json.loads(question_bytes)['tests']
    chosen = questions[args.offset:args.offset + args.limit] if args.limit else questions[args.offset:]
    if not chosen:
        parser.error('No questions selected')
    source_texts = {}
    for doc in manifest['documents']:
        path = ROOT / 'data/corpus' / doc['local_file_path']
        if digest(path.read_bytes()) != doc['sha256']:
            raise RuntimeError('Source file changed: ' + doc['file_path'])
        source_texts[doc['file_path']] = path.read_text(encoding='utf-8')

    with connect() as conn:
        register_vector(conn)
        row = conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s', (args.ingestion,)).fetchone()
        if not row:
            parser.error('Unknown ingestion ID')
        config = row[0]
        if config['model'] != MODEL or config['selection_sha256'] != digest(manifest_bytes):
            raise RuntimeError('Ingestion model/selection does not match this experiment')
        paths = {r[0] for r in conn.execute('SELECT DISTINCT file_path FROM rag_lab.chunks WHERE ingestion_id=%s',
                                          (args.ingestion,)).fetchall()}
        if paths != set(source_texts):
            raise RuntimeError('Ingestion must contain all and only the selected 100 documents')
        model_started = time.perf_counter()
        model, revision = load_model(config['revision'])
        load_seconds = time.perf_counter() - model_started
        results = []
        for question in chosen:
            result = evaluate_question(conn, model, question, source_texts, args.ingestion, args.top_k,
                                       (lock, GroundTruth, Retrieved, merge, QAResult))
            results.append(result)
            print(f"Question {question['source_index']}: precision={result['precision']:.4f}, recall={result['recall']:.4f}", flush=True)

    report = dict(ingestion_id=args.ingestion, upstream=lock, top_k=args.top_k,
                  questions_run=len(results), question_file_sha256=digest(question_bytes),
                  model_revision=revision, model_load_seconds=load_seconds,
                  scoring='Upstream QAResult on merged retrieved spans; character overlap',
                  avg_precision=sum(r['precision'] for r in results)/len(results),
                  avg_recall=sum(r['recall'] for r in results)/len(results),
                  results=results)
    directory = ROOT / 'artifacts' / args.ingestion / 'evaluations' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    (directory / 'results.json').write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
    fields = ['source_index','precision','recall','embedding_seconds','search_seconds','retrieval_seconds']
    with (directory / 'results.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f"Saved {len(results)} question result(s) to {directory}")


if __name__ == '__main__':
    main()
