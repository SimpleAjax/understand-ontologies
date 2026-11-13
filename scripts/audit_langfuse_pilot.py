"""Read back live observations/scores through Langfuse CLI and check the integration."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from pipeline import ROOT


def decode(value):
    if isinstance(value,str):
        try:return json.loads(value)
        except json.JSONDecodeError:return value
    return value


def cli(resource,action,arguments):
    process=subprocess.run(['npx.cmd' if os.name=='nt' else 'npx','--yes','langfuse-cli','api',
        resource,action,*arguments,'--json'],capture_output=True,text=True,encoding='utf-8',env=os.environ)
    if process.returncode:raise RuntimeError(f'Langfuse CLI {resource}/{action} failed; exit {process.returncode}')
    response=json.loads(process.stdout)
    if response.get('status',200)>=400:raise RuntimeError(f'Langfuse HTTP {response["status"]}')
    return response.get('body',response)


def pages(resource,action,arguments):
    items=[];cursor=None
    while True:
        body=cli(resource,action,arguments+(['--cursor',cursor] if cursor else []))
        items.extend(body['data']);cursor=body.get('meta',{}).get('cursor')
        if not cursor:return items
        if len(items)>=1000:raise RuntimeError('Audit exceeded its bounded 1000-item limit')


def audit(folder):
    load_dotenv(ROOT/'.env')
    report=json.loads((folder/'results.json').read_text(encoding='utf-8'))
    observations=pages('observations','list',['--session-id',report['run'],'--limit','1000',
        '--fields','core,basic,io,metadata,model,usage,metrics,trace_context'])
    trace_ids=[row['trace_id'] for row in report['results']]
    scores=pages('scores','list',['--trace-id',','.join(trace_ids),'--limit','100','--fields','details,subject'])
    (folder/'langfuse-observations-readback.json').write_text(json.dumps(observations,indent=2),encoding='utf-8')
    (folder/'langfuse-scores-readback.json').write_text(json.dumps(scores,indent=2),encoding='utf-8')
    checks=[]
    for row in report['results']:
        saved=json.loads((folder/f"sample-{row['source_index']}.json").read_text(encoding='utf-8'))
        obs=[o for o in observations if o['traceId']==row['trace_id']]
        roots=[o for o in obs if o['type']=='CHAIN' and not o.get('parentObservationId')]
        generations=[o for o in obs if o['type']=='GENERATION']
        errors=[]
        if len(roots)!=1:errors.append('Expected one question root')
        if len(generations)!=len(saved['retrieval']['llm_calls']):errors.append('Missing Qwen generations')
        byid={o['id']:o for o in obs}
        for o in obs:
            if o.get('parentObservationId') and o['parentObservationId'] not in byid:errors.append('Broken span hierarchy')
        if roots:
            inp=decode(roots[0].get('input'));out=decode(roots[0].get('output'))
            if not isinstance(inp,dict) or inp.get('question')!=saved['sample']['question']:errors.append('Root question missing')
            signature=lambda passages:[(p['file_path'],p['span'],p['text']) for p in passages]
            if not isinstance(out,dict) or signature(out.get('passages',[]))!=signature(saved['retrieval']['stages']['iterative']):errors.append('Final evidence missing')
        for generation in generations:
            inp=decode(generation.get('input'));out=decode(generation.get('output'))
            if not isinstance(inp,dict) or len(inp.get('messages',[]))!=2:errors.append('Exact Qwen messages missing')
            if not isinstance(out,dict) or 'parsed' not in out:errors.append('Qwen response missing')
            if generation.get('model')!='qwen3:4b-instruct-2507-q4_K_M':errors.append('Wrong model label')
            if generation.get('totalCost')!=0:errors.append('Local API cost must be explicitly zero')
            if not generation.get('usageDetails'):errors.append('Token usage missing')
        found={s['name']:s for s in scores if s.get('subject',{}).get('id')==row['trace_id']}
        for name,value in row['metrics'].items():
            if name not in found:errors.append('Missing score: '+name)
            elif abs(float(found[name]['value'])-value)>1e-9:errors.append('Wrong score: '+name)
        for name in ['meaning-search','keyword-search','combine-rankings-and-category-preference',
                     'select-source-passages','resolve-section-links-and-apply-budget']:
            if name not in {o['name'] for o in obs}:errors.append('Missing step: '+name)
        checks.append({'source_index':row['source_index'],'trace_url':row['trace_url'],
                       'observations':len(obs),'qwen_calls':len(generations),'scores':len(found),'errors':errors})
    serialized=json.dumps(observations)
    secret_found=bool(os.getenv('LANGFUSE_SECRET_KEY') and os.environ['LANGFUSE_SECRET_KEY'] in serialized)
    # Langfuse's SDK adds its public project key as scope.attributes.public_key.
    # That non-secret client identifier is expected; it must not appear in app IO.
    io_serialized=json.dumps([{'input':o.get('input'),'output':o.get('output')} for o in observations])
    public_in_io=bool(os.getenv('LANGFUSE_PUBLIC_KEY') and os.environ['LANGFUSE_PUBLIC_KEY'] in io_serialized)
    passed=not secret_found and not public_in_io and all(not c['errors'] for c in checks)
    audit_report={'passed':passed,'trace_count':len(checks),'observations':len(observations),'scores':len(scores),
        'secret_values_detected':secret_found,'public_key_in_application_io':public_in_io,
        'sdk_scope_public_key':'Expected non-secret SDK scope identifier; not application input/output.', 'checks':checks,
        'basis':'Live Langfuse observations and scores read back through CLI; no browser automation.'}
    (folder/'langfuse-audit.json').write_text(json.dumps(audit_report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit_report,indent=2))
    if not passed:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    args=parser.parse_args();audit(args.run.resolve())
