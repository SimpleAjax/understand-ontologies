"""Small, explicit-agreement term-retrieval pilot. Gold is used only by score()."""
import time
from collections import defaultdict

from rdflib import Graph, RDF, RDFS

from build_sample_ontology import O, E, OUTPUT, DOCS, validate
from pipeline import QUERY_PREFIX, digest

SAMPLE_IDS = (10, 30, 129, 268, 373)
ROOT_RULES = {10: 'InitialTerm10', 30: 'InitialTerm30', 129: 'Term129',
              268: 'InitialTerm268', 373: 'Term373'}


def apply_budget(candidates, texts, budget):
    """Keep ranked source ranges, remove overlap, and cap unique Python chars."""
    used, output, remaining = defaultdict(list), [], budget
    for candidate in candidates:
        path = candidate['file_path']
        start, end = candidate['span']
        if texts[path][start:end] != candidate['text']:
            raise ValueError('Candidate text differs from source')
        pieces = [(start, end)]
        for a, b in used[path]:
            pieces = [(x, y) for lo, hi in pieces
                      for x, y in [(lo, min(hi, a)), (max(lo, b), hi)] if x < y]
        for a, b in pieces:
            if not remaining:
                break
            stop = min(b, a + remaining)
            output.append({**candidate, 'span': [a, stop], 'text': texts[path][a:stop]})
            used[path].append((a, stop))
            remaining -= stop-a
    return output


def score(passages, question, texts, types):
    _, GroundTruth, Retrieved, merge, QAResult = types
    grouped = defaultdict(list)
    for p in passages:
        grouped[p['file_path']].append(tuple(p['span']))
    spans = [Retrieved(file_path=path, span=span, score=0.0)
             for path, ranges in sorted(grouped.items()) for span in merge(ranges)]
    expected = []
    for s in question['snippets']:
        a, b = s['span']
        if texts[s['file_path']][a:b] != s['answer']:
            raise ValueError('Expected evidence differs from source')
        expected.append({'file_path': s['file_path'], 'span': [a, b], 'text': s['answer']})
    evaluated = QAResult(qa_gt=GroundTruth(query=question['query'], snippets=question['snippets']),
                         retrieved_snippets=spans)
    for p in passages:
        start, end = p['span']
        overlaps = merge([(max(start, e['span'][0]), min(end, e['span'][1]))
                          for e in expected if e['file_path'] == p['file_path']
                          and max(start, e['span'][0]) < min(end, e['span'][1])])
        segments, pos = [], start
        for a, b in overlaps:
            segments.extend([{'text': texts[p['file_path']][pos:a], 'relevant': False},
                             {'text': texts[p['file_path']][a:b], 'relevant': True}])
            pos = b
        segments.append({'text': texts[p['file_path']][pos:end], 'relevant': False})
        p.update(segments=segments, relevant_characters=sum(b-a for a,b in overlaps))
    return {'precision': evaluated.precision, 'recall': evaluated.recall,
            'retrieved': passages, 'expected': expected,
            'returned_characters': sum(len(p['text']) for p in passages),
            'scored_spans': [{'file_path': s.file_path, 'span': list(s.span)} for s in spans]}


