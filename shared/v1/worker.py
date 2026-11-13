"""Archived execution worker. Imported project code must live inside this bundle."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.request
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from rag_runtime import ROOT, connect, load_model, QUERY_PREFIX
from compare_llm100 import RUN, CT, KINDS, INGESTION, catalogue, rank_passages, graph_candidates, verify_graphs, read, save, sha
from compare_retrieval import apply_budget
from scorer import score
from evaluate import upstream
from retrieval_v2 import API, MODEL

BUNDLE=Path(__file__).resolve().parents[2]
CONFIG=read(BUNDLE/'experiment/config.json')
DATASET=BUNDLE/'datasets'/CONFIG['dataset']
EVALUATION=BUNDLE/'evaluation'/CONFIG['evaluation_version']
spec=importlib.util.spec_from_file_location('experiment_pipeline',BUNDLE/'experiment/pipeline.py')
experiment_pipeline=importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment_pipeline)
SETTINGS=getattr(experiment_pipeline,'SETTINGS',{})
PROMPT=(BUNDLE/'experiment/prompt.txt').read_text(encoding='utf-8').rstrip('\n')
if hasattr(experiment_pipeline,'PROMPT'):
    if experiment_pipeline.PROMPT != PROMPT:raise ValueError('Pipeline prompt differs from versioned prompt.txt')

def check_model(folder,value):
    expected=folder/'expected-model.json'
    if expected.exists() and read(expected)!=value:raise ValueError('Model identity differs from original run')
    save(folder/'model.json',value)

def validate_database(conn,config,inputs,folder):
    chunks=[]
    for entry in inputs:
        rows=conn.execute('SELECT id,file_path,start_char,end_char,content,embedding::text FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY id', (INGESTION,entry['sample']['file_path'])).fetchall()
        if not rows:raise ValueError('Missing indexed source document')
        chunks.extend([list(r) for r in rows])
    identity={'config':config,'chunks_sha256':hashlib.sha256(json.dumps(chunks,sort_keys=True,default=str).encode()).hexdigest(),'chunk_count':len(chunks)}
    expected=folder/'expected-database.json'
    if expected.exists() and read(expected)!=identity:raise ValueError('Indexed chunks/vectors changed since original run')
    save(folder/'database.json',identity)

def validate_sources(inputs):
    for e in inputs:
        if sha(ROOT/'data/corpus'/e['document']['local_file_path'])!=e['document']['sha256']:
            raise ValueError('Source document changed')
    if read(BUNDLE/'graph-lock.json')!=read(RUN/'graph-lock.json'):
        raise ValueError('Sealed ontology version changed')
    verify_graphs()

def execution_proof(folder):
    modules={}
    for name,module in list(sys.modules.items()):
        path=getattr(module,'__file__',None)
        if path:
            path=Path(path).resolve()
            if any(path.is_relative_to(ROOT/area) for area in ('scripts','shared','evaluation','experiments')):
                raise ValueError('Live project code imported: '+str(path))
            if path.is_relative_to(BUNDLE) and path.is_file():modules[name]={'path':str(path),'sha256':sha(path)}
    save(folder/'execution-proof.json',dict(isolated_python=sys.flags.isolated,modules=modules,sys_path=sys.path))

def now():return datetime.now(timezone.utc).isoformat()

def langfuse_client(enabled):
    if not enabled:return None
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    if not os.getenv('LANGFUSE_SECRET_KEY'):return None
    from langfuse import Langfuse
    from langfuse_retrieval import safe_mask
    client=Langfuse(base_url=os.environ['LANGFUSE_BASE_URL'],environment='local-development',
        release='experiment-lab-v1',mask=safe_mask)
    if not client.auth_check():raise RuntimeError('Langfuse authentication failed')
    return client

def root_trace(client,name,sample,folder):
    return client.start_as_current_observation(name=name,as_type='chain',
        input={'question':sample['question'],'file_path':sample['file_path'],'source_index':sample['source_index']},
        metadata={'experiment':folder.parent.name,'run_id':folder.name,'known_development':True}) if client else nullcontext(None)

def propagation(client,folder):
    if not client:return nullcontext()
    from langfuse import propagate_attributes
    return propagate_attributes(session_id=folder.parent.name+'-'+folder.name,
        tags=['experiment-lab',folder.parent.name,'development'])

def unload_model():
    req=urllib.request.Request(API+'/api/generate',data=json.dumps({'model':MODEL,'keep_alive':0}).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:json.load(response)

def retrieve_selection(folder,inputs,client):
    with urllib.request.urlopen(API+'/api/tags',timeout=10) as response:models=json.load(response)['models']
    digest=next(m['digest'] for m in models if m['name']==MODEL)
    if digest!=read(RUN/'config.json')['model_digest']:raise ValueError('Wrong local Qwen model')
    check_model(folder, {'name':MODEL,'digest':digest,'settings':SETTINGS})
    for index,entry in enumerate(inputs,1):
        sample=entry['sample'];doc=entry['document']
        text=(ROOT/'data/corpus'/doc['local_file_path']).read_text(encoding='utf-8')
        print(f"{index}/{len(inputs)} select sentences: source {sample['source_index']}",flush=True)
        with propagation(client,folder),root_trace(client,'focused-evidence-selection',sample,folder) as root:
            # Fixed saved evidence and original text only; no benchmark gold enters this function.
            selected=experiment_pipeline.select(sample['question'],entry['before'],text,digest,folder/'responses',client)
            if root:root.update(output={'passages':selected['output'],'decision':selected['decision'],
                'selection_status':selected['status'],'source_evidence_unchanged':True})
        saved=dict(sample=sample,output=selected['output'],before=entry['before'],selection=selected,
            seconds=selected['seconds'],timing_scope='additional-selection-only',
            trace_id=root.trace_id if root else None,trace_url=client.get_trace_url(trace_id=root.trace_id) if root else None)
        save(folder/f"output-{sample['source_index']}.json",saved)
        print(f"Saved {sample['source_index']}: {selected['status']}; {sum(len(p['text']) for p in selected['output'])} chars; {selected['seconds']:.1f}s",flush=True)
        if client:client.flush()
        unload_model()

def retrieve_baseline(experiment,folder,inputs,client):
    from pgvector.psycopg import register_vector
    from rdflib import Graph
    with connect() as conn:
        register_vector(conn)
        config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(INGESTION,)).fetchone()[0]
        validate_database(conn, config, inputs, folder)
        model,revision=load_model(config['revision'],local_files_only=True)
        check_model(folder, {'name':config['model'],'revision':revision,'ingestion':INGESTION})
        for entry in inputs:
            sample=entry['sample'];doc=entry['document']
            text=(ROOT/'data/corpus'/doc['local_file_path']).read_text(encoding='utf-8');texts={sample['file_path']:text}
            g=Graph().parse(ROOT/doc['turtle_path']);cat=catalogue(g);vectors={}
            if experiment!='vector-v1' and cat:
                encoded=model.encode([p['text'] for p in cat],normalize_embeddings=True,batch_size=32,show_progress_bar=False)
                vectors={p['evidence_id']:v for p,v in zip(cat,encoded)}
            with propagation(client,folder),root_trace(client,experiment,sample,folder) as root:
                started=time.perf_counter();query=QUERY_PREFIX+sample['question'];vector=model.encode(query,normalize_embeddings=True)
                if experiment_pipeline.METHOD=='vector':
                    rows=conn.execute('''SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance
                        FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY distance,id LIMIT %s''',
                        (vector,INGESTION,sample['file_path'],CONFIG['top_k'])).fetchall()
                    candidates=[dict(file_path=p,span=[a,b],text=t,distance=d) for p,a,b,t,d in rows]
                elif experiment_pipeline.METHOD=='catalogue':candidates=rank_passages(cat,vectors,vector,k=CONFIG['top_k'])
                else:candidates,_,_=graph_candidates(g,sample['document_id'],sample['topic'],cat,vectors,vector,k=CONFIG['top_k'])
                output=apply_budget(candidates,texts,CONFIG['character_budget']);seconds=time.perf_counter()-started
                if root:root.update(output={'passages':output,'retrieval_seconds':seconds})
            save(folder/f"output-{sample['source_index']}.json",dict(sample=sample,output=output,seconds=seconds,
                timing_scope='retrieval-only',trace_id=root.trace_id if root else None,
                trace_url=client.get_trace_url(trace_id=root.trace_id) if root else None))
        conn.rollback()

def score_run(folder,inputs,client=None):
    # Called after every output is persisted. This is the only gold read in this runner.
    types=upstream();bank={e['sample']['source_index']:dict(query=e['sample']['question'],snippets=read(DATASET/'expected-evidence.json')[str(e['sample']['source_index'])]) for e in inputs};results=[]
    for entry in inputs:
        sample=entry['sample'];saved=read(folder/f"output-{sample['source_index']}.json");q=bank[sample['source_index']]
        if q['query']!=sample['question']:raise ValueError('Question version changed')
        doc=entry['document'];source=ROOT/'data/corpus'/doc['local_file_path']
        if sha(source)!=doc['sha256']:raise ValueError('Source changed before scoring')
        text=source.read_text(encoding='utf-8');texts={sample['file_path']:text}
        for passage in saved['output']:
            a,b=passage['span']
            if not 0<=a<b<=len(text) or passage['file_path']!=sample['file_path'] or text[a:b]!=passage['text']:
                raise ValueError('Retrieved evidence does not match original source')
        after=score(copy.deepcopy(saved['output']),q,texts,types)
        before=score(copy.deepcopy(saved['before']),q,texts,types) if 'before' in saved else None
        if after['returned_characters']>6000:raise ValueError('Evidence exceeds budget')
        metrics={'precision':after['precision'],'recall':after['recall'],'returned_characters':after['returned_characters']}
        if before:metrics.update(before_precision=before['precision'],before_recall=before['recall'],
            before_characters=before['returned_characters'],recall_delta=after['recall']-before['recall'])
        if client and saved.get('trace_id'):
            for name,value in metrics.items():client.create_score(trace_id=saved['trace_id'],name=name,value=value,
                data_type='NUMERIC',comment='Fixed-input development experiment. No automatic validation of legal completeness.')
        results.append(dict(source_index=sample['source_index'],question=sample['question'],document_id=sample['document_id'],
            file_path=sample['file_path'],metrics=metrics,before=before,after=after,
            seconds=saved.get('seconds'),timing_scope=saved.get('timing_scope'),
            trace_url=saved.get('trace_url'),selection_status=saved.get('selection',{}).get('status')))
    common=['precision','recall','returned_characters'];summary={k:mean(r['metrics'][k] for r in results) for k in common}
    if all(r['before'] for r in results):
        summary.update({k:mean(r['metrics'][k] for r in results) for k in ['before_precision','before_recall','before_characters']})
    timed=[r['seconds'] for r in results if r['seconds'] is not None]
    summary['mean_stage_seconds']=mean(timed) if timed else None
    report=dict(experiment=CONFIG['experiment_id'],run_id=folder.name,
        question_sha256=sha(DATASET/'questions.json'),scorer_sha256=sha(EVALUATION/'scorer.py'),
        gold_sha256=sha(DATASET/'expected-evidence.json'),upstream_sha256=sha(BUNDLE/'upstream.json'),summary=summary,results=results)
    save(folder/'results.json',report)
    lines=['# Experiment result','',f"Experiment: `{report['experiment']}`. Run: `{folder.name}`. {len(results)} known development samples.",'',
           '| Source | Before precision | After precision | Before recall | After recall | Characters before → after |',
           '|---|---:|---:|---:|---:|---:|']
    for row in results:
        m=row['metrics'];b=row['before']
        lines.append(f"| {row['source_index']} | {b['precision']:.1%} | {m['precision']:.1%} | {b['recall']:.1%} | {m['recall']:.1%} | {b['returned_characters']} → {m['returned_characters']} |" if b else
                     f"| {row['source_index']} | — | {m['precision']:.1%} | — | {m['recall']:.1%} | — → {m['returned_characters']} |")
    lines+=['',f"Mean precision: {summary['precision']:.1%}; recall: {summary['recall']:.1%}; returned characters: {summary['returned_characters']:.0f}.",
        '',f"Recorded mean stage time: {summary['mean_stage_seconds']:.2f}s." if timed else 'Replay only: no fresh model latency measured.',
        '', 'Sentence selection measures additional selection time only; it does not rerun or include the earlier search. A fresh agentic run has different timing scope. Do not compare these as interchangeable end-to-end latencies.',
        '', 'Gold was read only after all outputs were saved. Conditions/exceptions are requested in the prompt but legal completeness still needs human review. No score-based fallback or tuning was applied.',
        '', '[Frozen config](config.json) · [Saved inputs](inputs.json) · [Full results](results.json)']
    for row in results:
        if row['trace_url']:lines.append(f"\n[Langfuse source {row['source_index']}]({row['trace_url']})")
    (folder/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report

def finish(folder,status='complete',error=None):
    manifest=read(folder/'manifest.json');manifest.update(status=status,finished_at=now())
    if error:manifest['error']=error
    save(folder/'manifest.json',manifest)
    save(folder/'run-lock.json',{'files':{str(p.relative_to(folder)).replace('\\','/'):sha(p)
        for p in folder.rglob('*') if p.is_file() and p.name!='run-lock.json'}})
def main(folder,mode,no_langfuse=False):
    inputs=read(folder/'inputs.json')
    if not 1<=len(inputs)<=CONFIG['sample_cap']:raise ValueError('Invalid sample count')
    save(folder/'config.json',dict(experiment=CONFIG['experiment_id'],mode=mode,settings=CONFIG))
    save(folder/'manifest.json',dict(status='running',mode=mode,created_at=now()))
    client=None
    try:
        validate_sources(inputs)
        if mode=='check':
            execution_proof(folder)
            finish(folder,'validated')
            print('Validated archived imports/config/source seals; no model inference executed.',flush=True)
            return
        if mode=='replay':
            save(folder/'model.json',read(folder/'expected-model.json'))
        elif CONFIG['kind']=='agentic':
            if no_langfuse:raise ValueError('Agentic v2 requires configured Langfuse (existing traced pipeline)')
            with connect() as conn:
                config=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(INGESTION,)).fetchone()[0]
                validate_database(conn,config,inputs,folder)
            with urllib.request.urlopen(API+'/api/tags',timeout=10) as response:models=json.load(response)['models']
            digest=next(m['digest'] for m in models if m['name']==MODEL)
            check_model(folder,dict(name=MODEL,digest=digest,embedding=config))
            linked=experiment_pipeline.run(len(inputs))
            save(folder/'linked-run.json',{'path':str(linked)})
            for e in inputs:
                sample=e['sample'];saved=read(linked/f"sample-{sample['source_index']}.json")
                save(folder/f"output-{sample['source_index']}.json",dict(sample=sample,output=saved['retrieval']['stages']['iterative'],seconds=saved['retrieval']['seconds'],timing_scope='retrieval-only',trace_id=saved['trace_id'],trace_url=saved['trace_url']))
        else:
            client=langfuse_client(not no_langfuse)
            if CONFIG['kind']=='selection':retrieve_selection(folder,inputs,client)
            else:retrieve_baseline(CONFIG['experiment_id'],folder,inputs,client)
        report=score_run(folder,inputs,client)
        validate_sources(inputs)
        execution_proof(folder)
        finish(folder)
        print(json.dumps(report['summary'],indent=2),flush=True)
        print('Report: '+str(folder/'results.md'),flush=True)
    except Exception as error:
        finish(folder,'failed',str(error));raise
    finally:
        if client:client.flush();client.shutdown()
