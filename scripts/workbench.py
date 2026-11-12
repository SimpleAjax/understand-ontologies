"""Local retrieval workbench: python scripts/workbench.py (http://127.0.0.1:8768)."""

import argparse
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from pgvector.psycopg import register_vector
from pipeline import ROOT, MODEL, QUERY_PREFIX, connect, digest, load_model
from evaluate import upstream, evaluate_question
from compare_retrieval import OntologySearch, SAMPLE_IDS, compare
from holdout_workbench import HoldoutWorkbench


class Workbench:
    def __init__(self, ingestion):
        self.ingestion = ingestion
        self.types = upstream()
        manifest_bytes = (ROOT / 'experiments/cuad-100/selection.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.questions = json.loads((ROOT / 'experiments/cuad-100/questions.json').read_bytes())['tests']
        self.texts = {}
        for doc in manifest['documents']:
            path = ROOT / 'data/corpus' / doc['local_file_path']
            if digest(path.read_bytes()) != doc['sha256']:
                raise RuntimeError('Source file changed: ' + doc['file_path'])
            self.texts[doc['file_path']] = path.read_text(encoding='utf-8')
        with connect() as conn:
            row = conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s', (ingestion,)).fetchone()
            if not row:
                raise RuntimeError('Unknown ingestion ID')
            self.config = row[0]
            paths = {r[0] for r in conn.execute('SELECT DISTINCT file_path FROM rag_lab.chunks WHERE ingestion_id=%s', (ingestion,)).fetchall()}
            self.chunk_count = conn.execute('SELECT count(*) FROM rag_lab.chunks WHERE ingestion_id=%s', (ingestion,)).fetchone()[0]
        if paths != set(self.texts) or self.config['selection_sha256'] != digest(manifest_bytes) or self.config['model'] != MODEL:
            raise RuntimeError('Ingestion does not match the selected 100 documents and model')
        self.model = None
        self.lock = threading.Lock()
        self.ontology = OntologySearch()
        self.holdout = HoldoutWorkbench()
        self.model_state = 'loading'
        self.model_started = time.perf_counter()
        self.model_load_seconds = 0
        self.model_error = None

    def prepare_model(self):
        # Keep the HTTP server responsive while cold Python/model startup runs.
        with self.lock:
            self.model_started = time.perf_counter()
            try:
                self.model, _ = load_model(self.config['revision'], local_files_only=True)
                self.model_load_seconds = time.perf_counter() - self.model_started
                self.model_state = 'ready'
                print(f'Local BGE ready in {self.model_load_seconds:.2f} seconds.', flush=True)
            except Exception:
                import traceback
                traceback.print_exc()
                self.model_error = 'Local model could not load. Check the server log and downloaded model cache.'
                self.model_state = 'failed'

    def status(self):
        return dict(model_state=self.model_state, model_error=self.model_error,
                    model_load_seconds=self.model_load_seconds,
                    loading_elapsed_seconds=time.perf_counter()-self.model_started if self.model_state == 'loading' else 0,
                    search_running=self.model_state == 'ready' and self.lock.locked())

    def run(self, index, top_k, comparison=False, character_budget=6000, comparison_batch='sample5'):
        if self.model_state != 'ready':
            raise BlockingIOError(self.model_error or 'Local BGE is still loading. Wait for Ready before searching.')
        if not self.lock.acquire(blocking=False):
            raise BlockingIOError('A search is already running. Wait for it to finish.')
        try:
            eligible = self.holdout.questions if comparison_batch == 'holdout20' else SAMPLE_IDS
            if comparison and self.questions[index]['source_index'] not in eligible:
                raise ValueError('Choose a supported question for the selected comparison batch')
            load_seconds = 0  # Model was loaded before this request, reported separately.
            if comparison:
                with connect() as conn:
                    register_vector(conn)
                    if comparison_batch == 'holdout20':
                        result = self.holdout.run(conn,self.model,self.questions[index],self.texts,
                                                  self.ingestion,top_k,character_budget,self.types)
                    else:
                        result = compare(conn, self.model, self.questions[index], self.texts,
                                         self.ingestion, top_k, character_budget, self.types, self.ontology)
                result.update(ingestion_id=self.ingestion, question_index=index,
                              model_load_seconds=load_seconds, model=self.config,
                              startup_model_load_seconds=self.model_load_seconds,
                              upstream_commit=self.types[0]['commit'])
                folder = ROOT / 'artifacts' / self.ingestion / ('holdout20-live' if comparison_batch == 'holdout20' else 'comparisons')
                folder.mkdir(parents=True, exist_ok=True)
                name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
                result['saved_result'] = str((folder / name).relative_to(ROOT))
                (folder / name).write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
                return result
            with connect() as conn:
                register_vector(conn)
                result = evaluate_question(conn, self.model, self.questions[index], self.texts,
                                           self.ingestion, top_k, self.types, diagnose=True)
            # Source offsets are Python character offsets; create highlight slices
            # here rather than applying them to JavaScript's UTF-16 string offsets.
            for passage in result['retrieved']:
                start, end = passage['span']
                intervals = []
                for expected in result['expected']:
                    if expected['file_path'] == passage['file_path']:
                        a, b = max(start, expected['span'][0]), min(end, expected['span'][1])
                        if a < b:
                            intervals.append((a, b))
                intervals = self.types[3](intervals)
                segments, pos = [], start
                source = self.texts[passage['file_path']]
                for a, b in intervals:
                    segments.extend([{'text': source[pos:a], 'relevant': False},
                                     {'text': source[a:b], 'relevant': True}])
                    pos = b
                segments.append({'text': source[pos:end], 'relevant': False})
                passage['segments'] = segments
                passage['relevant_characters'] = sum(b-a for a,b in intervals)
            result.update(ingestion_id=self.ingestion, question_index=index, top_k=top_k,
                          model_load_seconds=load_seconds, model=self.config,
                          startup_model_load_seconds=self.model_load_seconds,
                          scoring='LegalBench-RAG character overlap; overlapping retrieved spans merged',
                          upstream_commit=self.types[0]['commit'])
            folder = ROOT / 'artifacts' / self.ingestion / 'workbench'
            folder.mkdir(parents=True, exist_ok=True)
            name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
            result['saved_result'] = str((folder / name).relative_to(ROOT))
            (folder / name).write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding='utf-8')
            return result
        finally:
            self.lock.release()


