"""Build -> seal -> evaluate the source-only 20-contract experiment.

The build path does not read the question bank. Evaluation requires intact seals.
"""
import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from rdflib import Graph, Literal, Namespace, RDF, RDFS, XSD, OWL

from pipeline import ROOT, connect, load_model, QUERY_PREFIX
from build_sample_ontology import O, LINKS
from holdout20_records import curate

FOLDER = ROOT / 'ontology/experiments/holdout20-v1'
E = Namespace('https://cimulink.local/ontology/holdout20-v1/')
CODE = ['scripts/holdout20.py', 'scripts/holdout20_records.py',
        'scripts/compare_retrieval.py', 'scripts/evaluate.py', 'scripts/pipeline.py',
        'scripts/build_sample_ontology.py', 'requirements.txt']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(name):
    return json.loads((FOLDER / name).read_text(encoding='utf-8'))


def save(name, value):
    (FOLDER / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def frozen_protocol():
    lock = read('protocol-lock.json')
    for name in ['protocol', 'schema']:
        path = FOLDER / ('protocol.md' if name == 'protocol' else 'schema.ttl')
        if sha(path) != lock[name + '_sha256']:
            raise ValueError('Frozen protocol/schema changed')
    return lock


def documents():
    result = {}
    for d in read('selection.json')['documents']:
        path = ROOT / 'data/corpus' / d['local_file_path']
        if sha(path) != d['sha256']:
            raise ValueError('Selected source changed: ' + d['id'])
        result[d['id']] = (d, path.read_text(encoding='utf-8'))
    return result


def locate(text, start, end):
    occurrence = None
    if isinstance(start, tuple):
        start, occurrence = start
    def pattern(marker):
        return r'\s+'.join(re.escape(p) for p in marker.split())
    starts = list(re.finditer(pattern(start), text))
    if occurrence is not None:
        starts = starts[occurrence:occurrence+1]
    if len(starts) != 1:
        raise ValueError(f'Expected unique start marker {start!r}; found {len(starts)}')
    a = starts[0].start()
    following = re.search(pattern(end), text[starts[0].end():])
    if not following:
        raise ValueError(f'End marker not found: {end!r}')
    b = starts[0].end() + following.start()
    while b > a and text[b-1].isspace():
        b -= 1
    return a, b


def build():
    frozen_protocol()
    if (FOLDER / 'graph-lock.json').exists():
        raise ValueError('Graph already sealed; do not overwrite evaluated extraction')
    started = time.perf_counter()
    docs = documents()
    records = {id: dict(id=id, file_path=d['file_path'], source_sha256=d['sha256'], rules=[])
               for id, (d, _) in docs.items()}

    def add(id, start, end, kind, label, condition=None, fields=None, refs=()):
        _, text = docs[id]
        a, b = locate(text, start, end)
        record = dict(id=f'{id}R{len(records[id]["rules"])+1:02d}', kind=kind, label=label,
                      span=[a,b], exact_text=text[a:b], condition=condition,
                      fields=fields or {}, references=[])
        for relationship, name, markers in refs:
            ref = dict(relationship=relationship, label=name, span=None)
            if markers:
                ref['span'] = list(locate(text, *markers))
            record['references'].append(ref)
        records[id]['rules'].append(record)

    curate(add)
    g = Graph().parse(FOLDER / 'schema.ttl')
    g.bind('ct', O); g.bind('ex', E); g.bind('xsd', XSD)

    def literal(n, field, value, datatype=None):
        g.add((n, O[field], Literal(value, datatype=datatype)))

    def passage(name, document, span):
        d, text = docs[document]
        n = E[name]
        g.add((n,RDF.type,O.SourcePassage))
        for field,val in [('source_path',d['file_path']),('source_sha256',d['sha256']),
                          ('start_char',span[0]),('end_char',span[1]),('exact_text',text[span[0]:span[1]])]:
            literal(n,field,val)
        return n

    for id, document in records.items():
        agreement = E[id]
        g.add((agreement,RDF.type,O.Agreement))
        g.add((agreement,RDFS.label,Literal(docs[id][0]['file_path'].removeprefix('cuad/'))))
        literal(agreement,'coverage','PARTIAL_SOURCE_ONLY_TERM_RENEWAL_TERMINATION; NOT_INDEPENDENTLY_REVIEWED')
        base = next((r for r in document['rules'] if r['kind']=='INITIAL_TERM'),document['rules'][0])
        for r in document['rules']:
            n = E[r['id']]
            g.add((agreement,O.has_rule,n)); g.add((n,RDF.type,O.Rule))
            g.add((n,RDFS.label,Literal(r['label'])))
            literal(n,'kind',r['kind']); literal(n,'description',r['exact_text'])
            evidence = passage(r['id']+'P',id,r['span'])
            g.add((n,O.supported_by,evidence))
            if r != base:
                g.add((n,O.qualifies,E[base['id']]))
            for field,val in r['fields'].items():
                datatype = XSD.duration if field in ['duration','termination_notice'] else XSD.date if field=='stated_end_date' else None
                literal(n,field,val,datatype)
            if r['condition']:
                c = E[r['id']+'C']
                g.add((n,O.subject_to,c)); g.add((c,RDF.type,O.Condition))
                g.add((c,RDFS.label,Literal(r['condition'])))
                literal(c,'description',r['condition']); g.add((c,O.supported_by,evidence))
            for i,ref in enumerate(r['references']):
                target = E[r['id']+f'F{i}']
                g.add((n,O[ref['relationship']],target));g.add((target,RDF.type,O.Reference))
                g.add((target,RDFS.label,Literal(ref['label'])))
                literal(target,'resolution_status','PASSAGE_LINKED' if ref['span'] else 'UNRESOLVED')
                if ref['span']:
                    g.add((target,O.resolved_to,passage(r['id']+f'FP{i}',id,ref['span'])))
    save('records.json',list(records.values()))
    g.serialize(destination=FOLDER/'graph.ttl',format='turtle')
    save('build-report.json',dict(built_at=now(),materialization_seconds=time.perf_counter()-started,
                                 documents=len(docs),rules=sum(len(d['rules']) for d in records.values()),
                                 source_characters=sum(len(t) for _,t in docs.values()),
                                 extraction='Manual coding-assistant source-only curation aided by document-wide topic scans; no independent legal review.',
                                 effort='Protocol-to-seal elapsed wall time includes coding and validation, not measured human extraction labor.'))
    validate_graph()


def validate_graph():
    frozen_protocol();docs=documents()
    g=Graph().parse(FOLDER/'graph.ttl')
    schema=Graph().parse(FOLDER/'schema.ttl')
    allowed={s for s in schema.subjects(RDF.type,OWL.ObjectProperty)} | {s for s in schema.subjects(RDF.type,OWL.DatatypeProperty)}
    allowed_classes=set(schema.subjects(RDF.type,OWL.Class))
    instance_types={s:t for s,t in g.subject_objects(RDF.type) if str(s).startswith(str(E))}
    assert set(instance_types.values())<=allowed_classes
    for s,p,o in g:
        if str(s).startswith(str(E)):
            assert p in allowed|{RDF.type,RDFS.label},p
    assert set(g.subjects(RDF.type,O.Agreement))=={E[id] for id in docs}
    texts={d['file_path']:text for d,text in docs.values()}
    hashes={d['file_path']:d['sha256'] for d,_ in docs.values()}
    for p in g.subjects(RDF.type,O.SourcePassage):
        path=str(g.value(p,O.source_path));a=int(g.value(p,O.start_char));b=int(g.value(p,O.end_char))
        assert 0<=a<b<=len(texts[path])
        assert str(g.value(p,O.exact_text))==texts[path][a:b]
        assert str(g.value(p,O.source_sha256))==hashes[path]
    for n in g.subjects(RDF.type,O.Rule):
        assert len(list(g.subjects(O.has_rule,n)))==1
        assert list(g.objects(n,O.supported_by))
        assert len(list(g.objects(n,O.kind)))==1
    for rel,(domain,target) in LINKS.items():
        for a,b in g.subject_objects(O[rel]):
            assert (b,RDF.type,O[target]) in g
            if domain:assert (a,RDF.type,O[domain]) in g
    for a,b in g.subject_objects(O.qualifies):
        assert set(g.subjects(O.has_rule,a))==set(g.subjects(O.has_rule,b))
    for n in g.subjects(O.duration_status,Literal('REDACTED')):
        assert not list(g.objects(n,O.duration))
    print(f'Validated {len(g)} triples, {len(docs)} agreements, {len(list(g.subjects(RDF.type,O.Rule)))} rules.',flush=True)
    return g


def seal():
    validate_graph()
    if (FOLDER/'graph-lock.json').exists():raise ValueError('Already sealed')
    files=[str((FOLDER/name).relative_to(ROOT)).replace('\\','/') for name in
           ['protocol.md','protocol-lock.json','schema.ttl','selection.json','records.json','graph.ttl','build-report.json','source-only-audit.json']]+CODE
    save('graph-lock.json',dict(sealed_at=now(),files={p:sha(ROOT/p) for p in files},
                                benchmark_unlocked=False))
    print('Graph sealed. Benchmark questions may now be unlocked.',flush=True)


def verify_seal():
    lock=read('graph-lock.json')
    for path,expected in lock['files'].items():
        if sha(ROOT/path)!=expected:raise ValueError('Sealed input changed: '+path)
    return lock


def graph_retrieve(g, id, texts):
    started=time.perf_counter();rules=list(g.objects(E[id],O.has_rule))
    def order(rule):
        starts=[int(g.value(p,O.start_char)) for p in g.objects(rule,O.supported_by)]
        return (0 if str(g.value(rule,O.kind))=='INITIAL_TERM' else 1,min(starts),str(rule))
    evidence=[]
    for rule in sorted(rules,key=order):
        evidence.extend(g.objects(rule,O.supported_by))
        for c in g.objects(rule,O.subject_to):evidence.extend(g.objects(c,O.supported_by))
        for p,target in g.predicate_objects(rule):
            if (target,RDF.type,O.Reference) in g:evidence.extend(g.objects(target,O.resolved_to))
    candidates=[]
    for p in dict.fromkeys(evidence):
        path=str(g.value(p,O.source_path));a=int(g.value(p,O.start_char));b=int(g.value(p,O.end_char))
        candidates.append(dict(file_path=path,span=[a,b],text=texts[path][a:b],evidence_id=str(p)))
    return candidates,time.perf_counter()-started


def evaluate():
    lock=verify_seal()
    if (FOLDER/'evaluation-unlock.json').exists():raise ValueError('Already evaluated; preserve the first run')
    save('evaluation-unlock.json',dict(unlocked_at=now(),graph_lock_sha256=sha(FOLDER/'graph-lock.json'),
                                      statement='First benchmark access by this experiment after graph sealing.'))
    # This is the only place the experiment opens benchmark questions/answers.
    from evaluate import upstream
    from compare_retrieval import apply_budget, score
    from pgvector.psycopg import register_vector
    protocol=frozen_protocol();types=upstream();docs=documents()
    texts={d['file_path']:text for d,text in docs.values()};id_by_path={d['file_path']:id for id,(d,_) in docs.items()}
    questions=json.loads((ROOT/'experiments/cuad-100/questions.json').read_text(encoding='utf-8'))['tests']
    selected=[];unmatched=[]
    for q in questions:
        paths={s['file_path'] for s in q['snippets']}
        if not paths & set(texts):continue
        topic=('expiry' if re.search(r'expiration date',q['query'],re.I) else
               'renewal' if re.search(r'renewal term',q['query'],re.I) else
               'renewal_notice' if re.search(r'notice period.*terminate.*renewal',q['query'],re.I) else None)
        if topic and len(paths)==1 and paths<=set(texts):selected.append((q,topic,id_by_path[next(iter(paths))]))
        else:unmatched.append(q['source_index'])
    g=Graph().parse(FOLDER/'graph.ttl');results=[]
    with connect() as conn:
        register_vector(conn)
        config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',('d891bfe3634a5bf21d97',)).fetchone()[0]
        model_start=time.perf_counter();model,_=load_model(config['revision'],local_files_only=True);model_load=time.perf_counter()-model_start
        for q,topic,id in selected:
            path=docs[id][0]['file_path'];started=time.perf_counter();query=QUERY_PREFIX+q['query']
            if len(model.tokenizer.encode(query))>model.max_seq_length:raise ValueError('Query too long')
            vector=model.encode(query,normalize_embeddings=True);embedded=time.perf_counter()
            rows=conn.execute('''SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance
                FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY distance,id LIMIT %s''',
                (vector,'d891bfe3634a5bf21d97',path,protocol['top_k'])).fetchall()
            vector_seconds=time.perf_counter()-started
            raw=[dict(file_path=p,span=[a,b],text=t,distance=d) for p,a,b,t,d in rows]
            graph_raw,graph_seconds=graph_retrieve(g,id,texts)
            record=dict(source_index=q['source_index'],document_id=id,topic=topic,question=q['query'])
            for method,candidates,seconds in [('vector',raw,vector_seconds),('ontology',graph_raw,graph_seconds)]:
                passages=apply_budget(candidates,texts,protocol['character_budget'])
                record[method]=score(passages,q,texts,types)
                full=sum(len(p['text']) for p in apply_budget(candidates,texts,sum(len(p['text']) for p in candidates)))
                record[method].update(retrieval_seconds=seconds,candidate_unique_characters=full,
                                      budget_truncated=full>protocol['character_budget'])
            results.append(record)
            print(f'{id} {topic} {q["source_index"]}: recall vector={record["vector"]["recall"]:.3f}, ontology={record["ontology"]["recall"]:.3f}',flush=True)
    def summarize(rows):
        return {method:{'precision':mean(r[method]['precision'] for r in rows),
                        'recall':mean(r[method]['recall'] for r in rows),
                        'mean_retrieval_ms':mean(r[method]['retrieval_seconds']*1000 for r in rows),
                        'mean_returned_characters':mean(r[method]['returned_characters'] for r in rows),
                        'full_recall_questions':sum(r[method]['recall']>=0.999999 for r in rows)}
                for method in ['vector','ontology']} if rows else None
    per_doc={id:dict(questions=sum(r['document_id']==id for r in results),
                     metrics=summarize([r for r in results if r['document_id']==id])) for id in docs}
    primary=[r for r in results if r['topic']=='expiry']
    report=dict(completed_at=now(),graph_lock_sha256=sha(FOLDER/'graph-lock.json'),
                benchmark_file_sha256=sha(ROOT/'experiments/cuad-100/questions.json'),
                ingestion_id='d891bfe3634a5bf21d97',upstream_commit=types[0]['commit'],model=config,
                model_load_seconds=model_load,primary_expiry=dict(questions=len(primary),metrics=summarize(primary)),
                all_in_scope=dict(questions=len(results),metrics=summarize(results)),per_document=per_doc,
                document_macro={m:{metric:mean(d['metrics'][m][metric] for d in per_doc.values() if d['metrics'])
                                   for metric in ['precision','recall']} for m in ['vector','ontology']},
                excluded_out_of_scope_question_ids=unmatched,results=results,
                limitations=['Manual source-only extraction, not independent legal review.',
                             'Available exposure logs do not prove complete historical blinding.',
                             'Programmatic source preparation had previously validated benchmark spans.',
                             'Same-agreement, fixed-topic retrieval; no automatic entity/topic routing.',
                             'Partial contract coverage and benchmark gold may omit qualifications.',
                             'No changes to sealed extraction or retrieval after unlocking.'])
    save('results.json',report)
    with (FOLDER/'results.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=['document_id','source_index','topic','method','precision','recall','retrieval_ms','returned_characters'])
        writer.writeheader()
        for r in results:
            for m in ['vector','ontology']:
                writer.writerow(dict(document_id=r['document_id'],source_index=r['source_index'],topic=r['topic'],method=m,
                                     precision=r[m]['precision'],recall=r[m]['recall'],retrieval_ms=r[m]['retrieval_seconds']*1000,
                                     returned_characters=r[m]['returned_characters']))
    lines=['# Twenty-contract retrieval results','',f'Questions: {len(results)} in scope; {len(primary)} expiry questions (primary).','',
           'Same selected agreement, top-5 vector candidates, maximum 6,000 unique source characters per method. Graph sealed before benchmark unlock.','',
           '| Set | Method | Precision | Recall | Mean retrieval | Mean characters | Full recall |','| --- | --- | --- | --- | --- | --- | --- |']
    for label,rows in [('Expiry (primary)',primary),('All in scope',results)]:
        stats=summarize(rows)
        if stats:
            for m,v in stats.items():lines.append(f'| {label} | {m} | {v["precision"]:.1%} | {v["recall"]:.1%} | {v["mean_retrieval_ms"]:.2f} ms | {v["mean_returned_characters"]:.0f} | {v["full_recall_questions"]}/{len(rows)} |')
    lines+=['','## Per-document results','', '| Document | Questions | Vector recall | Ontology recall |','| --- | --- | --- | --- |']
    for id,d in per_doc.items():
        v=d['metrics'];lines.append(f'| {id} | {d["questions"]} | {v["vector"]["recall"]:.1%} | {v["ontology"]["recall"]:.1%} |' if v else f'| {id} | 0 | N/A | N/A |')
    start=datetime.fromisoformat(read('protocol-lock.json')['frozen_at']);end=datetime.fromisoformat(lock['sealed_at'])
    lines+=['','## Effort and limitations','',f'Protocol-to-graph-seal elapsed time: {(end-start).total_seconds()/60:.1f} minutes, including coding, extraction and validation. This is not measured human extraction labor. Model loading ({model_load:.2f} s) is excluded from query timings. Ontology query timing excludes graph parsing and validation; vector timing includes query embedding and SQL search. Source reading, materialization, review and storage costs are not priced. No paid embedding/extraction API used.','']
    lines+=['- '+s for s in report['limitations']]
    lines+=['','The graph is unchanged after viewing scores. This batch is now evaluated development material. A new batch is required to evaluate any changes made in response to these results.','',
            'Files: [protocol](protocol.md), [selection](selection.json), [Turtle graph](graph.ttl), [source-only records](records.json), [graph seal](graph-lock.json), [unlock record](evaluation-unlock.json), [full results](results.json), [CSV](results.csv).']
    (FOLDER/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    verify_seal()
    print(json.dumps(report['primary_expiry'],indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','validate','seal','evaluate'])
    args=parser.parse_args()
    {'build':build,'validate':validate_graph,'seal':seal,'evaluate':evaluate}[args.command]()
