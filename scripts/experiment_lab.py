"""Small experiment registry: append-only runs, saved-output replay and matched comparisons."""
import argparse
import copy
import hashlib
import json
import os
import shutil
import time
import urllib.request
import uuid
from contextlib import nullcontext
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean

from pipeline import ROOT,connect,load_model,QUERY_PREFIX
from compare_llm100 import RUN,CT,KINDS,INGESTION,catalogue,rank_passages,graph_candidates,verify_graphs,read,save,sha
from compare_retrieval import apply_budget,score
from evaluate import upstream
from sentence_selection import select,SETTINGS,PROMPT
from retrieval_v2 import API,MODEL

REGISTRY=ROOT/'experiments/registry.json'
RUNS=ROOT/'artifacts/experiment-runs'
CODE=['scripts/experiment_lab.py','scripts/sentence_selection.py','scripts/compare_llm100.py',
      'scripts/compare_retrieval.py','scripts/evaluate.py','scripts/pipeline.py',
      'scripts/retrieval_v2.py','scripts/langfuse_retrieval.py','scripts/run_langfuse_pilot.py']


def now():return datetime.now(timezone.utc).isoformat()


def new_run(experiment,config,inputs):
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:6]
    folder=RUNS/experiment/name;folder.mkdir(parents=True)
    (folder/'code').mkdir()
    for path in CODE:shutil.copyfile(ROOT/path,folder/'code'/Path(path).name)
    save(folder/'config.json',dict(experiment=experiment,created_at=now(),run_id=name,
        code_sha256={path:sha(ROOT/path) for path in CODE},registry_sha256=sha(REGISTRY),
        source_graph_lock_sha256=sha(RUN/'graph-lock.json'),**config))
    save(folder/'inputs.json',inputs)
    import platform,importlib.metadata
    versions={}
    for package in ['torch','transformers','sentence-transformers','numpy','psycopg','pgvector','langfuse','pydantic','rdflib']:
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]=None
    save(folder/'environment.json',{'python':platform.python_version(),'platform':platform.platform(),
                                   'packages':versions,'note':'Version record, not an automatic environment restorer.'})
    (folder/'prompt.txt').write_text(PROMPT if experiment=='sentence-selection-v1' else 'See code snapshots for the original experiment prompt.',encoding='utf-8')
    save(folder/'manifest.json',dict(status='running',experiment=experiment,created_at=now(),
        config_sha256=sha(folder/'config.json'),inputs_sha256=sha(folder/'inputs.json')))
    return folder


def default_inputs(limit,source=None,selection=False):
    registry=read(REGISTRY);samples=read(ROOT/registry['default_sample_set'])[:limit]
    docs={d['id']:d for d in read(RUN/'manifest.json')['documents']}
    receipt=read(source/'retrieval-complete.json') if selection else None
    result=[]
    for sample in samples:
        doc=docs[sample['document_id']]
        if sha(ROOT/'data/corpus'/doc['local_file_path'])!=doc['sha256']:raise ValueError('Source document changed')
        entry=dict(sample=sample,document=doc)
        if selection:
            file=source/f"sample-{sample['source_index']}-retrieval.json"
            if sha(file)!=receipt['files'][file.name]:raise ValueError('Fixed source retrieval changed')
            data=read(file)
            if data['sample']['question']!=sample['question']:raise ValueError('Source question differs')
            entry.update(before=copy.deepcopy(data['retrieval']['stages']['iterative']),source_trace_file=str(file.relative_to(ROOT)),
                source_trace_sha256=sha(file))
        result.append(entry)
    return result


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
    save(folder/'model.json',{'name':MODEL,'digest':digest,'settings':SETTINGS})
    for index,entry in enumerate(inputs,1):
        sample=entry['sample'];doc=entry['document']
        text=(ROOT/'data/corpus'/doc['local_file_path']).read_text(encoding='utf-8')
        print(f"{index}/{len(inputs)} select sentences: source {sample['source_index']}",flush=True)
        with propagation(client,folder),root_trace(client,'focused-evidence-selection',sample,folder) as root:
            # Fixed saved evidence and original text only; no benchmark gold enters this function.
            selected=select(sample['question'],entry['before'],text,digest,folder/'responses',client)
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
        model,revision=load_model(config['revision'],local_files_only=True)
        save(folder/'model.json',{'name':config['model'],'revision':revision,'ingestion':INGESTION})
        for entry in inputs:
            sample=entry['sample'];doc=entry['document']
            text=(ROOT/'data/corpus'/doc['local_file_path']).read_text(encoding='utf-8');texts={sample['file_path']:text}
            g=Graph().parse(ROOT/doc['turtle_path']);cat=catalogue(g);vectors={}
            if experiment!='vector-v1' and cat:
                encoded=model.encode([p['text'] for p in cat],normalize_embeddings=True,batch_size=32,show_progress_bar=False)
                vectors={p['evidence_id']:v for p,v in zip(cat,encoded)}
            with propagation(client,folder),root_trace(client,experiment,sample,folder) as root:
                started=time.perf_counter();query=QUERY_PREFIX+sample['question'];vector=model.encode(query,normalize_embeddings=True)
                if experiment=='vector-v1':
                    rows=conn.execute('''SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance
                        FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY distance,id LIMIT 5''',
                        (vector,INGESTION,sample['file_path'])).fetchall()
                    candidates=[dict(file_path=p,span=[a,b],text=t,distance=d) for p,a,b,t,d in rows]
                elif experiment=='catalogue-v1':candidates=rank_passages(cat,vectors,vector,k=5)
                else:candidates,_,_=graph_candidates(g,sample['document_id'],sample['topic'],cat,vectors,vector,k=5)
                output=apply_budget(candidates,texts,6000);seconds=time.perf_counter()-started
                if root:root.update(output={'passages':output,'retrieval_seconds':seconds})
            save(folder/f"output-{sample['source_index']}.json",dict(sample=sample,output=output,seconds=seconds,
                timing_scope='retrieval-only',trace_id=root.trace_id if root else None,
                trace_url=client.get_trace_url(trace_id=root.trace_id) if root else None))
        conn.rollback()