def handler(lab, port):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, data, content_type='application/json; charset=utf-8'):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=True).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # A refresh can close a completed request; do not send a second response.
                pass

        def do_GET(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                return self.send(403, {'error': 'Use the local workbench address.'})
            path = urlparse(self.path).path
            if path == '/':
                return self.send(200, (ROOT / 'ui/index.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/status':
                return self.send(200, lab.status())
            if path == '/api/questions':
                return self.send(200, {'questions': lab.questions, 'documents': len(lab.texts),
                                      'chunks': lab.chunk_count, 'config': lab.config,
                                      'ingestion_id': lab.ingestion, 'query_prefix': QUERY_PREFIX,
                                      'comparison_source_ids': SAMPLE_IDS,
                                      'ontology_sha256': lab.ontology.graph_hash,
                                      'holdout20_source_ids': sorted(lab.holdout.questions),
                                      'holdout20_graph_sha256': lab.holdout.graph_hash,
                                      'holdout20_summary': lab.holdout.report['all_in_scope'],
                                      'holdout20_documents': len(lab.holdout.documents)})
            self.send(404, {'error': 'Not found'})

        def do_POST(self):
            if self.headers.get('Host') not in {f'127.0.0.1:{port}', f'localhost:{port}'}:
                return self.send(403, {'error': 'Use the local workbench address.'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}:
                return self.send(403, {'error': 'Use the local workbench page.'})
            if self.path not in {'/api/run', '/api/compare'}:
                return self.send(404, {'error': 'Not found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                index, top_k = data['question_index'], data.get('top_k', 5)
                if type(index) is not int or not 0 <= index < len(lab.questions):
                    raise ValueError('Select a question from the bank')
                if type(top_k) is not int or not 1 <= top_k <= 20:
                    raise ValueError('Choose between 1 and 20 passages')
                budget = data.get('character_budget', 6000)
                if type(budget) is not int or not 500 <= budget <= 20000:
                    raise ValueError('Choose a character budget between 500 and 20000')
                batch = data.get('comparison_batch', 'sample5')
                if batch not in {'sample5','holdout20'}:
                    raise ValueError('Unknown comparison batch')
                result = lab.run(index, top_k, comparison=self.path == '/api/compare',
                                 character_budget=budget, comparison_batch=batch)
                self.send(200, result)
            except (ValueError, KeyError, json.JSONDecodeError) as error:
                self.send(400, {'error': str(error)})
            except BlockingIOError as error:
                self.send(409, {'error': str(error)})
            except Exception:
                import traceback
                traceback.print_exc()
                self.send(500, {'error': 'Search failed. Check the workbench terminal for details.'})

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingestion', default='d891bfe3634a5bf21d97')
    parser.add_argument('--port', type=int, default=8768)
    args = parser.parse_args()
    lab = Workbench(args.ingestion)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(lab, args.port))
    threading.Thread(target=lab.prepare_model, daemon=True).start()
    print(f'Retrieval workbench: http://127.0.0.1:{args.port}', flush=True)
    print('Loading BGE from local cache in the background. UI shows readiness. Press Ctrl+C to stop.', flush=True)
    server.serve_forever()
