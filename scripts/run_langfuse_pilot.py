"""Live Langfuse tracing of at most the five existing development samples."""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime,timezone
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from rdflib import Graph,URIRef

from pipeline import ROOT,connect,load_model
from compare_llm100 import RUN,CT,KINDS,INGESTION,catalogue,read,save,sha,verify_graphs
from retrieval_v2 import API,MODEL,identity,embedding_array
from langfuse_retrieval import TracedEmbedding,TracedSearch,TracedSelector,safe_mask,HOSTED_RATE

SOURCE=ROOT/'ontology/experiments/retrieval-v2-pilot5-r1'


def load_items(conn,doc,model):
    path=ROOT/'data/corpus'/doc['local_file_path']
    if sha(path)!=doc['sha256']:raise ValueError('Source contract changed')
    text=path.read_text(encoding='utf-8');g=Graph().parse(ROOT/doc['turtle_path']);cat=catalogue(g)
    def kinds(p):return {str(g.value(r,CT.kind)) for r in g.subjects(CT.supported_by,URIRef(p['evidence_id'])) if g.value(r,CT.kind)}
    items={};vectors={}
    for file_path,a,b,content,vector in conn.execute('''SELECT file_path,start_char,end_char,content,embedding
        FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY start_char,id''',
        (INGESTION,doc['file_path'])):
        if text[a:b]!=content:raise ValueError('Stored chunk differs from original contract')
        categories=set()
        for p in cat:
            overlap=max(0,min(b,p['span'][1])-max(a,p['span'][0]))
            if overlap and overlap/min(b-a,p['span'][1]-p['span'][0])>=.5:categories.update(kinds(p))
        id=identity(file_path,[a,b])
        items[id]=dict(id=id,file_path=file_path,span=[a,b],text=content,categories=sorted(categories),origin='original_chunk')
        vectors[id]=embedding_array(vector)
    if cat:
        encoded=model.encode([p['text'] for p in cat],normalize_embeddings=True,batch_size=16,show_progress_bar=False)
        for p,vector in zip(cat,encoded):
            id=identity(p['file_path'],p['span'])
            items[id]=dict(p,id=id,categories=sorted(kinds(p)),origin='extracted_passage');vectors[id]=vector
    return text,list(items.values()),vectors