def score_run(folder,inputs,client=None):
    # Called after every output is persisted. This is the only gold read in this runner.
    types=upstream();bank={q['source_index']:q for q in read(ROOT/'experiments/cuad-100/questions.json')['tests']};results=[]
    for entry in inputs:
        sample=entry['sample'];saved=read(folder/f"output-{sample['source_index']}.json");q=bank[sample['source_index']]
        if q['query']!=sample['question']:raise ValueError('Question version changed')
        doc=entry['document'];source=ROOT/'data/corpus'/doc['local_file_path']
        if sha(source)!=doc['sha256']:raise ValueError('Source changed before scoring')
        text=source.read_text(encoding='utf-8');texts={sample['file_path']:text}
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
    report=dict(experiment=read(folder/'config.json')['experiment'],run_id=folder.name,
        question_sha256=sha(ROOT/'experiments/cuad-100/questions.json'),summary=summary,results=results)
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


def run(experiment,limit,no_langfuse=False):
    registry=read(REGISTRY)
    if experiment not in registry['experiments']:raise ValueError('Unknown experiment; use list')
    if not 1<=limit<=registry['sample_cap']:raise ValueError('Current registered sample cap is five')
    verify_graphs();spec=registry['experiments'][experiment]
    source=ROOT/spec['default_source'] if spec['kind']=='selection' else None
    inputs=default_inputs(limit,source,selection=spec['kind']=='selection')
    folder=new_run(experiment,{'mode':'fresh','settings':SETTINGS if source else {},
        'source_run':str(source.relative_to(ROOT)) if source else None,'sample_count':limit},inputs)
    print('Run folder: '+str(folder),flush=True);client=None
    try:
        if spec['kind']=='agentic':
            if no_langfuse:raise ValueError('The existing agentic tracing runner requires Langfuse; use a baseline or sentence experiment for offline runs')
            from run_langfuse_pilot import run as agentic
            linked=agentic(limit);save(folder/'linked-run.json',{'path':str(linked.relative_to(ROOT))})
            for entry in inputs:
                sample=entry['sample'];saved=read(linked/f"sample-{sample['source_index']}.json")
                save(folder/f"output-{sample['source_index']}.json",dict(sample=sample,
                    output=saved['retrieval']['stages']['iterative'],seconds=saved['retrieval']['seconds'],
                    timing_scope='retrieval-only',trace_id=saved['trace_id'],trace_url=saved['trace_url']))
        else:
            client=langfuse_client(not no_langfuse)
            if spec['kind']=='selection':retrieve_selection(folder,inputs,client)
            else:retrieve_baseline(experiment,folder,inputs,client)
        report=score_run(folder,inputs,client);verify_graphs();finish(folder)
        print(json.dumps(report['summary'],indent=2),flush=True)
        print('Report: '+str(folder/'results.md'),flush=True)
        return folder
    except Exception as error:
        finish(folder,'failed',str(error));raise
    finally:
        if client:client.flush();client.shutdown()


