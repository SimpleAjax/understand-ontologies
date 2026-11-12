"""Local contract ingestion. Run --help for commands; credentials come from .env."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', encoding='utf-8-sig')
MODEL = 'BAAI/bge-small-en-v1.5'
QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '


def digest(value):
    return hashlib.sha256(value).hexdigest()


def connect(database=None, **kwargs):
    return psycopg.connect(
        host=os.getenv('PGHOST', '127.0.0.1'),
        port=os.getenv('PGPORT', '5432'),
        user=os.getenv('PGUSER', 'postgres'),
        password=os.getenv('PGPASSWORD'),
        dbname=database or os.getenv('PGDATABASE', 'understand_ontologies'),
        connect_timeout=5, **kwargs,
    )


def init_db():
    name = os.getenv('PGDATABASE', 'understand_ontologies')
    with connect('postgres', autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_available_extensions WHERE name='vector'").fetchone():
            raise RuntimeError('PostgreSQL is reachable, but its pgvector extension is not installed. Install pgvector for this PostgreSQL server, then rerun init-db.')
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
            conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    with connect() as conn:
        conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        conn.execute('CREATE SCHEMA IF NOT EXISTS rag_lab')
        conn.execute('''CREATE TABLE IF NOT EXISTS rag_lab.ingestions (
            id text PRIMARY KEY, config jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now())''')
        conn.execute('''CREATE TABLE IF NOT EXISTS rag_lab.chunks (
            ingestion_id text NOT NULL REFERENCES rag_lab.ingestions(id),
            id text NOT NULL, file_path text NOT NULL, start_char integer NOT NULL,
            end_char integer NOT NULL, content text NOT NULL,
            token_count integer NOT NULL, embedding vector(384) NOT NULL,
            PRIMARY KEY (ingestion_id,id), CHECK(end_char>start_char))''')
    print('Database and rag_lab tables ready.', flush=True)


def chunks(text, tokenizer, size, overlap):
    """Contiguous source slices, preferring paragraph then sentence boundaries.

    Count with the model tokenizer and retain whitespace for exact provenance.
    Overlap is approximate because cuts prefer natural boundaries.
    """
    start = 0
    previous_end = 0
    while start < len(text):
        # Tokenize a bounded character window. Token count cannot exceed character
        # count for this WordPiece tokenizer, so size*30 safely covers typical text.
        window_end = min(len(text), start + size * 30)
        offsets = tokenizer(text[start:window_end], add_special_tokens=False,
                            return_offsets_mapping=True, truncation=False, verbose=False)['offset_mapping']
        if not offsets:
            if previous_end < len(text):
                yield start, len(text), 0
            break
        end = window_end if len(offsets) <= size else start + offsets[size - 1][1]
        if end < len(text):
            # Avoid tiny chunks: consider boundaries in the latter half only.
            minimum = max(previous_end + 1, start + (end - start) // 2)
            for pattern in (r'\n\s*\n', r'(?<=[.!?])\s+'):
                candidates = [start + m.end() for m in re.finditer(pattern, text[start:end])
                              if start + m.end() >= minimum]
                if candidates:
                    end = candidates[-1]
                    break
        count = len(tokenizer.encode(text[start:end], add_special_tokens=False))
        while count > size:
            end -= 1
            count = len(tokenizer.encode(text[start:end], add_special_tokens=False))
        if end <= previous_end:
            raise RuntimeError('Chunking did not advance')
        yield start, end, count
        previous_end = end
        if end == len(text):
            break
        local_offsets = tokenizer(text[start:end], add_special_tokens=False,
                                  return_offsets_mapping=True)['offset_mapping']
        next_start = end
        if overlap and len(local_offsets) > overlap:
            next_start = start + local_offsets[-overlap][0]
        if next_start <= start:
            next_start = end
        start = next_start


def load_model(revision, *, local_files_only=False):
    if local_files_only and not revision:
        raise ValueError('Local-only model loading requires a pinned revision')
    from huggingface_hub import HfApi
    from sentence_transformers import SentenceTransformer
    # Resolve main once and record its immutable revision in every run.
    revision = revision or HfApi().model_info(MODEL).sha
    model = SentenceTransformer(MODEL, revision=revision, device='cpu',
                                local_files_only=local_files_only)
    return model, revision


def execute(args):
    if args.command == 'init-db':
        init_db()
        return
    manifest_bytes = (ROOT / 'experiments/cuad-100/selection.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    model, revision = load_model(args.revision)
    if args.command == 'search':
        with connect() as conn:
            register_vector(conn)
            config_row = conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',
                                      (args.ingestion,)).fetchone()
            if not config_row:
                raise ValueError('Unknown ingestion ID')
            config = config_row[0]
            if revision != config['revision']:
                model, revision = load_model(config['revision'])
            query = QUERY_PREFIX + args.question
            if len(model.tokenizer.encode(query)) > model.max_seq_length:
                raise ValueError('Question exceeds model token limit')
            started = time.perf_counter()
            vector = model.encode(query, normalize_embeddings=True)
            rows = conn.execute('''SELECT file_path,start_char,end_char,content,
                embedding <=> %s AS distance FROM rag_lab.chunks
                WHERE ingestion_id=%s ORDER BY distance,id LIMIT %s''',
                (vector, args.ingestion, args.top_k)).fetchall()
        print(json.dumps({'seconds': time.perf_counter()-started,
                          'results': [dict(zip(['file_path','start','end','text','distance'], r))
                                      for r in rows]}, ensure_ascii=True, indent=2))
        return
    config = {'model': MODEL, 'revision': revision, 'size': args.size,
              'overlap': args.overlap, 'splitter': 'source-boundaries-v1',
              'normalized': True, 'selection_sha256': digest(manifest_bytes),
              'versions': {p: importlib.metadata.version(p) for p in
                           ['sentence-transformers','transformers','tokenizers','torch']}}
    ingestion = digest(json.dumps(config, sort_keys=True).encode())[:20]
    output = ROOT / 'artifacts' / ingestion
    output.mkdir(parents=True, exist_ok=True)
    (output / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    documents = manifest['documents'][:args.limit] if args.limit else manifest['documents']
    conn = connect() if args.command == 'ingest' else None
    started = time.perf_counter()
    total = embedded = 0
    try:
        if conn:
            register_vector(conn)
            conn.execute('INSERT INTO rag_lab.ingestions(id,config) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                         (ingestion, Jsonb(config)))
            conn.commit()
        with (output / 'chunks.jsonl').open('w', encoding='utf-8') as preview:
            for number, doc in enumerate(documents, 1):
                path = ROOT / 'data/corpus' / doc['local_file_path']
                if digest(path.read_bytes()) != doc['sha256']:
                    raise ValueError(f"Source checksum changed: {doc['file_path']}")
                text = path.read_text(encoding='utf-8')
                records = []
                for start, end, count in chunks(text, model.tokenizer, args.size, args.overlap):
                    content = text[start:end]
                    if len(model.tokenizer.encode(content)) > model.max_seq_length:
                        raise ValueError('Chunk exceeds model input limit')
                    cid = digest(f"{doc['file_path']}:{start}:{end}:{doc['sha256']}".encode())
                    record = dict(id=cid, file_path=doc['file_path'], start=start,
                                  end=end, token_count=count, text=content)
                    records.append(record)
                    preview.write(json.dumps(record, ensure_ascii=True)+'\n')
                total += len(records)
                if conn:
                    existing = {r[0] for r in conn.execute(
                        'SELECT id FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s',
                        (ingestion, doc['file_path'])).fetchall()}
                    pending = [r for r in records if r['id'] not in existing]
                    for offset in range(0, len(pending), args.batch_size):
                        batch = pending[offset:offset+args.batch_size]
                        vectors = model.encode([r['text'] for r in batch], batch_size=args.batch_size,
                                               normalize_embeddings=True, show_progress_bar=False)
                        if vectors.shape != (len(batch),384) or not np.isfinite(vectors).all():
                            raise ValueError('Invalid embedding output')
                        with conn.cursor() as cursor:
                            cursor.executemany('''INSERT INTO rag_lab.chunks
                                (ingestion_id,id,file_path,start_char,end_char,content,token_count,embedding)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                                [(ingestion,r['id'],r['file_path'],r['start'],r['end'],r['text'],
                                  r['token_count'],v) for r,v in zip(batch,vectors)])
                        conn.commit()
                        embedded += len(batch)
                print(f'{number}/{len(documents)} documents; {total} chunks; {embedded} newly embedded', flush=True)
        report = {'ingestion_id': ingestion, 'command': args.command, 'documents': len(documents),
                  'chunks': total, 'newly_embedded': embedded,
                  'seconds': time.perf_counter()-started, 'embedding_api_cost': 0,
                  'local_compute_cost': 'unpriced'}
        if conn:
            report['stored_chunks'] = conn.execute('SELECT count(*) FROM rag_lab.chunks WHERE ingestion_id=%s', (ingestion,)).fetchone()[0]
            report['table_bytes_all_runs'] = conn.execute("SELECT pg_total_relation_size('rag_lab.chunks')").fetchone()[0]
        (output / f'{args.command}-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
    except Exception as error:
        # Save a bounded failure record without connection strings or credentials.
        (output / f'{args.command}-failure.json').write_text(json.dumps({
            'ingestion_id': ingestion, 'error_type': type(error).__name__,
            'chunks_prepared': total, 'newly_embedded': embedded,
            'seconds': time.perf_counter() - started,
            'status': 'incomplete; rerun with the same settings to resume',
        }, indent=2), encoding='utf-8')
        raise
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init-db')
    for name in ['preview','ingest','search']:
        p = commands.add_parser(name)
        p.add_argument('--revision', help='Immutable Hugging Face model revision')
        if name == 'search':
            p.add_argument('question')
            p.add_argument('--ingestion', required=True)
            p.add_argument('--top-k', type=int, default=5)
        else:
            p.add_argument('--limit', type=int, default=0, help='0 means all 100 documents')
            p.add_argument('--size', type=int, default=480)
            p.add_argument('--overlap', type=int, default=50)
            p.add_argument('--batch-size', type=int, default=16)
    args = parser.parse_args()
    if args.command in ['preview','ingest'] and not (
        1 <= args.size <= 480 and 0 <= args.overlap < args.size and args.limit >= 0 and args.batch_size > 0
    ):
        parser.error('Require size 1..480, overlap 0..size-1, limit >=0, batch-size >0')
    if args.command == 'search' and args.top_k < 1:
        parser.error('top-k must be positive')
    execute(args)


if __name__ == '__main__':
    main()
