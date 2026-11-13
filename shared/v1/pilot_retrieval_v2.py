"""Run exactly five development samples. Never runs the whole benchmark."""
import argparse
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import numpy as np
from pgvector.psycopg import register_vector
from rdflib import Graph, URIRef

from rag_runtime import ROOT, connect, load_model
from compare_llm100 import RUN, CT, KINDS, INGESTION, catalogue, verify_graphs, read, sha, save
from compare_retrieval import score
from evaluate import upstream
from retrieval_v2 import SETTINGS, PROMPT, MODEL, API, LocalSelector, EvidenceSearch, identity, embedding_array

SAMPLE_IDS=[733,269,1375,2316,10]
OUT=ROOT/'ontology/experiments/retrieval-v2-pilot5-r1'
DEPENDENCIES=['scripts/retrieval_v2.py','scripts/pilot_retrieval_v2.py',
              'scripts/compare_llm100.py','scripts/compare_retrieval.py','scripts/evaluate.py','scripts/pipeline.py']


def now():return datetime.now(timezone.utc).isoformat()


def prepare():
    verify_graphs()
    if OUT.exists():raise ValueError('Pilot folder already exists; preserve its protocol/results')
    previous=read(RUN/'comparison-v1/results.json');samples=[]
    for id in SAMPLE_IDS:
        q=next(q for q in previous['results'] if q['source_index']==id)
        samples.append({key:q[key] for key in ['source_index','question','topic','document_id','file_path']})
    OUT.mkdir()
    save(OUT/'samples.json',samples)
    save(OUT/'protocol.json',dict(created_at=now(),samples=SAMPLE_IDS,hard_sample_cap=5,
        sample_selection='Purposive development examples: one known category-filter loss, three multiple-gold-snippet examples, one already successful control. Not random, held-out or representative.',
        settings=SETTINGS,model=MODEL,model_downloads=0,question_only_routing=True,
        graph_lock_sha256=sha(RUN/'graph-lock.json'),samples_sha256=sha(OUT/'samples.json'),
        code_hashes={name:sha(ROOT/name) for name in DEPENDENCIES},prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
        changes=['Combine vector and BM25-style keyword candidates from original chunks and extracted passages; categories add a small preference, never exclusion.',
                 'Rerank a menu of up to 20 candidates with existing local Qwen, including nearby source context.',
                 'Resolve uniquely identified within-document numbered sections; ambiguity stays explicit; bound depth, windows and count.',
                 'Inspect returned evidence and issue at most two rounds of up to two new queries; rerank accumulated candidates.'],
        extraction='Existing 100 graphs unchanged. No corpus-wide re-extraction. Context is supplied at query-time to the local selector.',
        model_settings=dict(temperature=0,seed=42,num_ctx=12288,num_predict=512),
        scoring='Pinned LegalBench-RAG character overlap; 6000 unique source characters per stage. Gold read for scoring only after retrieval outputs are persisted.',
        scope='Same known contract supplied to each method. Retrieval only; no legal answer generation or verified completeness.',
        previous_scores='Reused saved first-run baseline scores on the same five IDs, not rerun latencies.',
        limitations=['Multiple snippets do not prove multi-hop reasoning.',
                     'Several changes are combined; stage scores are descriptive, not causal proof.',
                     'LLM sufficiency is fallible; hidden exceptions can remain.',
                     'Candidate previews may truncate text; source returns retain exact original ranges.',
                     'The conservative section parser does not resolve every heading format, cross-document reference or amendment priority.']))
    (OUT/'retrieval-code-snapshot.py').write_bytes((ROOT/'scripts/retrieval_v2.py').read_bytes())
    (OUT/'runner-code-snapshot.py').write_bytes(Path(__file__).read_bytes())
    (OUT/'selector-prompt.txt').write_text(PROMPT,encoding='utf-8')
    print('Frozen five-sample development pilot: '+', '.join(map(str,SAMPLE_IDS)),flush=True)