def replay(source):
    if read(source/'manifest.json')['status']!='complete':raise ValueError('Only complete saved runs can be replayed')
    if read(source/'results.json')['question_sha256']!=sha(ROOT/'experiments/cuad-100/questions.json'):
        raise ValueError('Benchmark version changed; this would not reproduce the saved scoring')
    lock=read(source/'run-lock.json')
    for name,digest in lock['files'].items():
        if sha(source/name)!=digest:raise ValueError('Saved run changed: '+name)
    inputs=read(source/'inputs.json');cfg=read(source/'config.json')
    folder=new_run(cfg['experiment'],{'mode':'saved-output-replay','replay_of':str(source),
        'source_config_sha256':sha(source/'config.json')},inputs)
    shutil.copyfile(source/'config.json',folder/'replayed-source-config.json')
    shutil.copyfile(source/'prompt.txt',folder/'replayed-source-prompt.txt')
    (folder/'prompt.txt').write_text('No prompt was executed in this saved-output replay. See replayed-source-prompt.txt for provenance.',encoding='utf-8')
    for entry in inputs:
        id=entry['sample']['source_index'];saved=read(source/f'output-{id}.json')
        saved.update(seconds=None,timing_scope='replay-no-model-calls',trace_id=None,trace_url=None)
        save(folder/f'output-{id}.json',saved)
    result=score_run(folder,inputs);finish(folder)
    print('Replay report: '+str(folder/'results.md'));return result


def compare(left,right):
    a=read(left/'results.json');b=read(right/'results.json')
    if a['question_sha256']!=b['question_sha256']:raise ValueError('Different question bank versions')
    aa={x['source_index']:x for x in a['results']};bb={x['source_index']:x for x in b['results']}
    if set(aa)!=set(bb):raise ValueError('Run comparisons require the same sample IDs')
    left_sources={x['sample']['source_index']:x['document']['sha256'] for x in read(left/'inputs.json')}
    right_sources={x['sample']['source_index']:x['document']['sha256'] for x in read(right/'inputs.json')}
    if left_sources!=right_sources:raise ValueError('Source document versions differ')
    lines=['# Matched experiment comparison','',f"Left: `{left}`\n\nRight: `{right}`",'',
        '| Source | Precision left → right | Recall left → right | Characters left → right |','|---|---:|---:|---:|']
    for id in sorted(aa):
        x,y=aa[id],bb[id]
        if (x['question'],x['document_id'])!=(y['question'],y['document_id']):raise ValueError('Question/document mismatch')
        m,n=x['metrics'],y['metrics'];lines.append(f"| {id} | {m['precision']:.1%} → {n['precision']:.1%} | {m['recall']:.1%} → {n['recall']:.1%} | {m['returned_characters']} → {n['returned_characters']} |")
    lines+=['','Same sample IDs and question-bank hash. Check each run’s config, source hashes, model digest and timing scope before attributing changes. Replays have no new inference timing; five known examples do not demonstrate generalization.']
    target=ROOT/'artifacts/experiment-comparisons'/('compare-'+uuid.uuid4().hex[:8]+'.md');target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n'.join(lines)+'\n',encoding='utf-8');print('Comparison: '+str(target));return target


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    r=sub.add_parser('run');r.add_argument('experiment');r.add_argument('--limit',type=int,default=5);r.add_argument('--no-langfuse',action='store_true')
    p=sub.add_parser('replay');p.add_argument('run_folder',type=Path)
    c=sub.add_parser('compare');c.add_argument('left',type=Path);c.add_argument('right',type=Path)
    args=parser.parse_args()
    if args.command=='list':
        for name,spec in read(REGISTRY)['experiments'].items():print(name+' — '+spec['description'])
    elif args.command=='run':run(args.experiment,args.limit,args.no_langfuse)
    elif args.command=='replay':replay(args.run_folder.resolve())
    else:compare(args.left.resolve(),args.right.resolve())