def unload():
    req=urllib.request.Request(API+'/api/generate',data=json.dumps({'model':MODEL,'keep_alive':0}).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:json.load(response)


def run(limit):
    if not 1<=limit<=5:raise ValueError('This integration runs between one and five samples only')
    from pilot_retrieval_v2 import verify
    verify();verify_graphs();load_dotenv(ROOT/'.env')
    from langfuse import Langfuse,propagate_attributes
    lf=Langfuse(base_url=os.environ['LANGFUSE_BASE_URL'],environment='local-development',
                release='retrieval-v2-langfuse-v1',mask=safe_mask)
    if not lf.auth_check():raise RuntimeError('Langfuse authentication failed')
    name='langfuse-pilot5-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'artifacts'/name;out.mkdir()
    samples=read(SOURCE/'samples.json')[:limit];docs={d['id']:d for d in read(RUN/'manifest.json')['documents']}
    with urllib.request.urlopen(API+'/api/tags',timeout=10) as response:models=json.load(response)['models']
    model_info=next(m for m in models if m['name']==MODEL)
    if model_info['digest']!=read(RUN/'config.json')['model_digest']:raise ValueError('Wrong local model digest')
    save(out/'run.json',dict(run=name,source_samples=[s['source_index'] for s in samples],
        sdk_version='5.2.0',model=MODEL,graph_lock_sha256=sha(RUN/'graph-lock.json'),
        adapter_sha256=sha(ROOT/'scripts/langfuse_retrieval.py'),
        runner_sha256=sha(Path(__file__)),hosted_estimate_rate=HOSTED_RATE,
        note='Fresh live instrumentation. Qwen reset between samples to limit GPU memory growth. No paid model API calls.'))
    try:
        with connect() as conn:
            register_vector(conn)
            config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(INGESTION,)).fetchone()[0]
            model,revision=load_model(config['revision'],local_files_only=True)
            for index,sample in enumerate(samples,1):
                print(f"{index}/{limit} trace sample {sample['source_index']}",flush=True)
                with propagate_attributes(session_id=name,tags=['retrieval-v2','pilot5','local-qwen','development'],
                    trace_name='contract-evidence-retrieval',metadata={'source_index':str(sample['source_index'])}):
                    with lf.start_as_current_observation(name='contract-evidence-retrieval',as_type='chain',
                        input={'question':sample['question'],'contract':sample['file_path'],'source_index':sample['source_index']},
                        metadata={'sample_scope':'known-development','max_followup_rounds':2,
                                  'character_budget':6000,'backend':'local-ollama','answer_generation':False}) as root:
                        trace_id=root.trace_id;root_id=root.id
                        with lf.start_as_current_observation(name='load-contract-and-catalogue',as_type='span',
                            input={'document_id':sample['document_id'],'file_path':sample['file_path']}) as setup:
                            text,items,vectors=load_items(conn,docs[sample['document_id']],model)
                            setup.update(output={'candidate_count':len(items),'source_characters':len(text),
                                'origins':{origin:sum(p['origin']==origin for p in items) for origin in ['original_chunk','extracted_passage']},
                                'source_sha256':docs[sample['document_id']]['sha256']})
                        # Fresh response cache per instrumented run: a live timing experiment, not a replay.
                        selector=TracedSelector(out/'responses',model_info['digest'],lf)
                        traced_model=TracedEmbedding(model,lf,revision)
                        search=TracedSearch(sample['file_path'],text,items,vectors,traced_model,
                            KINDS[sample['topic']],selector,langfuse=lf)
                        # Guard benchmark/gold reads only during the source-only retrieval call.
                        import builtins
                        from unittest.mock import patch
                        real_open=builtins.open;real_io_open=__import__('io').open
                        def guarded(opener):
                            def open_checked(file,*args,**kwargs):
                                path=str(file).replace('\\','/').lower()
                                if 'questions.json' in path or '/data/benchmarks/' in path or path.endswith('/comparison-v1/results.json'):
                                    raise RuntimeError('Gold access forbidden during traced retrieval')
                                return opener(file,*args,**kwargs)
                            return open_checked
                        with patch('builtins.open',guarded(real_open)),patch('io.open',guarded(real_io_open)):
                            result=search.run(sample['question'])
                        root.update(output={'passages':result['stages']['iterative'],'stop_reason':result['stop_reason'],
                            'followup_queries':[q['query'] for q in result['queries'][1:]],
                            'retrieval_seconds':result['seconds'],'actual_paid_api_cost_usd':0,
                            'hosted_equivalent_estimate_usd':selector.hosted_equivalent_usd},
                            metadata={'source_index':sample['source_index'],'document_id':sample['document_id'],
                                'llm_calls':len(selector.calls),'retrieval_only':True,
                                'sufficiency_warning':'A model stop flag is not verified completeness.'})
                    trace_url=lf.get_trace_url(trace_id=trace_id)
                    save(out/f"sample-{sample['source_index']}.json",dict(sample=sample,retrieval=result,
                        trace_id=trace_id,root_observation_id=root_id,trace_url=trace_url,
                        hosted_equivalent_estimate_usd=selector.hosted_equivalent_usd))
                    print(f"Saved trace {trace_id}; {result['seconds']:.1f}s",flush=True)
                lf.flush()
                unload()
            conn.rollback()
        # All source-only retrievals are complete before any benchmark answers are opened.
        from compare_retrieval import score
        from evaluate import upstream
        types=upstream();bank={q['source_index']:q for q in read(ROOT/'experiments/cuad-100/questions.json')['tests']}
        previous={q['source_index']:q for q in read(RUN/'comparison-v1/results.json')['results']}
        results=[]
        lf.create_dataset(name='cuad-retrieval-development-5',description='Five known development samples; not unseen or representative.',
            metadata={'scope':'retrieval character overlap, no final-answer scoring'})
        for sample in samples:
            saved=read(out/f"sample-{sample['source_index']}.json");q=bank[sample['source_index']]
            if q['query']!=sample['question']:raise ValueError('Question changed')
            text=(ROOT/'data/corpus'/docs[sample['document_id']]['local_file_path']).read_text(encoding='utf-8')
            scored={stage:score(passages,q,{sample['file_path']:text},types)
                    for stage,passages in saved['retrieval']['stages'].items()}
            final=scored['iterative'];trace_id=saved['trace_id']
            metrics={'evidence_precision':final['precision'],'evidence_recall':final['recall'],
                'full_evidence_retrieved':int(final['recall']>=.999999),
                'retrieval_seconds':saved['retrieval']['seconds'],
                'hosted_equivalent_estimate_usd':saved['hosted_equivalent_estimate_usd'],
                'baseline_ontology_recall':previous[sample['source_index']]['ontology']['recall']}
            metrics.update({'recall_'+stage:s['recall'] for stage,s in scored.items() if stage!='iterative'})
            for metric,value in metrics.items():
                lf.create_score(trace_id=trace_id,name=metric,value=value,
                    data_type='BOOLEAN' if metric=='full_evidence_retrieved' else 'NUMERIC',
                    comment='Character-overlap development evaluation; not legal-answer correctness. Hosted cost is counterfactual, actual paid model API cost is zero.')
            item=lf.create_dataset_item(dataset_name='cuad-retrieval-development-5',id='cuad-source-'+str(sample['source_index']),
                input={'question':sample['question'],'file_path':sample['file_path']},
                expected_output={'evidence':final['expected']},source_trace_id=trace_id,
                metadata={'source_index':sample['source_index'],'document_id':sample['document_id'],'split':'development'})
            saved['metrics']=metrics;saved['scored_stages']=scored;saved['dataset_item_id']=item.id
            save(out/f"sample-{sample['source_index']}.json",saved)
            results.append({'source_index':sample['source_index'],'trace_id':trace_id,'trace_url':saved['trace_url'],
                            'metrics':metrics})
        verify_graphs();lf.flush()
        save(out/'results.json',dict(run=name,sample_count=len(results),results=results,
            note='Live traces; local Qwen reset between questions; new timings/scores are not replacements for frozen pilot results.'))
        lines=['# Langfuse live pilot','',f'Run: {name}. Only {len(results)} known development samples.', '',
               '| Source | Recall | Precision | Retrieval | Langfuse |','|---|---:|---:|---:|---|']
        for row in results:
            m=row['metrics'];lines.append(f"| {row['source_index']} | {m['evidence_recall']:.1%} | {m['evidence_precision']:.1%} | {m['retrieval_seconds']:.1f}s | [Open trace]({row['trace_url']}) |")
        lines+=['','Each trace shows the exact Qwen request/response, original candidate passages, meaning and keyword results, category preference, selected source text, section resolutions and follow-up searches. Precision/recall scores are attached after retrieval completes.','',
            'Langfuse generation costs are actual paid API cost ($0 for local inference). Hosted-equivalent estimates are separately named scores and metadata, with their rate source. They are not a provider bill.','',
            'Five development samples only, no final legal-answer generation. Cold Qwen loading can occur once per question because the model is reset between samples to limit GPU memory growth. Original experiment files and seals remain unchanged.']
        (out/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        print('Report: '+str(out/'results.md'),flush=True)
        return out
    finally:
        lf.flush();lf.shutdown()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=5,choices=range(1,6))
    args=parser.parse_args();run(args.limit)