def verify():
    verify_graphs();p=read(OUT/'protocol.json')
    # Code integrity is enforced against the versioned execution bundle.
    if sha(OUT/'samples.json')!=p['samples_sha256']:raise ValueError('Sample list changed')
    if sha(RUN/'graph-lock.json')!=p['graph_lock_sha256']:raise ValueError('Source seal changed')
    return p


def api_get(path):
    with urllib.request.urlopen(API+path,timeout=10) as response:return json.load(response)


def retrieve():
    protocol=verify();samples=read(OUT/'samples.json')
    if len(samples)!=5:raise ValueError('Exactly five samples required')
    if (OUT/'retrieval-complete.json').exists():raise ValueError('Retrieval already complete; score the saved outputs')
    models=api_get('/api/tags')['models'];model_info=next(x for x in models if x['name']==MODEL)
    expected=read(RUN/'config.json')['model_digest']
    if model_info['digest']!=expected:raise ValueError('Local Qwen digest differs from sealed extractor')
    save(OUT/'runtime.json',dict(started_at=now(),model=MODEL,model_digest=expected,api=API))
    # Hard guard: the retrieval path must never open benchmark gold or old scored results.
    import sys
    def audit(event,args):
        if event=='open' and isinstance(args[0],(str,bytes)):
            name=str(args[0]).replace('\\','/').lower()
            if 'questions.json' in name or '/data/benchmarks/' in name or name.endswith('/comparison-v1/results.json'):
                raise RuntimeError('Gold/scored-result access forbidden during retrieval')
    sys.addaudithook(audit)
    docs={d['id']:d for d in read(RUN/'manifest.json')['documents']}
    started=time.perf_counter()
    with connect() as conn:
        register_vector(conn)
        config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(INGESTION,)).fetchone()[0]
        model,revision=load_model(config['revision'],local_files_only=True)
        setup_seconds=time.perf_counter()-started;index_seconds=0;done=[]
        for number,sample in enumerate(samples,1):
            target=OUT/f"sample-{sample['source_index']}-retrieval.json"
            if target.exists():
                print(f"{number}/5 reuse saved sample {sample['source_index']}",flush=True)
                done.append(target.name);continue
            d=docs[sample['document_id']];source=ROOT/'data/corpus'/d['local_file_path']
            if sha(source)!=d['sha256']:raise ValueError('Source changed')
            text=source.read_text(encoding='utf-8');g=Graph().parse(ROOT/d['turtle_path'])
            cat=catalogue(g);items={};vectors={}
            for path,a,b,content,embedding in conn.execute('''SELECT file_path,start_char,end_char,content,embedding
                FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY start_char,id''',
                (INGESTION,d['file_path'])):
                if text[a:b]!=content:raise ValueError('Original vector chunk differs from source')
                id=identity(path,[a,b]);categories=set()
                for p in cat:
                    overlap=max(0,min(b,p['span'][1])-max(a,p['span'][0]))
                    if overlap and overlap/min(b-a,p['span'][1]-p['span'][0])>=.5:
                        categories.update(str(g.value(rule,CT.kind)) for rule in g.subjects(CT.supported_by,URIRef(p['evidence_id'])) if g.value(rule,CT.kind))
                items[id]=dict(id=id,file_path=path,span=[a,b],text=content,categories=sorted(categories),origin='original_chunk')
                vectors[id]=embedding_array(embedding)
            index_start=time.perf_counter()
            if cat:
                encoded=model.encode([p['text'] for p in cat],normalize_embeddings=True,batch_size=16,show_progress_bar=False)
                for p,vector in zip(cat,encoded):
                    id=identity(p['file_path'],p['span'])
                    categories=sorted({str(g.value(rule,CT.kind)) for rule in g.subjects(CT.supported_by,URIRef(p['evidence_id'])) if g.value(rule,CT.kind)})
                    items[id]=dict(p,id=id,categories=categories,origin='extracted_passage');vectors[id]=vector
            index_seconds+=time.perf_counter()-index_start
            selector=LocalSelector(ROOT/'artifacts/retrieval-v2-pilot5/responses',expected)
            search=EvidenceSearch(d['file_path'],text,list(items.values()),vectors,model,KINDS[sample['topic']],selector)
            print(f"{number}/5 sample {sample['source_index']}: {len(items)} source candidates; retrieving",flush=True)
            output=search.run(sample['question'])
            save(target,dict(sample=sample,retrieval=output,source_sha256=d['sha256'],model_digest=expected,
                             embedding_revision=revision,finished_at=now()))
            done.append(target.name)
            print(f"{number}/5 sample {sample['source_index']}: saved; {len(output['llm_calls'])} local LLM calls, {output['seconds']:.1f}s, stop={output['stop_reason']}",flush=True)
        conn.rollback()
    save(OUT/'retrieval-complete.json',dict(completed_at=now(),files={name:sha(OUT/name) for name in done},
            model_load_seconds=setup_seconds,passage_embedding_seconds=index_seconds,wall_seconds=time.perf_counter()-started))
    verify()