class OntologySearch:
    def __init__(self):
        raw = OUTPUT.read_bytes()
        self.graph_hash = digest(raw)
        self.graph = Graph().parse(data=raw, format='turtle')
        validate(self.graph)

    def retrieve(self, agreement_id):
        started = time.perf_counter()
        g = self.graph
        label = lambda n: str(g.value(n, RDFS.label) or str(n).rsplit('/', 1)[-1])
        short = lambda n: str(n).rsplit('/', 1)[-1]
        agreement = E[f'A{agreement_id}']
        root = E[ROOT_RULES[agreement_id]]
        rules, queue = [root], [root]
        paths = [{'from': label(agreement), 'relationship': 'has_rule', 'to': label(root)}]
        # Follow incoming qualifies links, not all unrelated agreement rules.
        while queue:
            current = queue.pop(0)
            for n in sorted(g.subjects(O.qualifies, current), key=str):
                if (agreement, O.has_rule, n) not in g:
                    continue
                paths.append({'from': label(n), 'relationship': 'qualifies', 'to': label(current)})
                if n not in rules:
                    rules.append(n)
                    queue.append(n)
        evidence, facts, references = [], [], []
        for rule in rules:
            details = {'id': short(rule), 'label': label(rule), 'fields': [], 'conditions': []}
            for pred, target in sorted(g.predicate_objects(rule), key=lambda pair: (str(pair[0]), str(pair[1]))):
                if pred in (RDF.type, RDFS.label):
                    continue
                field = str(pred).split('#')[-1]
                if pred == O.supported_by:
                    evidence.append(target)
                    paths.append({'from': short(rule), 'relationship': field, 'to': short(target)})
                elif pred == O.subject_to:
                    details['conditions'].append(label(target))
                    paths.append({'from': short(rule), 'relationship': field, 'to': label(target)})
                    for passage in g.objects(target, O.supported_by):
                        evidence.append(passage)
                        paths.append({'from': label(target), 'relationship': 'supported_by',
                                      'to': short(passage)})
                elif (target, RDF.type, O.Reference) in g:
                    refs = list(g.objects(target, O.resolved_to))
                    evidence.extend(refs)
                    for passage in refs:
                        paths.append({'from': label(target), 'relationship': 'resolved_to',
                                      'to': short(passage)})
                    references.append({'id': short(target), 'label': label(target),
                                       'status': str(g.value(target, O.resolution_status)),
                                       'evidence_ids': [short(p) for p in refs]})
                    details['fields'].append({'field': field, 'value': label(target)})
                    paths.append({'from': short(rule), 'relationship': field, 'to': label(target)})
                elif pred != O.qualifies:
                    details['fields'].append({'field': field, 'value': str(target)})
            facts.append(details)
        candidates = []
        for p in dict.fromkeys(evidence):
            candidates.append({'evidence_id': short(p), 'file_path': str(g.value(p, O.source_path)),
                               'span': [int(g.value(p, O.start_char)), int(g.value(p, O.end_char))],
                               'text': str(g.value(p, O.exact_text))})
        return candidates, {'graph_sha256': self.graph_hash, 'root_rule': short(root),
                            'rules': facts, 'paths': paths, 'references': references,
                            'coverage': 'Partial, manually curated development graph; other clauses may be missing.',
                            'retrieval_seconds': time.perf_counter()-started}


def compare(conn, model, question, texts, ingestion, top_k, budget, types, ontology):
    sample = question['source_index']
    if sample not in SAMPLE_IDS:
        raise ValueError('Comparison currently supports the five sample expiry questions only')
    # Agreement comes from explicit pilot selection, not expected snippet locations.
    path = DOCS[sample]
    started = time.perf_counter()
    query = QUERY_PREFIX + question['query']
    if len(model.tokenizer.encode(query)) > model.max_seq_length:
        raise ValueError('Question exceeds model token limit')
    vector = model.encode(query, normalize_embeddings=True)
    embedded = time.perf_counter()
    rows = conn.execute('''SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance
        FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s
        ORDER BY distance,id LIMIT %s''', (vector, ingestion, path, top_k)).fetchall()
    searched = time.perf_counter()
    candidates = [{'file_path': p, 'span': [a,b], 'text': t, 'distance': d,
                   'candidate_rank': i} for i,(p,a,b,t,d) in enumerate(rows,1)]
    graph_candidates, graph_details = ontology.retrieve(sample)
    # Neither retrieval path above receives expected evidence. Scoring happens here.
    results = {}
    for name, raw in [('vector', candidates), ('ontology', graph_candidates)]:
        chosen = apply_budget(raw, texts, budget)
        full_chars = sum(len(p['text']) for p in apply_budget(raw, texts, sum(len(p['text']) for p in raw)))
        results[name] = score(chosen, question, texts, types)
        results[name].update(candidate_passages=len(raw), candidate_characters=full_chars,
                             budget_truncated=full_chars > budget)
    results['vector'].update(retrieval_seconds=searched-started,
                             embedding_seconds=embedded-started, search_seconds=searched-embedded)
    results['ontology'].update(graph_details)
    return {'mode': 'comparison', 'source_index': sample, 'question': question['query'],
            'agreement_id': f'A{sample}', 'file_path': path, 'top_k': top_k,
            'character_budget': budget, 'embedding_input': query,
            'topic': 'Term / expiry with linked qualifications',
            'selection': 'Explicit agreement and fixed term topic; no LLM query routing.',
            'scoring': 'LegalBench-RAG character overlap on merged ranges; gold used only after retrieval.',
            'caveat': 'Five hand-curated development examples, not held-out accuracy. Benchmark gold may omit useful qualifications.',
            **results}
