"""Live exploration of the sealed batch; never modifies its first-run artifacts."""
import json
import time

from rdflib import Graph, RDF, RDFS

from pipeline import QUERY_PREFIX, digest
from build_sample_ontology import O
from compare_retrieval import apply_budget, score
from holdout20 import FOLDER, E, graph_retrieve, verify_seal


class HoldoutWorkbench:
    def __init__(self):
        verify_seal()
        self.graph = Graph().parse(FOLDER / 'graph.ttl')
        self.graph_hash = digest((FOLDER / 'graph.ttl').read_bytes())
        self.report = json.loads((FOLDER / 'results.json').read_text(encoding='utf-8'))
        self.selection = json.loads((FOLDER / 'selection.json').read_text(encoding='utf-8'))
        self.questions = {r['source_index']: r for r in self.report['results']}
        self.documents = {d['id']: d for d in self.selection['documents']}

    def details(self, id):
        g = self.graph
        short = lambda n: str(n).rsplit('/', 1)[-1]
        label = lambda n: str(g.value(n, RDFS.label) or short(n))
        facts, paths, references = [], [], []
        for rule in sorted(g.objects(E[id], O.has_rule), key=str):
            paths.append({'from': id, 'relationship': 'has_rule', 'to': short(rule)})
            details = dict(id=short(rule), label=label(rule), fields=[], conditions=[])
            for predicate, target in sorted(g.predicate_objects(rule), key=lambda t:(str(t[0]),str(t[1]))):
                field = str(predicate).split('#')[-1]
                if predicate in (RDF.type, RDFS.label, O.description):
                    continue
                if predicate == O.subject_to:
                    details['conditions'].append(label(target))
                    paths.append({'from': short(rule), 'relationship': field, 'to': label(target)})
                    for p in g.objects(target, O.supported_by):
                        paths.append({'from': label(target), 'relationship': 'supported_by', 'to': short(p)})
                elif (target, RDF.type, O.Reference) in g:
                    details['fields'].append(dict(field=field, value=label(target)))
                    references.append(dict(id=short(target), label=label(target),
                                           status=str(g.value(target, O.resolution_status))))
                    paths.append({'from': short(rule), 'relationship': field, 'to': label(target)})
                    for p in g.objects(target, O.resolved_to):
                        paths.append({'from': label(target), 'relationship': 'resolved_to', 'to': short(p)})
                elif predicate in (O.qualifies, O.supported_by):
                    paths.append({'from': short(rule), 'relationship': field, 'to': short(target)})
                else:
                    details['fields'].append(dict(field=field, value=str(target)))
            facts.append(details)
        return dict(rules=facts, paths=paths, references=references,
                    graph_sha256=self.graph_hash,
                    coverage='Sealed source-only graph. Partial contract coverage, no independent legal review; exploratory runs do not replace the first evaluation.')

    def run(self, conn, model, question, texts, ingestion, top_k, budget, types):
        if question['source_index'] not in self.questions:
            raise ValueError('Choose one of the 31 batch questions')
        if ingestion != self.report['ingestion_id']:
            raise ValueError('The batch requires its original ingestion')
        id = self.questions[question['source_index']]['document_id']
        path = self.documents[id]['file_path']
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
        raw = [dict(file_path=p, span=[a,b], text=t, distance=d, candidate_rank=i)
               for i,(p,a,b,t,d) in enumerate(rows,1)]
        graph_raw, graph_seconds = graph_retrieve(self.graph, id, texts)
        result = dict(mode='comparison', comparison_batch='holdout20', source_index=question['source_index'],
                      question=question['query'], agreement_id=id, file_path=path, top_k=top_k,
                      character_budget=budget, embedding_input=query,
                      topic='Term / expiry with linked qualifications',
                      selection='Explicit agreement and fixed topic. Live exploratory run against sealed graph.',
                      scoring='LegalBench-RAG character overlap; gold used only after retrieval.',
                      caveat='Live exploration of the 20-contract batch; first-run scores and sealed graph remain unchanged.')
        for method, candidates in [('vector',raw),('ontology',graph_raw)]:
            result[method] = score(apply_budget(candidates,texts,budget),question,texts,types)
            full = sum(len(p['text']) for p in apply_budget(candidates,texts,sum(len(p['text']) for p in candidates)))
            result[method].update(candidate_passages=len(candidates),candidate_characters=full,budget_truncated=full>budget)
        result['vector'].update(retrieval_seconds=searched-started,
                                embedding_seconds=embedded-started,search_seconds=searched-embedded)
        result['ontology'].update(self.details(id),retrieval_seconds=graph_seconds)
        for p in result['ontology']['retrieved']:
            p['evidence_id'] = p['evidence_id'].rsplit('/',1)[-1]
        result['first_evaluation'] = {
            method: {field:self.questions[question['source_index']][method][field]
                     for field in ['precision','recall','retrieval_seconds','returned_characters']}
            for method in ['vector','ontology']}
        return result
