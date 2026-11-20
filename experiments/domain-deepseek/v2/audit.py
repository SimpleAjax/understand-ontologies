"""Audit fixed nodes, additive edges, source evidence, costs and cloud traces."""
import argparse
import json
import os
from pathlib import Path
import sys
from rdflib import Graph
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_langfuse_pilot import pages,decode
read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def audit(folder):
    import hashlib
    load_dotenv(ROOT/'.env');cfg=read(folder/'code/experiment/config.json')
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for name,digest in read(folder/'run-lock.json')['files'].items():assert sha(folder/name)==digest
    for name,digest in read(folder/'bundle-lock.json')['files'].items():assert sha(folder/'code'/name)==digest
    cfolder=folder/'variants/expanded';counts=[]
    for entry in read(folder/'inputs.json'):
        doc=entry['document'];source=ROOT/'data/corpus'/doc['local_file_path'];assert sha(source)==doc['sha256']
        text=source.read_text(encoding='utf-8');b=read(folder/'graphs'/f"{doc['id']}.json");c=read(cfolder/'graphs'/f"{doc['id']}.json")
        assert b['provisions']==c['provisions'] and b['passages']==c['passages']
        bg=Graph().parse(folder/'graphs'/f"{doc['id']}.ttl");cg=Graph().parse(cfolder/'graphs'/f"{doc['id']}.ttl");assert set(bg)<=set(cg)
        for p in b['passages']:assert text[slice(*p['span'])]==p['text']
        counts.append(dict(document_id=doc['id'],provisions=len(b['provisions']),extra_links=sum(l['traversable'] for l in c['expanded_links'])))
    traces={};costs=[]
    for path in folder.glob('api-calls-*.json'):costs.extend(read(path))
    build_obs=[]
    remote=[]
    all_obs=list(build_obs)
    for variant,sub in [('existing',folder),('expanded',cfolder)]:
        rows=read(sub/'results.json')['results'];saved=[read(sub/f"output-{r['source_index']}.json") for r in rows]
        obs=pages('observations','list',['--session-id',cfg['experiment_id']+'-'+folder.name+'-'+variant,'--limit','1000','--fields','core,basic,io,model,usage'])
        scores=pages('scores','list',['--trace-id',','.join(s['trace_id'] for s in saved),'--limit','100','--fields','details,subject'])
        for row,s in zip(rows,saved):
            found=[o for o in obs if o['traceId']==s['trace_id']];byid={o['id']:o for o in found}
            assert sum(o['type']=='GENERATION' for o in found)==len(s['calls'])+len(s['answer']['calls'])
            assert sum(o['type']=='TOOL' for o in found)==len(s['tool_steps'])
            for o in found:
                assert not o.get('parentObservationId') or o['parentObservationId'] in byid
                if o['type']=='GENERATION':assert len(decode(o['input']))==2 and o.get('model')==cfg['remote_model']
            roots=[o for o in found if o['type']=='CHAIN' and not o.get('parentObservationId')];assert len(roots)==1
            assert decode(roots[0]['input'])['question']==row['question']
            text=(ROOT/'data/corpus'/row['file_path']).read_text(encoding='utf-8')
            assert sum(len(p['text']) for p in s['output'])<=6000
            for p in s['output']:assert text[slice(*p['span'])]==p['text']
            assert set(s['answer']['citations'])<={p['id'] for p in s['output']}
            found_scores={x['name']:x['value'] for x in scores if x.get('subject',{}).get('id')==s['trace_id']}
            for name,value in row['metrics'].items():assert name in found_scores and abs(found_scores[name]-value)<1e-9
            guard=read(sub/'audits'/f"query-{row['source_index']}.json");assert not guard['raw_source_access'] and not guard['gold_access']
        traces[variant]=dict(traces=len(saved),observations=len(obs),scores=len(scores))
        remote.extend(o for o in obs if o['type']=='GENERATION')
        all_obs.extend(obs)
    costs=[]
    for sub in [folder,cfolder]:
        for path in sub.glob('api-calls-*.json'):costs.extend(read(path))
    assert len(remote)==len(costs)
    assert abs(sum(o.get('totalCost',0) for o in remote)-sum(c['cost_usd'] for c in costs))<1e-8
    for call in costs:assert call['provider']=='Wafer' and not call['cache_hit']
    secret_found=False
    for key in ['OPENROUTER_API_KEY','LANGFUSE_SECRET_KEY']:
        secret=os.getenv(key)
        if secret:
            assert secret not in json.dumps(all_obs)
            for path in folder.rglob('*'):
                if path.is_file():assert secret not in path.read_text(encoding='utf-8',errors='ignore'),path
    result=dict(passed=True,agreements=10,base_facts_preserved=True,graphs=counts,cloud=traces,api_generations=len(remote),api_cost_usd=sum(c['cost_usd'] for c in costs),secret_detected=secret_found,limitation='Structural, source, additivity and trace checks; not a legal/semantic correctness review.')
    target=ROOT/'artifacts/experiment-comparisons'/('deepseek-inference-audit-'+folder.name+'.json');target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_folder',type=Path);args=p.parse_args();audit(args.run_folder.resolve())