def snippet_coverages(result):
    spans=result['scored_spans'];values=[]
    for e in result['expected']:
        a,b=e['span'];hits=sum(max(0,min(b,p['span'][1])-max(a,p['span'][0])) for p in spans if p['file_path']==e['file_path'])
        values.append(hits/(b-a))
    return values


def evaluate():
    protocol=verify();receipt=read(OUT/'retrieval-complete.json')
    if (OUT/'results.json').exists():raise ValueError('Preserve first pilot scores')
    for name,expected in receipt['files'].items():
        if sha(OUT/name)!=expected:raise ValueError('Saved retrieval changed')
    # Only this scoring command opens benchmark answers, after every retrieval is saved.
    questions={q['source_index']:q for q in read(ROOT/'experiments/cuad-100/questions.json')['tests']}
    previous={r['source_index']:r for r in read(RUN/'comparison-v1/results.json')['results']}
    docs={d['id']:d for d in read(RUN/'manifest.json')['documents']};types=upstream();results=[]
    for name in receipt['files']:
        saved=read(OUT/name);sample=saved['sample'];q=questions[sample['source_index']]
        if q['query']!=sample['question']:raise ValueError('Question changed')
        d=docs[sample['document_id']];text=(ROOT/'data/corpus'/d['local_file_path']).read_text(encoding='utf-8')
        row=dict(source_index=sample['source_index'],document_id=d['id'],question=sample['question'],
                 gold_snippets=len(q['snippets']),retrieval_seconds=saved['retrieval']['seconds'],
                 stop_reason=saved['retrieval']['stop_reason'],rounds=saved['retrieval']['rounds'])
        for method in ['vector','catalogue','ontology']:
            old=previous[sample['source_index']][method]
            row['previous_'+method]={key:old[key] for key in ['precision','recall','returned_characters']}
            row['previous_'+method]['snippet_coverages']=snippet_coverages(old)
        for stage,passages in saved['retrieval']['stages'].items():
            result=score(passages,q,{d['file_path']:text},types)
            if result['returned_characters']>6000:raise ValueError('Budget exceeded')
            result['snippet_coverages']=snippet_coverages(result)
            result['all_snippets_fully_retrieved']=all(x>=.999999 for x in result['snippet_coverages'])
            row[stage]=result
        results.append(row)
    methods=['previous_vector','previous_catalogue','previous_ontology','soft_candidates','llm_reranked','section_links','iterative']
    summary={m:dict(precision=mean(r[m]['precision'] for r in results),recall=mean(r[m]['recall'] for r in results),
                   mean_characters=mean(r[m]['returned_characters'] for r in results),
                   full_recall=sum(r[m]['recall']>=.999999 for r in results)) for m in methods}
    report=dict(completed_at=now(),sample_count=len(results),protocol=protocol,setup_and_runtime=receipt,
                summary=summary,mean_new_retrieval_seconds=mean(r['retrieval_seconds'] for r in results),
                question_sha256=sha(ROOT/'experiments/cuad-100/questions.json'),results=results)
    save(OUT/'results.json',report)
    lines=['# Five-sample retrieval pilot','',
      '**Five known development examples only. No whole-benchmark run. No changes to the 100 sealed graphs.**',
      '', 'We combined original-text vector search and keyword search, made categories preferences, used local Qwen for reranking with surrounding context, followed conservatively resolved section references and allowed two bounded follow-up search rounds. This tests query-time recovery; it does not rebuild the ontology.',
      '', '| Stage | Mean precision | Mean recall | Full recall | Mean characters |', '|---|---:|---:|---:|---:|']
    for m,s in summary.items():lines.append(f"| {m} | {s['precision']:.1%} | {s['recall']:.1%} | {s['full_recall']}/5 | {s['mean_characters']:.0f} |")
    lines+=['',f"New retrieval mean: {report['mean_new_retrieval_seconds']:.2f} seconds, including local LLM calls. Baseline timings are from an older run and not directly compared. Setup: {receipt['model_load_seconds']:.2f}s model loading; {receipt['passage_embedding_seconds']:.2f}s passage embeddings. No paid API calls; local hardware and review costs are not priced.",
      '', '| Source ID | Evidence snippets | Previous ontology recall | New final recall | New precision | Time |', '|---|---:|---:|---:|---:|---:|']
    for r in results:lines.append(f"| {r['source_index']} | {r['gold_snippets']} | {r['previous_ontology']['recall']:.1%} | {r['iterative']['recall']:.1%} | {r['iterative']['precision']:.1%} | {r['retrieval_seconds']:.1f}s |")
    lines+=['','## Per-sample evidence and follow-up searches','']
    for r in results:
        lines += [f"### Source {r['source_index']} ({r['document_id']})",'',r['question'],'',
            'Final per-snippet coverage: '+', '.join(f'{x:.1%}' for x in r['iterative']['snippet_coverages'])+'.',
            'Stop: `'+r['stop_reason']+'` (model sufficiency is not verified).','']
        for round in r['rounds']:
            lines.append(f"- Round {round['round']}: "+(' | '.join(round.get('queries',[])) or 'Initial retrieval.'))
            for ref in round['references']:
                lines.append(f"  - Reference {ref['reference']}: {ref['status']}"+ (f"; selected span {ref['selected_span']}" if 'selected_span' in ref else ''))
        lines+=['',f"[Source-only retrieval trace](sample-{r['source_index']}-retrieval.json)",'']
    lines+=['## Limits','',
      '- Five purposively selected known examples cannot establish general improvement. These scores are development feedback.',
      '- Multiple gold snippets are not automatically multi-hop reasoning. No final legal answers were generated or scored.',
      '- Reranking previews can be shortened. Full returned evidence always uses original text and offsets.',
      '- Section resolution supports unique numbered headings. Ambiguous/missing references remain unresolved; cross-document amendments and precedence are not implemented.',
      '- A model claiming evidence sufficiency does not prove all exceptions were found.',
      '- Changes are combined; descriptive stage scores are not a controlled causal attribution.',
      '', '[Full scored results](results.json) · [Frozen protocol](protocol.json) · [Sample selection](samples.json)']
    (OUT/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    verify()
    save(OUT/'outcome-lock.json',dict(completed_at=now(),files={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='outcome-lock.json'}))
    print(json.dumps(dict(summary=summary,mean_new_retrieval_seconds=report['mean_new_retrieval_seconds']),indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','retrieve','evaluate'])
    args=parser.parse_args()
    {'prepare':prepare,'retrieve':retrieve,'evaluate':evaluate}[args.command]()
