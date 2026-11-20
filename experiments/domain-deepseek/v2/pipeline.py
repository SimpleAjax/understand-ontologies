"""Controlled A/B/C pilot: API extraction, fixed local agent, additive relationships."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
import urllib.error
import urllib.request

import engine as e
from rdflib import Graph, RDF, RDFS, Literal, URIRef

HERE=Path(__file__).resolve().parent
EXTRA=['requires_condition','exception_to','prevents','notice_for','amends','survives','incorporates','qualifies']


class Budget:
    def __init__(self,limit):self.lock=threading.Lock();self.total=0.;self.reserved=0.;self.limit=limit;self.calls=[]
    def reserve(self,value):
        with self.lock:
            if self.total+self.reserved+value>self.limit:raise RuntimeError('Configured API spend ceiling reached')
            self.reserved+=value
    def settle(self,estimate,call):
        with self.lock:
            self.reserved-=estimate;self.total+=call['cost_usd'];self.calls.append(call)


class Hybrid(e.Model):
    def __init__(self,folder,cfg,client=None,budget=None,document='main'):
        super().__init__(folder,cfg,client);self.budget=budget or Budget(cfg['spend_limit_usd']);self.document=document
    def identity(self):
        return dict(query_model=self.cfg['remote_model'],extraction_model=self.cfg['remote_model'],provider=self.cfg['provider'],reasoning_enabled=False)
    def unload(self):pass
    def call(self,name,prompt,data,schema,stage,options=None):
        messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(data,ensure_ascii=False))]
        cap=(options or {}).get('remote_max_tokens',self.cfg['remote_max_tokens'] if stage.startswith('extraction') else 2048)
        payload=dict(model=self.cfg['remote_model'],messages=messages,temperature=0,seed=42,max_tokens=cap,
                     reasoning={'enabled':False},provider=dict(order=[self.cfg['provider']],allow_fallbacks=False,require_parameters=True),
                     response_format=dict(type='json_schema',json_schema=dict(name='contract_graph',strict=True,schema=schema)))
        key=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        path=self.folder/'responses'/stage/f'{key}.json';cached=path.exists();started=time.perf_counter()
        # Conservative reservation at pinned endpoint prices; no credential is serialized.
        estimate=len(json.dumps(payload))*.000000038+cap*.0000005
        if not cached:self.budget.reserve(estimate)
        ctx=self.client.start_as_current_observation(name=name,as_type='generation',input=messages,model=self.cfg['remote_model'],model_parameters=dict(temperature=0,max_tokens=cap,reasoning_enabled=False),metadata=dict(provider=self.cfg['provider'],request_fingerprint=key,cache_hit=cached,document_id=self.document,stage=stage)) if self.client else nullcontext(None)
        with ctx as obs:
            if cached:
                if e.read(path.with_name(key+'-request.json'))!=payload:raise ValueError('API cache payload differs')
                raw=e.read(path)
            else:
                e.save(path.with_name(key+'-request.json'),payload)
                req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['OPENROUTER_API_KEY'],'Content-Type':'application/json'})
                for attempt in range(3):
                    try:
                        with urllib.request.urlopen(req,timeout=240) as response:raw=json.load(response)
                        break
                    except urllib.error.HTTPError as error:
                        if error.code in (429,502,503) and attempt<2:time.sleep(2**attempt);continue
                        body=error.read().decode('utf-8','replace').replace(os.environ['OPENROUTER_API_KEY'],'[REDACTED]')
                        e.save(path.with_name(key+'-error.json'),dict(status=error.code,body=body))
                        raise RuntimeError('OpenRouter HTTP '+str(error.code)+'; see redacted-key-free error artifact') from None
                e.save(path,raw)
            if 'error' in raw:raise ValueError('OpenRouter returned an error object')
            usage=raw.get('usage',{});cost=float(usage.get('cost',0))
            if 'cost' not in usage:raise ValueError('Provider cost missing; refusing to report zero')
            call=dict(stage=stage,name=name,key=key,document_id=self.document,cache_hit=cached,seconds=time.perf_counter()-started,input=usage.get('prompt_tokens',0),output=usage.get('completion_tokens',0),cost_usd=0 if cached else cost,reported_original_cost_usd=cost,provider=raw.get('provider'),generation_id=raw.get('id'))
            if not cached:self.budget.settle(estimate,call)
            self.calls.append(call);e.save(self.folder/f'api-calls-{self.document}.json',self.calls)
            choice=raw['choices'][0]
            if obs:obs.update(output=choice['message'],usage_details=dict(input=0 if cached else call['input'],output=0 if cached else call['output']),cost_details={'total':call['cost_usd']},metadata=dict(provider=raw.get('provider'),generation_id=raw.get('id'),request_fingerprint=key,cache_hit=cached,stage=stage,document_id=self.document))
        if choice['finish_reason']!='stop':
            if cap>=self.cfg['remote_output_retry']:raise ValueError('API output still truncated after one retry')
            return self.call(name,prompt,data,schema,stage,dict(remote_max_tokens=self.cfg['remote_output_retry']))
        parsed=json.loads(choice['message']['content']);e.validate_shape(parsed,schema);return parsed


def expand(record,base_graph,model):
    ids=[r['id'] for r in record['provisions']]
    for r in record['provisions']:ids.extend(r['id']+'C'+str(i) for i,_ in enumerate(r['conditions']))
    schema=e.obj(links=e.array(e.obj(source=e.enum(ids),relation=e.enum(EXTRA),target=e.enum(ids),sources=e.array(e.enum([p['id'] for p in record['passages']]),6),quote=e.string(1200),explanation=e.string(400)),40),uncertainties=e.array(e.string(300),15))
    result=model.call('expand-domain-relationships',(HERE/'expanded-prompt.txt').read_text(),dict(provisions=record['provisions'],passages=record['passages']),schema,'extraction-expanded')
    graph=Graph()
    for t in base_graph:graph.add(t)
    for prefix,ns in base_graph.namespaces():graph.bind(prefix,ns)
    ns='https://cimulink.local/agreements/domain10/'+record['document']['id']+'#'
    passages={p['id']:p for p in record['passages']}
    norm=lambda text:' '.join(text.split())
    accepted=[]
    for i,link in enumerate(result['links']):
        valid=bool(link['sources'] and link['quote'].strip() and link['source']!=link['target'] and any(norm(link['quote']) in norm(passages[p]['text']) for p in link['sources']))
        link['traversable']=valid;link['review_status']='QUOTE_CHECKED_UNREVIEWED' if valid else 'REVIEW_ONLY_INVALID_QUOTE_OR_SELF_LINK'
        if valid:
            graph.add((URIRef(ns+link['source']),e.D[link['relation']],URIRef(ns+link['target'])));accepted.append(link)
        n=URIRef(ns+'ExpandedLink'+str(i));graph.add((n,RDF.type,e.D.ProposedRelationship));graph.add((n,e.D.description,Literal(json.dumps(link))))
        for p in link['sources']:graph.add((n,e.D.supportedBy,URIRef(ns+p)))
    # No old facts are changed, and no new business nodes are created.
    assert set(base_graph)<=set(graph)
    return graph,dict(**record,expanded_links=result['links'],expanded_uncertainties=result['uncertainties'])


def expanded_inspect(self,ids):
    packet=ORIGINAL_INSPECT(self,ids)
    # Conditions reached through new links also carry directly retrievable quotations.
    for id in ids:
        n=self.rules[id]
        for c in self.g.objects(n,e.D.requires_condition):
            if self.id(c) in self.rules:continue
            sources=[]
            for p in self.g.objects(c,e.D.supportedBy):
                value=self.passages[self.id(p)];self.revealed[value['id']]=value;sources.append(value)
            packet['provisions'].append(dict(id=self.id(c),meaning=str(self.g.value(c,RDFS.label)),conditions=[],passages=sources))
    return packet


ORIGINAL_INSPECT=e.GraphTools.inspect


def main(folder,mode,no_langfuse=False):
    from dotenv import load_dotenv
    from langfuse import Langfuse,propagate_attributes
    from langfuse_retrieval import safe_mask
    root=Path(os.environ['LAB_PROJECT_ROOT']);load_dotenv(root/'.env');cfg=e.read(HERE/'config.json');inputs=e.read(folder/'inputs.json')
    e.save(folder/'manifest.json',dict(status='running',mode=mode));e.save(folder/'config.json',dict(experiment=cfg['experiment_id'],settings=cfg,mode=mode))
    if mode=='check':e.finish(folder,'validated');return
    client=None;budget=Budget(cfg['spend_limit_usd']);local=Hybrid(folder,cfg,None,budget)
    cfolder=folder/'variants/expanded';session=cfg['experiment_id']+'-'+folder.name
    try:
        if not no_langfuse:
            client=Langfuse(base_url=os.environ['LANGFUSE_BASE_URL'],environment='local-development',release=cfg['experiment_id'],mask=safe_mask)
            if not client.auth_check():raise RuntimeError('Langfuse authentication failed')
        local.client=client;identity=local.identity();e.save(folder/'model.json',identity)
        if (folder/'expected-model.json').exists() and e.read(folder/'expected-model.json')!=identity:raise ValueError('Model identity changed')
        if mode=='replay':raise ValueError('Use the experiment replay command in README; no implicit regeneration')
        started=time.perf_counter();records=[];all_calls=[]
        if not (folder/'graph-lock.json').exists():
            def build(entry):
                doc=entry['document'];model=Hybrid(folder,cfg,client,budget,doc['id'])
                prop=propagate_attributes(session_id=session+'-build',tags=['deepseek-extraction','source-only']) if client else nullcontext()
                ctx=client.start_as_current_observation(name='build-deepseek-domain',as_type='chain',input=dict(document_id=doc['id'],sha256=doc['sha256'])) if client else nullcontext(None)
                with prop,ctx as obs:
                    record=e.extract_document(root,folder,doc,cfg,model)
                    base=Graph().parse(folder/'graphs'/f"{doc['id']}.ttl")
                    enriched,crecord=expand(record,base,model)
                    e.save(cfolder/'graphs'/f"{doc['id']}.json",crecord);enriched.serialize(cfolder/'graphs'/f"{doc['id']}.ttl",format='turtle')
                    if obs:obs.update(output=dict(provisions=len(record['provisions']),base_links=sum(x['traversable'] for x in record['links']),extra_links=sum(x['traversable'] for x in crecord['expanded_links'])))
                print('Finished both graph variants: '+doc['id'],flush=True)
                return record,model.calls
            # Guard is installed once around the thread pool; no per-thread monkeypatch races.
            with e.access_guard(root,'extraction') as opened:
                with ThreadPoolExecutor(max_workers=cfg['workers']) as pool:
                    for record,calls in pool.map(build,inputs):records.append(record);all_calls.extend(calls)
            e.save(folder/'extraction-access-audit.json',dict(files=sorted(set(opened)),benchmark_access_attempts=0))
            e.freeze_graphs(folder,inputs);e.freeze_graphs(cfolder,inputs)
            summary=dict(agreements=len(records),provisions=sum(len(r['provisions']) for r in records),seconds=time.perf_counter()-started,calls=len(all_calls),input_tokens=sum(c['input'] for c in all_calls),output_tokens=sum(c['output'] for c in all_calls),api_usd=sum(c['cost_usd'] for c in all_calls),workers=cfg['workers'],model=cfg['remote_model'],provider=cfg['provider'])
            e.save(folder/'extraction-summary.json',summary);e.save(cfolder/'extraction-summary.json',summary)
        for sub in [folder,cfolder]:
            e.verify_graphs(sub)
        queries=e.select_queries(root,folder,inputs,cfg)
        # Verify identical questions to the predeclared previous development run.
        previous=e.read(root/cfg['baseline_run']/'queries.json')
        if queries!=previous[:len(queries)]:raise ValueError('Question cohort differs from baseline')
        for name in ['inputs.json','queries.json','query-bank-identity.json','model.json']:
            shutil.copyfile(folder/name,cfolder/name)
        (cfolder/'code').mkdir(exist_ok=True)
        for name in ['evaluation','upstream.json']:
            src=folder/'code'/name;dst=cfolder/'code'/name
            if src.is_dir():shutil.copytree(src,dst,dirs_exist_ok=True)
            else:shutil.copyfile(src,dst)
        # ALL B/C query outputs precede any benchmark evidence scoring.
        for variant,sub in [('existing',folder),('expanded',cfolder)]:
            e.RELATIONS=list(dict.fromkeys(['qualifies','exception_to','applies_after','requires','references']+(EXTRA if variant=='expanded' else [])))
            e.GraphTools.inspect=expanded_inspect if variant=='expanded' else ORIGINAL_INSPECT
            for index,q in enumerate(queries,1):
                print(f"Query {variant} {index}/{len(queries)} source {q['source_index']}",flush=True)
                local=Hybrid(sub,cfg,client,budget,variant+'-'+str(q['source_index']))
                graph=Graph().parse(sub/'graphs'/f"{q['document_id']}.ttl")
                prop=propagate_attributes(session_id=session+'-'+variant,tags=['deepseek-graphs',variant,'local-query-agent']) if client else nullcontext()
                ctx=client.start_as_current_observation(name='answer-via-domain-graph',as_type='chain',input=dict(question=q['question'],document_id=q['document_id'],variant=variant)) if client else nullcontext(None)
                with prop,ctx as obs:
                    with e.access_guard(root,'graph-search') as opened:
                        result=e.search_graph(q['question'],graph,cfg,local,client);answer=e.answer_question(q['question'],result,cfg,local)
                    e.save(sub/f"output-{q['source_index']}.json",dict(sample=q,**result,answer=answer,trace_id=obs.trace_id if obs else None,trace_url=client.get_trace_url(trace_id=obs.trace_id) if obs else None))
                    e.save(sub/'audits'/f"query-{q['source_index']}.json",dict(raw_source_access=False,gold_access=False,files=sorted(set(opened))))
                    if obs:obs.update(output=dict(answer=answer['answer'],evidence=result['output']))
                local.unload()
                if client:client.flush()
        e.baseline(root,folder,queries,cfg);shutil.copyfile(folder/'vector-outputs.json',cfolder/'vector-outputs.json')
        reports={}
        for variant,sub in [('existing',folder),('expanded',cfolder)]:
            e.save(sub/'config.json',dict(experiment=cfg['experiment_id']+'-'+variant,settings=cfg,mode=mode))
            reports[variant]=e.evaluate(root,sub,queries,cfg,client);e.verify_graphs(sub)
            e.save(sub/'variant.json',dict(variant=variant))
        e.save(folder/'comparison.json',dict(baseline=e.read(root/cfg['baseline_run']/'results.json')['summary'],existing=reports['existing']['summary'],expanded=reports['expanded']['summary'],extraction=e.read(folder/'extraction-summary.json')))
        # Replace inherited local-only cost wording with the actual API build spend.
        for sub in [folder,cfolder]:
            p=sub/'results.md';p.write_text(p.read_text(encoding='utf-8').replace('Local paid API cost is zero;',f"Query model API cost is zero; inherited extraction/relationship API cost is recorded separately ({e.read(folder/'extraction-summary.json')['api_usd']:.6f} USD across both graph variants);"),encoding='utf-8')
        e.save(folder/'execution-proof.json',dict(isolated_python=__import__('sys').flags.isolated,module=str(Path(__file__).resolve()),engine_sha256=e.sha(HERE/'engine.py')))
        e.finish(cfolder,'complete');e.finish(folder,'complete');print(json.dumps(e.read(folder/'comparison.json'),indent=2),flush=True)
    except Exception as error:e.finish(folder,'failed',str(error));raise
    finally:
        if client:client.flush();client.shutdown()
