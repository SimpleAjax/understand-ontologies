"""Frozen-source, same-contract comparison. No graph/extraction changes allowed."""
import argparse
import csv
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import numpy as np
from rdflib import Graph, Namespace, RDF
from pgvector.psycopg import register_vector

from pipeline import ROOT, MODEL, QUERY_PREFIX, connect, digest, load_model
from compare_retrieval import apply_budget, score
from evaluate import upstream

RUN = ROOT / 'ontology/experiments/llm100-v1'
OUT = RUN / 'comparison-v1'
CT = Namespace('https://cimulink.local/ontology/contract-terms/0.1#')
EX = Namespace('https://cimulink.local/ontology/llm100-v1/')
INGESTION = 'd891bfe3634a5bf21d97'
METHODS = ('vector', 'catalogue', 'ontology')
KINDS = {
    'expiry': ['INITIAL_TERM', 'CONDITIONAL_REFERENCED_TERM', 'POST_EXPIRY_CONTINUATION'],
    'renewal': ['OPTIONAL_RENEWAL', 'AUTOMATIC_RENEWAL', 'POST_EXPIRY_CONTINUATION'],
    'renewal_notice': ['TERMINATION', 'OPTIONAL_RENEWAL', 'AUTOMATIC_RENEWAL', 'POST_EXPIRY_CONTINUATION'],
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha(path):
    return digest(path.read_bytes())


def verify_graphs():
    lock = read(RUN / 'graph-lock.json')
    for name, expected in lock['files'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Sealed extraction changed: ' + name)
    return lock


def topic(query):
    # Fixed public CUAD task wording; no source IDs, gold spans or answer text.
    if re.search(r'expiration date', query, re.I):
        return 'expiry'
    if re.search(r'notice period.*terminate.*renewal', query, re.I):
        return 'renewal_notice'
    if re.search(r'renewal term', query, re.I):
        return 'renewal'
    return None


def prepare():
    verify_graphs()
    if OUT.exists():
        raise ValueError('Comparison folder exists; preserve the first protocol/results')
    OUT.mkdir()
    files = [Path(__file__), ROOT/'scripts/compare_retrieval.py',
             ROOT/'scripts/evaluate.py', ROOT/'scripts/pipeline.py']
    protocol = dict(created_at=datetime.now(timezone.utc).isoformat(),
        graph_lock_sha256=sha(RUN/'graph-lock.json'),
        code_hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in files},
        ingestion=INGESTION, top_k=5, character_budget=6000, topic_kinds=KINDS,
        scope='Expiry, renewal term, renewal notice. Selected from query text only.',
        agreement_routing='Benchmark supplies the correct contract to ALL methods. Not an end-to-end entity-routing test. File identity comes from benchmark metadata; offsets/answers are used only by scoring.',
        vector='Pinned BGE query embedding; exact pgvector cosine ranking of original chunks within supplied contract; top 5.',
        catalogue='Same BGE query, cosine ranking of ALL distinct extracted evidence passages in supplied contract; top 5. No kind filters or relationship traversal.',
        ontology='Same BGE query, cosine ranking of distinct evidence passages of query-selected rule kinds; top 5 seed passages; follow subject_to/supported_by and resolved reference links for seed rules. No fallback to gold or other kinds.',
        budgeting='All methods capped at 6000 unique source characters, ranked order, overlap removed.',
        metrics='Macro character-overlap precision/recall using pinned LegalBench-RAG; latency includes query embedding per method (shared embedding measured once and charged equally), candidate lookup/ranking and budgeting; excludes scoring and cold setup.',
        splits='Report development and not_in_known_exposure_artifacts separately; neither proves pretraining/historical blinding.',
        prior_knowledge='Task templates and earlier experiments were already inspected. No claim of fresh blindness. This protocol is frozen before running this comparison; extraction remains sealed.',
        ablation='Compare ontology seed-only vs relationship-expanded source ranges before budget to measure additional evidence.',
        local_api_cost_usd=0, cost_caveat='Local CPU/GPU, electricity, labor and hardware are not priced.')
    save(OUT/'protocol.json', protocol)
    (OUT/'code-snapshot.py').write_bytes(Path(__file__).read_bytes())
    print('Comparison protocol frozen.', flush=True)


def passage(g, node):
    return dict(evidence_id=str(node), file_path=str(g.value(node, CT.source_path)),
        span=[int(g.value(node, CT.start_char)), int(g.value(node, CT.end_char))],
        text=str(g.value(node, CT.exact_text)))


def catalogue(g):
    return sorted((passage(g, n) for n in g.subjects(RDF.type, CT.SourcePassage)),
                  key=lambda p:(p['span'],p['evidence_id']))


def rank_passages(items, vectors, query_vector, eligible=None, k=5):
    scored = [(float(vectors[p['evidence_id']] @ query_vector), p) for p in items
              if eligible is None or p['evidence_id'] in eligible]
    scored.sort(key=lambda pair:(-pair[0],pair[1]['span'],pair[1]['evidence_id']))
    return [{**p, 'cosine_similarity':s} for s,p in scored[:k]]


def graph_candidates(g, document_id, query_topic, items, vectors, query_vector, k=5):
    rules = sorted((r for r in g.objects(EX[document_id],CT.has_rule)
                    if str(g.value(r,CT.kind)) in KINDS[query_topic]), key=str)
    eligible = {str(p) for r in rules for p in g.objects(r,CT.supported_by)}
    seeds = rank_passages(items,vectors,query_vector,eligible,k)
    candidates = list(seeds); seen = {p['evidence_id'] for p in seeds}; paths=[]
    for seed in seeds:
        for rule in rules:
            if str(seed['evidence_id']) not in {str(p) for p in g.objects(rule,CT.supported_by)}:
                continue
            paths.append(dict(rule=str(rule),kind=str(g.value(rule,CT.kind)),evidence=seed['evidence_id']))
            linked=[]
            for condition in sorted(g.objects(rule,CT.subject_to),key=str):
                linked.extend(g.objects(condition,CT.supported_by))
            for predicate in (CT.references_section,CT.applies_within,CT.agreement_effective_from,
                              CT.starts_from,CT.ends_on_event):
                for reference in sorted(g.objects(rule,predicate),key=str):
                    linked.extend(g.objects(reference,CT.resolved_to))
            for node in sorted(set(linked),key=str):
                if str(node) not in seen:
                    candidates.append(passage(g,node)); seen.add(str(node))
    return candidates, seeds, paths


def summarize(rows):
    if not rows:
        return None
    return {m:dict(questions=len(rows), precision=mean(r[m]['precision'] for r in rows),
        recall=mean(r[m]['recall'] for r in rows),
        mean_ms=mean(r[m]['retrieval_seconds']*1000 for r in rows),
        median_ms=median(r[m]['retrieval_seconds']*1000 for r in rows),
        p95_ms=float(np.percentile([r[m]['retrieval_seconds']*1000 for r in rows],95)),
        mean_characters=mean(r[m]['returned_characters'] for r in rows),
        full_recall=sum(r[m]['recall']>=.999999 for r in rows),
        zero_recall=sum(r[m]['recall']==0 for r in rows)) for m in METHODS}


def evaluate():
    verify_graphs(); protocol=read(OUT/'protocol.json')
    if (OUT/'evaluation-unlock.json').exists():
        raise ValueError('First comparison already unlocked; preserve results')
    if protocol['graph_lock_sha256'] != sha(RUN/'graph-lock.json'):
        raise ValueError('Graph lock changed')
    for name,expected in protocol['code_hashes'].items():
        if sha(ROOT/name)!=expected: raise ValueError('Comparison code changed: '+name)
    manifest=read(RUN/'manifest.json'); docs=manifest['documents']; bypath={d['file_path']:d for d in docs}
    texts={d['file_path']:(ROOT/'data/corpus'/d['local_file_path']).read_text(encoding='utf-8') for d in docs}
    setup=time.perf_counter()
    graphs={d['id']:Graph().parse(ROOT/d['turtle_path']) for d in docs}
    cats={id:catalogue(g) for id,g in graphs.items()}; all_items=[p for items in cats.values() for p in items]
    graph_setup=time.perf_counter()-setup
    types=upstream()
    with connect() as conn:
        register_vector(conn)
        config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(INGESTION,)).fetchone()[0]
        if config['model']!=MODEL:raise ValueError('Wrong vector embedding model')
        dbpaths={r[0] for r in conn.execute('SELECT DISTINCT file_path FROM rag_lab.chunks WHERE ingestion_id=%s',(INGESTION,))}
        if dbpaths!=set(texts):raise ValueError('Wrong document scope in PostgreSQL')
        started=time.perf_counter(); model,revision=load_model(config['revision'],local_files_only=True)
        model_load=time.perf_counter()-started
        token_lengths=[len(model.tokenizer.encode(p['text'])) for p in all_items]
        started=time.perf_counter()
        embeddings=model.encode([p['text'] for p in all_items],normalize_embeddings=True,batch_size=32,show_progress_bar=False)
        index_seconds=time.perf_counter()-started
        vectors={p['evidence_id']:v for p,v in zip(all_items,embeddings)}
        save(OUT/'evaluation-unlock.json',dict(unlocked_at=datetime.now(timezone.utc).isoformat(),
            protocol_sha256=sha(OUT/'protocol.json'),graph_lock_sha256=sha(RUN/'graph-lock.json')))
        questions=read(ROOT/'experiments/cuad-100/questions.json')['tests']
        selected=[]; excluded=Counter()
        for q in questions:
            t=topic(q['query']); paths={s['file_path'] for s in q['snippets']}
            if not t:excluded['out_of_scope']+=1;continue
            if len(paths)!=1 or not paths<=set(bypath):excluded['unsupported_contract_scope']+=1;continue
            selected.append((q,t,bypath[next(iter(paths))]))
        # Warm embedding inference; cold load and passage-index build are reported separately.
        model.encode(QUERY_PREFIX+'contract term',normalize_embeddings=True)
        results=[]
        for q,t,d in selected:
            query=QUERY_PREFIX+q['query']
            if len(model.tokenizer.encode(query))>model.max_seq_length:raise ValueError('Question too long')
            started=time.perf_counter(); vector=model.encode(query,normalize_embeddings=True)
            embedding_seconds=time.perf_counter()-started
            started=time.perf_counter()
            rows=conn.execute('''SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance
                FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY distance,id LIMIT %s''',
                (vector,INGESTION,d['file_path'],protocol['top_k'])).fetchall()
            raw=[dict(file_path=p,span=[a,b],text=text,distance=dist) for p,a,b,text,dist in rows]
            raw=apply_budget(raw,texts,protocol['character_budget']); vec_seconds=time.perf_counter()-started
            started=time.perf_counter()
            flat=apply_budget(rank_passages(cats[d['id']],vectors,vector,k=protocol['top_k']),texts,protocol['character_budget'])
            flat_seconds=time.perf_counter()-started
            started=time.perf_counter()
            expanded,seeds,paths=graph_candidates(graphs[d['id']],d['id'],t,cats[d['id']],vectors,vector,protocol['top_k'])
            chosen=apply_budget(expanded,texts,protocol['character_budget']); graph_seconds=time.perf_counter()-started
            row=dict(source_index=q['source_index'],question=q['query'],topic=t,document_id=d['id'],
                     file_path=d['file_path'],evaluation_group=d['evaluation_group'],embedding_seconds=embedding_seconds,
                     selected_kinds=KINDS[t],graph_paths=paths,relationship_extra_passages=len(expanded)-len(seeds),
                     relationship_extra_characters=sum(len(p['text']) for p in apply_budget(expanded,texts,10**9))-sum(len(p['text']) for p in apply_budget(seeds,texts,10**9)))
            for method,passages,seconds in [('vector',raw,vec_seconds),('catalogue',flat,flat_seconds),('ontology',chosen,graph_seconds)]:
                row[method]=score(passages,q,texts,types)
                row[method].update(retrieval_seconds=embedding_seconds+seconds,lookup_budget_seconds=seconds)
            results.append(row)
            print(f"{len(results)}/{len(selected)} {d['id']} {t}: recall "+' '.join(f'{m}={row[m]["recall"]:.3f}' for m in METHODS),flush=True)
        conn.rollback()  # Read-only experiment; no database writes.
    splits={'all_in_scope':results,'expiry_primary':[r for r in results if r['topic']=='expiry']}
    for name in ['development','not_in_known_exposure_artifacts']:
        splits[name]=[r for r in results if r['evaluation_group']==name]
        splits[name+'_expiry']=[r for r in splits[name] if r['topic']=='expiry']
    report=dict(completed_at=datetime.now(timezone.utc).isoformat(),protocol=protocol,
        question_file_sha256=sha(ROOT/'experiments/cuad-100/questions.json'),upstream=types[0],
        model_revision=revision,setup=dict(graph_parse_seconds=graph_setup,model_load_seconds=model_load,
        passage_embedding_seconds=index_seconds,passages=len(all_items),
        passages_truncated_by_embedding_model=sum(n>model.max_seq_length for n in token_lengths)),
        excluded=dict(excluded),summaries={name:summarize(rows) for name,rows in splits.items()},
        documents_with_questions=len({r['document_id'] for r in results}),
        documents_without_in_scope_questions=[d['id'] for d in docs if not any(r['document_id']==d['id'] for r in results)],
        relationship_ablation=dict(questions_with_additional_passages=sum(r['relationship_extra_passages']>0 for r in results),
                                   total_additional_characters=sum(r['relationship_extra_characters'] for r in results)),
        results=results)
    save(OUT/'results.json',report)
    with (OUT/'results.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['source_index','document_id','topic','evaluation_group','method','precision','recall','retrieval_ms','returned_characters']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in results:
            for m in METHODS:
                writer.writerow({**{k:r[k] for k in fields[:4]},'method':m,
                    'precision':r[m]['precision'],'recall':r[m]['recall'],
                    'retrieval_ms':r[m]['retrieval_seconds']*1000,'returned_characters':r[m]['returned_characters']})
    lines=['# Three-way retrieval comparison','',f"{len(results)} in-scope questions across {report['documents_with_questions']} contracts. All 100 graphs remain unchanged.",'',
        '**Scope:** the benchmark supplies the correct contract to every method. This is not a test of finding the contract across the corpus. Top 5 seeds/candidates, at most 6,000 unique source characters each. No answer-generation model is scored.', '',
        '| Set | Method | Precision | Recall | Mean latency | Mean characters | Full recall |',
        '|---|---|---:|---:|---:|---:|---:|']
    for name,stats in report['summaries'].items():
        if not stats:continue
        for method,v in stats.items():
            lines.append(f"| {name} | {method} | {v['precision']:.1%} | {v['recall']:.1%} | {v['mean_ms']:.2f} ms | {v['mean_characters']:.0f} | {v['full_recall']}/{v['questions']} |")
    lines+=['','## What this establishes','',
        'Vector searches original chunks. Catalogue searches the extracted passages without graph semantics. Ontology first filters rule kinds from the question topic, ranks their evidence and follows supported condition/reference links.',
        f"Relationship traversal added evidence on {report['relationship_ablation']['questions_with_additional_passages']} questions. An ontology gain here may come from category filtering, not multi-hop reasoning.",
        '', 'Precision and recall measure character overlap with benchmark evidence, not legal answer accuracy. Extra useful context can lower precision. Previously inspected documents are development; other documents are only absent from known exposure logs, not proven blind.',
        '',f"Cold setup excluded from query timings: graph parsing {graph_setup:.2f}s; BGE loading {model_load:.2f}s; extracted-passage embeddings {index_seconds:.2f}s. {report['setup']['passages_truncated_by_embedding_model']} extracted passages exceeded the embedding model limit and were truncated for embedding only (original evidence retained). Query embedding is charged equally to all three methods; scoring and diagnostics are excluded. Single warm run, no significance claim.",
        '', 'Paid inference/embedding API spend: $0. Hardware, electricity, labor, extraction and review costs are not priced. The catalogue and ontology both require the same previously generated extraction; vector uses the existing ingestion. Extraction responses/metrics remain in artifacts/llm100-v1.',
        '', '[Full question-level results](results.json) · [CSV](results.csv) · [Frozen protocol](protocol.json)',
        '', '## Per-question inspection','', '| Source ID | Contract | Topic | Vector recall | Catalogue recall | Ontology recall |', '|---|---|---|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['source_index']} | {r['document_id']} | {r['topic']} | {r['vector']['recall']:.1%} | {r['catalogue']['recall']:.1%} | {r['ontology']['recall']:.1%} |")
    (OUT/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    verify_graphs()
    print(json.dumps(report['summaries'],indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','evaluate'])
    args=parser.parse_args()
    {'prepare':prepare,'evaluate':evaluate}[args.command]()
