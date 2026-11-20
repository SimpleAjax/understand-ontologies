"""Read back this experiment's Langfuse query traces and scores through CLI."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from audit_langfuse_pilot import pages,decode
from dotenv import load_dotenv


def audit(folder):
    load_dotenv(ROOT/'.env')
    report=json.loads((folder/'results.json').read_text(encoding='utf-8'))
    saved=[json.loads((folder/f"output-{row['source_index']}.json").read_text(encoding='utf-8')) for row in report['results']]
    session='domain-ontology-v1-'+folder.name
    obs=pages('observations','list',['--session-id',session,'--limit','1000','--fields','core,basic,io,model,usage'])
    scores=pages('scores','list',['--trace-id',','.join(s['trace_id'] for s in saved),'--limit','100','--fields','details,subject'])
    checks=[]
    for row,s in zip(report['results'],saved):
        trace=[o for o in obs if o['traceId']==s['trace_id']]
        roots=[o for o in trace if o['type']=='CHAIN' and not o.get('parentObservationId')]
        gens=[o for o in trace if o['type']=='GENERATION'];tools=[o for o in trace if o['type']=='TOOL'];errors=[]
        if len(roots)!=1:errors.append('Expected exactly one query root')
        if len(gens)!=len(s['calls'])+len(s['answer']['calls']):errors.append('Generation count mismatch')
        if len(tools)!=len(s['tool_steps']):errors.append('Graph-tool count mismatch')
        byid={o['id']:o for o in trace}
        for o in trace:
            if o.get('parentObservationId') and o['parentObservationId'] not in byid:errors.append('Broken span hierarchy')
        if roots:
            if decode(roots[0].get('input',{})).get('question')!=row['question']:errors.append('Root question missing')
            if decode(roots[0].get('output',{})).get('answer')!=s['answer']['answer']:errors.append('Root answer missing')
        for generation in gens:
            messages=decode(generation.get('input'))
            if not isinstance(messages,list) or len(messages)!=2:errors.append('Exact messages missing')
            if generation.get('totalCost')!=0:errors.append('Local API cost not zero')
            if not generation.get('usageDetails'):errors.append('Token usage missing')
            if generation.get('model')!='qwen3:4b-instruct-2507-q4_K_M':errors.append('Wrong model label')
        found={score['name']:score['value'] for score in scores if score.get('subject',{}).get('id')==s['trace_id']}
        for name,value in row['metrics'].items():
            if name not in found or abs(found[name]-value)>1e-9:errors.append('Missing/incorrect score '+name)
        checks.append(dict(source_index=row['source_index'],generations=len(gens),tools=len(tools),scores=len(found),errors=errors))
    secret=os.getenv('LANGFUSE_SECRET_KEY');secret_found=bool(secret and secret in json.dumps(obs))
    public=os.getenv('LANGFUSE_PUBLIC_KEY');io_data=json.dumps([{'input':o.get('input'),'output':o.get('output')} for o in obs])
    public_in_io=bool(public and public in io_data)
    result=dict(passed=not secret_found and not public_in_io and all(not c['errors'] for c in checks),session=session,traces=len(saved),observations=len(obs),scores=len(scores),secret_detected=secret_found,public_key_in_application_io=public_in_io,checks=checks)
    path=ROOT/'artifacts/experiment-comparisons'/('domain-cloud-audit-'+folder.name+'.json')
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_folder',type=Path);args=p.parse_args();audit(args.run_folder.resolve())
