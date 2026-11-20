"""Domain extraction and bounded graph-only evidence agent. No RAG in the agent."""
import builtins
from contextlib import contextmanager, nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import time
import urllib.request
from statistics import mean
from unittest.mock import patch

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef

HERE=Path(__file__).resolve().parent
D=Namespace('https://cimulink.local/ontology/domain-contract/1#')
RELATIONS=['qualifies','exception_to','applies_after','requires','references']
KINDS=['Permission','Obligation','Prohibition','Discretion','Status','Declaration','Term','Payment','Amendment','Other']
ENTITY_KINDS=['Organization','PartyRole','Person','Product','Place','GenericScope','EventType','Agreement','Document','Unknown']


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');temp.replace(p)
def array(item,maximum):return dict(type='array',items=item,maxItems=maximum)
def string(maximum=200):return dict(type='string',maxLength=maximum)
def enum(values):return dict(type='string',enum=values)
def obj(**fields):return dict(type='object',properties=fields,required=list(fields),additionalProperties=False)


@contextmanager
def access_guard(root,stage):
    """Enforce source-only extraction and graph-only querying at the file boundary."""
    opened=[]
    def wrap(opener):
        def checked(file,*args,**kwargs):
            if isinstance(file,(str,os.PathLike)):
                p=Path(file).resolve();s=p.as_posix().lower()
                if any(x in s for x in ('questions.json','expected-evidence.json','/data/benchmarks/','/comparison-v1/','queries.json','vector-outputs.json')):
                    raise RuntimeError('Benchmark/other-stage data forbidden during '+stage+': '+p.name)
                if stage=='graph-search' and p.is_relative_to(root/'data/corpus'):
                    raise RuntimeError('Raw corpus access forbidden in graph-only search')
                opened.append(str(p))
            return opener(file,*args,**kwargs)
        return checked
    with patch('builtins.open',wrap(builtins.open)),patch('io.open',wrap(io.open)):
        yield opened


def units(text,maximum):
    # Preserve all non-whitespace text and stable offsets, splitting at sentence/paragraph/section boundaries.
    boundaries=[0]+[m.end() for m in re.finditer(r'\n\s*\n|(?<=[.!?;])\s+(?=[A-Z0-9])',text)]+[len(text)]
    out=[]
    for a,b in zip(boundaries,boundaries[1:]):
        while a<b:
            end=min(b,a+maximum)
            if end<b:
                space=text.rfind(' ',a+maximum//2,end)
                if space>a:end=space+1
            if text[a:end].strip():out.append(dict(id=f'P{len(out)+1:04}',span=[a,end],text=text[a:end]))
            a=end
    return out


def batches(passages,maximum):
    batch=[];size=0
    for p in passages:
        if batch and size+len(p['text'])>maximum:yield batch;batch=[];size=0
        batch.append(p);size+=len(p['text'])
    if batch:yield batch


def source_text(root,doc):
    path=root/'data/corpus'/doc['local_file_path']
    if sha(path)!=doc['sha256']:raise ValueError('Source hash changed: '+doc['id'])
    return path.read_text(encoding='utf-8')


class Model:
    def __init__(self,folder,cfg,client=None):self.folder=folder;self.cfg=cfg;self.client=client;self.calls=[]
    def api(self,path,value=None):
        req=urllib.request.Request(self.cfg['api']+path,data=json.dumps(value).encode() if value is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=300) as response:return json.load(response)
    def identity(self):
        model=next(m for m in self.api('/api/tags')['models'] if m['name']==self.cfg['model'])
        if model['digest']!=self.cfg['model_digest']:raise ValueError('Wrong local model digest')
        return dict(name=model['name'],digest=model['digest'],runtime=self.api('/api/version'))
    def unload(self):self.api('/api/generate',dict(model=self.cfg['model'],keep_alive=0))
    def call(self,name,prompt,data,schema,stage,options=None):
        messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps(data,ensure_ascii=False))]
        payload=dict(model=self.cfg['model'],messages=messages,stream=False,format=schema,
                     options=options or self.cfg['options'],keep_alive='10m')
        key=hashlib.sha256((self.cfg['model_digest']+json.dumps(payload,sort_keys=True)).encode()).hexdigest()
        path=self.folder/'responses'/stage/f'{key}.json';cached=path.exists();started=time.perf_counter()
        # Reuse exact older requests when available, but avoid known-underbudget first attempts on new dense extraction batches.
        if stage=='extraction' and not cached and payload['options']['num_predict']<4096:
            return self.call(name,prompt,data,schema,stage,dict(payload['options'],num_predict=4096))
        context=self.client.start_as_current_observation(name=name,as_type='generation',input=messages,model=self.cfg['model'],model_parameters=payload['options'],metadata=dict(request_fingerprint=key,cache_hit=cached,stage=stage),cost_details={'input':0,'output':0,'total':0}) if self.client else nullcontext(None)
        with context as observation:
            if cached:
                if read(path.with_name(key+'-request.json'))!=payload:raise ValueError('Cached extraction request differs')
                raw=read(path)
            else:
                save(path.with_name(key+'-request.json'),payload)
                raw=self.api('/api/chat',payload);save(path,raw)
            usage=dict(input=raw.get('prompt_eval_count',0),output=raw.get('eval_count',0))
            truncated=raw.get('done_reason')!='stop'
            if observation:observation.update(output=raw['message'],usage_details={k:0 if cached else v for k,v in usage.items()},metadata=dict(model_timings_seconds={k:raw.get(k,0)/1e9 for k in ('load_duration','prompt_eval_duration','eval_duration')},stage=stage,request_fingerprint=key,cache_hit=cached,truncated=truncated))
        call=dict(stage=stage,name=name,key=key,cache_hit=cached,seconds=time.perf_counter()-started,**usage)
        self.calls.append(call);save(self.folder/'model-calls.json',self.calls)
        if truncated:
            if payload['options']['num_predict']>=4096:raise ValueError('Truncated model response after bounded retry: '+key)
            retry=dict(payload['options'],num_predict=4096)
            print('Retry truncated '+stage+' with 4096 output-token cap',flush=True)
            return self.call(name,prompt,data,schema,stage,retry)
        parsed=json.loads(raw['message']['content'])
        validate_shape(parsed,schema)
        return parsed


def validate_shape(value,schema):
    kind=schema['type']
    if kind=='object':
        if not isinstance(value,dict) or set(value)!=set(schema['required']):raise ValueError('Invalid model object fields')
        for k,v in value.items():validate_shape(v,schema['properties'][k])
    elif kind=='array':
        if not isinstance(value,list) or len(value)>schema['maxItems']:raise ValueError('Invalid model array')
        for item in value:validate_shape(item,schema['items'])
    elif kind=='string':
        if not isinstance(value,str) or len(value)>schema.get('maxLength',10**9):raise ValueError('Invalid model string')
        if 'enum' in schema and value not in schema['enum']:raise ValueError('Unknown model ID/category')
    elif kind=='boolean':
        if not isinstance(value,bool):raise ValueError('Invalid model boolean')


def extraction_schema(ids,cfg):
    evidence=array(enum(ids),4)
    condition=obj(text=string(220),kind=enum(['condition','exception','time','scope']),sources=evidence)
    return obj(provisions=array(obj(kind=enum(KINDS),actor=string(120),actor_kind=enum(ENTITY_KINDS),action=string(100),target=string(120),target_kind=enum(ENTITY_KINDS),meaning=string(320),sources=evidence,conditions=array(condition,4),references=array(string(80),4)),cfg['max_provisions_per_batch']),uncertainties=array(string(200),8))


def extract_document(root,folder,doc,cfg,model):
    text=source_text(root,doc);passages=units(text,cfg['unit_characters'])
    records=[];uncertainties=[];calls_start=len(model.calls);started=time.perf_counter()
    for index,batch in enumerate(batches(passages,cfg['extraction_batch_characters'])):
        print(f"Extract {doc['id']} batch {index+1}: {len(batch)} passages",flush=True)
        result=model.call('extract-domain-provisions',(HERE/'prompt.txt').read_text(),dict(document=doc['id'],identity_context=text[:550],passages=batch),extraction_schema([p['id'] for p in batch],cfg),'extraction')
        valid={p['id'] for p in batch}
        for record in result['provisions']:
            if not record['sources'] or not set(record['sources'])<=valid:raise ValueError('Provision lacks valid source support')
            for condition in record['conditions']:
                if not condition['sources']:raise ValueError('Condition lacks source support')
            records.append(dict(id=f'R{len(records)+1:04}',**record))
        uncertainties.extend(result['uncertainties'])
    # Source-only cross-provision pass: IDs and source evidence are available; no questions.
    schema=obj(links=array(obj(source=enum([r['id'] for r in records]),relation=enum(RELATIONS),target=enum([r['id'] for r in records]),sources=array(enum([p['id'] for p in passages]),6)),20),uncertainties=array(string(200),10))
    data=relation_context(records,passages)
    if records and len(json.dumps(data,ensure_ascii=False))<=30000:
        related=model.call('connect-domain-provisions',(HERE/'relations-prompt.txt').read_text(),data,schema,'extraction-links',cfg['relation_options'])
    else:
        related=dict(links=[],uncertainties=['Cross-provision inference skipped: no provisions or compact context exceeds 30000 characters; direct qualifications remain represented.'])
    record=dict(document=doc,passages=passages,provisions=records,links=related['links'],uncertainties=uncertainties+related['uncertainties'],seconds=time.perf_counter()-started,calls=model.calls[calls_start:])
    validate_record(record,text);screen_links(record);save(folder/'graphs'/f"{doc['id']}.json",record)
    graph=to_graph(record);graph.serialize(folder/'graphs'/f"{doc['id']}.ttl",format='turtle')
    print(f"Saved {doc['id']}: {len(records)} provisions, {sum(x['traversable'] for x in record['links'])}/{len(record['links'])} proposed links pass conservative screen",flush=True)
    model.unload()
    return record


def relation_context(records,passages):
    data=dict(provisions=records,passages=passages)
    if len(json.dumps(data,ensure_ascii=False))>30000:
        data=dict(provisions=[{k:r[k] for k in ('id','kind','action','meaning','sources')} for r in records],
                  passages=[dict(id=p['id'],text=p['text']) for p in passages])
    return data


def validate_record(record,text):
    passages={p['id']:p for p in record['passages']};rules={r['id']:r for r in record['provisions']}
    covered=set()
    for p in passages.values():
        a,b=p['span'];assert 0<=a<b<=len(text) and text[a:b]==p['text']
        covered.update(range(a,b))
    assert all(i in covered for i,c in enumerate(text) if not c.isspace()),'Source text omitted'
    for r in rules.values():
        assert r['sources'] and set(r['sources'])<=set(passages)
        for c in r['conditions']:assert c['sources'] and set(c['sources'])<=set(passages)
    for link in record['links']:
        assert link['source'] in rules and link['target'] in rules
        assert set(link['sources'])<=set(passages)


def screen_links(record):
    """Conservative textual screen, NOT a proof of legal relationship correctness."""
    passages={p['id']:p for p in record['passages']};rules={r['id']:r for r in record['provisions']}
    cues={'qualifies':r'\b(unless|subject to|provided|except|however|only|limited)\b',
          'exception_to':r'\b(unless|except|notwithstanding|however)\b',
          'applies_after':r'\b(after|following|upon)\b.{0,60}\b(terminat\w*|expir\w*)\b',
          'requires':r'\b(must|required|subject to|only if|condition|consent|approval)\b',
          'references':r'\b(section|clause|article|paragraph|appendix|exhibit)\s+[A-Z0-9]'}
    for link in record['links']:
        a,b=rules[link['source']],rules[link['target']]
        if link['source']==link['target'] or not link['sources']:
            link.update(traversable=False,screeningStatus='REVIEW_ONLY_SELF_LINK_OR_MISSING_EVIDENCE')
            continue
        source=' '.join(passages[p]['text'] for p in a['sources'])
        same_passage=bool(set(a['sources']) & set(b['sources']))
        explicit_reference=False
        for p in b['sources']:
            start=passages[p]['text'].strip()
            number=re.match(r'(?:(?:section|clause|article)\s+)?(\d+(?:\.\d+)*)[.)]?\s',start,re.I)
            if number and re.search(r'\b(?:section|clause|article|paragraph)\s+'+re.escape(number[1])+r'(?![\d.])',source,re.I):explicit_reference=True
        cue=bool(re.search(cues[link['relation']],source,re.I|re.S))
        accepted=cue and (same_passage or explicit_reference)
        if link['relation']=='applies_after':accepted=accepted and bool(re.search(r'terminat|expir',b['action']+' '+b['meaning'],re.I))
        link['traversable']=accepted
        link['screeningStatus']='TEXT_CUE_AND_LOCAL_OR_EXPLICIT_REFERENCE; UNREVIEWED' if accepted else 'REVIEW_ONLY_NO_EXPLICIT_PATH_SUPPORT'
    return record


def to_graph(record):
    e=Namespace('https://cimulink.local/agreements/domain10/'+record['document']['id']+'#')
    g=Graph();g.bind('d',D);g.bind('ex',e)
    def entity(id,kind,label):
        n=e[id];g.add((n,RDF.type,D[kind]));g.add((D[kind],RDF.type,OWL.Class));g.add((n,RDFS.label,Literal(label)));return n
    def edge(s,p,o):g.add((s,D[p],o));g.add((D[p],RDF.type,OWL.ObjectProperty))
    def value(s,p,v):g.add((s,D[p],Literal(v)));g.add((D[p],RDF.type,OWL.DatatypeProperty))
    agreement=entity('Agreement','Agreement',record['document']['file_path'])
    value(agreement,'sourcePath',record['document']['file_path']);value(agreement,'sourceSHA256',record['document']['sha256']);value(agreement,'reviewStatus','UNREVIEWED_LOCAL_LLM_PROPOSED')
    for p in record['passages']:
        n=entity(p['id'],'SourcePassage',p['id']);value(n,'startChar',p['span'][0]);value(n,'endChar',p['span'][1]);value(n,'exactText',p['text']);edge(n,'withinAgreement',agreement)
    def mentioned(label,kind):
        key=hashlib.sha256((kind+'|'+label.strip().casefold()).encode()).hexdigest()[:12]
        n=entity('E'+key,kind,label);edge(n,'withinAgreement',agreement)
        if kind in ('GenericScope','EventType','Unknown'):value(n,'instanceStatus','DESCRIPTION_NOT_ACTUAL_EVENT_OR_TRANSACTION')
        return n
    for r in record['provisions']:
        n=entity(r['id'],r['kind'],r['action']);edge(agreement,'hasProvision',n);edge(n,'withinAgreement',agreement)
        edge(n,'actor',mentioned(r['actor'],r['actor_kind']));edge(n,'target',mentioned(r['target'],r['target_kind']))
        value(n,'meaning',r['meaning']);value(n,'reviewStatus','UNREVIEWED')
        for p in r['sources']:edge(n,'supportedBy',e[p])
        for i,c in enumerate(r['conditions']):
            cn=entity(r['id']+'C'+str(i),'Condition',c['text']);edge(n,c['kind'],cn)
            for p in c['sources']:edge(cn,'supportedBy',e[p])
        for i,ref in enumerate(r['references']):
            rn=entity(r['id']+'Ref'+str(i),'Reference',ref);edge(n,'referencesSection',rn);value(rn,'resolutionStatus','UNRESOLVED')
    for index,relation in enumerate(record['links']):
        if relation.get('traversable',False):edge(e[relation['source']],relation['relation'],e[relation['target']])
        statement=entity('Link'+str(index),'ProposedRelationship',relation['relation'])
        edge(statement,'fromProvision',e[relation['source']]);edge(statement,'toProvision',e[relation['target']]);value(statement,'predicate',relation['relation']);value(statement,'reviewStatus','UNREVIEWED')
        value(statement,'traversable',relation.get('traversable',False));value(statement,'screeningStatus',relation.get('screeningStatus','NOT_SCREENED'))
        for p in relation['sources']:edge(statement,'supportedBy',e[p])
    for i,note in enumerate(record['uncertainties']):value(agreement,'uncertainty',note)
    return g


class GraphTools:
    """All search data is read from parsed TTL, never the extraction JSON or corpus."""
    def __init__(self,graph,cfg):
        self.g=graph;self.cfg=cfg;self.rules={};self.passages={};self.revealed={};self.steps=[]
        for n in graph.subjects(D.exactText,None):
            self.passages[self.id(n)]=dict(id=self.id(n),span=[int(graph.value(n,D.startChar)),int(graph.value(n,D.endChar))],text=str(graph.value(n,D.exactText)))
        for agreement in graph.subjects(RDF.type,D.Agreement):
            self.file_path=str(graph.value(agreement,D.sourcePath))
            for n in graph.objects(agreement,D.hasProvision):self.rules[self.id(n)]=n
    @staticmethod
    def id(n):return str(n).split('#')[-1]
    def directory(self):
        rows=[]
        for id,n in sorted(self.rules.items()):
            rows.append(dict(id=id,kind=self.id(self.g.value(n,RDF.type)),action=str(self.g.value(n,RDFS.label)),actor=[str(self.g.value(x,RDFS.label)) for x in self.g.objects(n,D.actor)],target=[str(self.g.value(x,RDFS.label)) for x in self.g.objects(n,D.target)]))
        if len(json.dumps(rows))>20000:raise ValueError('Graph directory too large; no silent truncation')
        return rows
    def inspect(self,ids):
        if len(ids)>self.cfg['inspect_limit'] or any(id not in self.rules for id in ids):raise ValueError('Invalid graph inspection IDs')
        nodes=set(self.rules[id] for id in ids);paths=[]
        for n in list(nodes):
            neighbors=[]
            for rel in RELATIONS:
                for target in self.g.objects(n,D[rel]):neighbors.append((n,rel,target))
                for source in self.g.subjects(D[rel],n):neighbors.append((source,rel,n))
            for a,rel,b in sorted(neighbors,key=lambda x:tuple(map(str,x)))[:self.cfg['neighbor_limit']]:
                nodes.update([a,b]);paths.append([self.id(a),rel,self.id(b)])
        result=[]
        for n in sorted(nodes,key=str):
            if self.id(n) not in self.rules:continue
            evidence=set(self.g.objects(n,D.supportedBy));conditions=[]
            for rel in ('condition','exception','time','scope'):
                for c in self.g.objects(n,D[rel]):
                    evidence.update(self.g.objects(c,D.supportedBy));conditions.append(dict(relation=rel,text=str(self.g.value(c,RDFS.label))))
            sources=[]
            for p in sorted(evidence,key=str):
                value=self.passages[self.id(p)];self.revealed[value['id']]=value;sources.append(value)
            result.append(dict(id=self.id(n),meaning=str(self.g.value(n,D.meaning)),conditions=conditions,passages=sources))
        packet=dict(provisions=result,paths=paths)
        if len(json.dumps(packet))>26000:raise ValueError('Graph tool response exceeds context cap')
        self.steps.append(dict(request=ids,response=packet));return packet


def evidence_output(tool,ids,budget):
    if len(ids)!=len(set(ids)) or any(id not in tool.revealed for id in ids):raise ValueError('Agent selected unrevealed passage')
    # Deduplicate source overlaps, retaining model ordering and the common character budget.
    from compare_retrieval import apply_budget
    passages=[dict(id=p['id'],file_path=tool.file_path,span=p['span'],text=p['text']) for p in [tool.revealed[id] for id in ids]]
    # apply_budget only needs source slices: materialize a virtual character buffer from graph quotations.
    maximum=max((p['span'][1] for p in tool.passages.values()),default=0);chars=[' ']*maximum
    for p in tool.passages.values():chars[p['span'][0]:p['span'][1]]=p['text']
    return apply_budget(passages,{tool.file_path:''.join(chars)},budget)


def search_graph(question,graph,cfg,model,client=None):
    tool=GraphTools(graph,cfg);history=[];start=len(model.calls);started=time.perf_counter();stop='round_limit';decision=None
    for round in range(cfg['agent_rounds']):
        allowed=list(tool.rules);revealed=list(tool.revealed)
        schema=obj(action=enum(['inspect','finish']),provision_ids=array(enum(allowed),cfg['inspect_limit']),passage_ids=array(enum(revealed) if revealed else string(20),20),needs_more_context=dict(type='boolean'),note=string(300))
        decision=model.call('plan-graph-evidence',(HERE/'search-prompt.txt').read_text(),dict(question=question,directory=tool.directory(),history=history,round=round+1,round_limit=cfg['agent_rounds']),schema,'search',cfg['search_options'])
        if decision['action']=='finish':
            if not tool.revealed:stop='no_evidence_inspected';break
            stop='model_finished';break
        if not decision['provision_ids']:stop='empty_inspection';break
        context=client.start_as_current_observation(name='inspect-graph-provisions',as_type='tool',input={'provision_ids':decision['provision_ids']}) if client else nullcontext(None)
        with context as obs:
            packet=tool.inspect(decision['provision_ids'])
            if obs:obs.update(output=packet)
        history.append(dict(decision=decision,tool_result=packet))
        if len(json.dumps(history))>33000:stop='context_limit';break
    ids=decision['passage_ids'] if decision and decision['action']=='finish' else list(tool.revealed)
    if any(id not in tool.revealed for id in ids):raise ValueError('Unknown/unrevealed final passage')
    output=evidence_output(tool,ids,cfg['character_budget'])
    return dict(output=output,seconds=time.perf_counter()-started,timing_scope='graph-retrieval-only',stop=stop,
                needs_more_context=(decision or {}).get('needs_more_context',True) or stop!='model_finished',decision=decision,tool_steps=tool.steps,calls=model.calls[start:],revealed_ids=list(tool.revealed),selected_ids=ids)


def freeze_graphs(folder,inputs):
    lock=dict(documents=[e['document']['id'] for e in inputs],files={p.relative_to(folder).as_posix():sha(p) for p in sorted((folder/'graphs').glob('*')) if p.is_file()},
              created_before_question_selection=True,extraction_code_sha256=sha(HERE/'pipeline.py'),prompt_sha256=sha(HERE/'prompt.txt'))
    save(folder/'graph-lock.json',lock)
    return lock


def verify_graphs(folder):
    lock=read(folder/'graph-lock.json')
    for name,digest in lock['files'].items():
        if sha(folder/name)!=digest:raise ValueError('Frozen domain graph changed: '+name)
    return lock


def select_queries(root,folder,inputs,cfg):
    # First benchmark read occurs only AFTER all ten graphs have been frozen.
    verify_graphs(folder)
    bank_path=root/'experiments/cuad-100/questions.json'
    identity={'sha256':sha(bank_path)}
    if (folder/'query-bank-identity.json').exists() and read(folder/'query-bank-identity.json')!=identity:raise ValueError('Question bank version changed')
    bank=read(bank_path)['tests'];rng=random.Random(cfg['query_seed']);queries=[];missing=[]
    for e in inputs:
        doc=e['document']
        # Input question metadata only; answer strings/offsets do not enter the query packet.
        candidates=[q for q in bank if q.get('snippets') and all(s['file_path']==doc['file_path'] for s in q['snippets'])]
        if not candidates:missing.append(doc['id']);continue
        for q in rng.sample(sorted(candidates,key=lambda q:q['source_index']),min(cfg['questions_per_agreement'],len(candidates))):
            queries.append(dict(source_index=q['source_index'],question=q['query'],document_id=doc['id'],file_path=doc['file_path']))
    if (folder/'queries.json').exists():
        if read(folder/'queries.json')!=queries:raise ValueError('Frozen query selection changed')
    else:save(folder/'queries.json',queries)
    save(folder/'query-bank-identity.json',identity)
    save(folder/'query-selection.json',dict(seed=cfg['query_seed'],questions=len(queries),missing_agreements=missing,method='One random benchmark question per selected agreement, all task topics eligible; oracle correct agreement; selected after graph freeze, not based on scores.'))
    return queries


def answer_question(question,retrieval,cfg,model):
    ids=list(dict.fromkeys(p['id'] for p in retrieval['output']))
    schema=obj(answer=string(2000),citations=array(enum(ids) if ids else string(20),20),uncertain=dict(type='boolean'))
    before=len(model.calls);started=time.perf_counter()
    answer=model.call('answer-from-graph-evidence',(HERE/'answer-prompt.txt').read_text(),dict(question=question,evidence=retrieval['output'],needs_more_context=retrieval['needs_more_context'],stop=retrieval['stop']),schema,'answer',cfg['answer_options'])
    if any(c not in ids for c in answer['citations']):raise ValueError('Answer citation not in supplied evidence')
    if not ids and (not answer['uncertain'] or answer['citations']):raise ValueError('Empty evidence must produce uncertainty')
    return dict(**answer,seconds=time.perf_counter()-started,calls=model.calls[before:],citation_ids_valid=True,answer_correctness='NOT_AUTOMATICALLY_SCORED')


def baseline(root,folder,queries,cfg):
    from rag_runtime import connect,load_model,QUERY_PREFIX
    from pgvector.psycopg import register_vector
    from compare_retrieval import apply_budget
    outputs={};started=time.perf_counter();ingestion='d891bfe3634a5bf21d97'
    with connect() as conn:
        register_vector(conn)
        settings=conn.execute('SELECT config FROM rag_lab.ingestions WHERE id=%s',(ingestion,)).fetchone()[0]
        model,revision=load_model(settings['revision'],local_files_only=True)
        model_seconds=time.perf_counter()-started
        for q in queries:
            start=time.perf_counter();vector=model.encode(QUERY_PREFIX+q['question'],normalize_embeddings=True)
            rows=conn.execute('SELECT file_path,start_char,end_char,content,embedding <=> %s AS distance FROM rag_lab.chunks WHERE ingestion_id=%s AND file_path=%s ORDER BY distance,id LIMIT 5',(vector,ingestion,q['file_path'])).fetchall()
            candidates=[dict(file_path=p,span=[a,b],text=t,distance=d) for p,a,b,t,d in rows]
            text=(root/'data/corpus'/q['file_path']).read_text(encoding='utf-8')
            outputs[str(q['source_index'])]=dict(output=apply_budget(candidates,{q['file_path']:text},cfg['character_budget']),seconds=time.perf_counter()-start)
        conn.rollback()
    save(folder/'vector-outputs.json',outputs)
    save(folder/'vector-environment.json',dict(ingestion=ingestion,revision=revision,settings=settings,model_load_seconds=model_seconds,scope='Evaluation comparator only; vector results never enter graph agent'))
    return outputs


def evaluate(root,folder,queries,cfg,client=None):
    # Every graph retrieval AND generated answer is saved before gold is used here.
    from scorer import score
    from evaluate import upstream
    types=upstream();bank_path=root/'experiments/cuad-100/questions.json'
    if sha(bank_path)!=read(folder/'query-bank-identity.json')['sha256']:raise ValueError('Scoring bank changed')
    bank={q['source_index']:q for q in read(bank_path)['tests']}
    vectors=read(folder/'vector-outputs.json');rows=[]
    for q in queries:
        saved=read(folder/f"output-{q['source_index']}.json");gold=bank[q['source_index']]
        assert q['question']==gold['query']
        text=(root/'data/corpus'/q['file_path']).read_text(encoding='utf-8');texts={q['file_path']:text}
        for p in saved['output']:
            a,b=p['span'];assert p['file_path']==q['file_path'] and text[a:b]==p['text']
        import copy
        graph_score=score(copy.deepcopy(saved['output']),gold,texts,types)
        vector_score=score(copy.deepcopy(vectors[str(q['source_index'])]['output']),gold,texts,types)
        record=read(folder/'graphs'/f"{q['document_id']}.json")
        modeled_ids={id for r in record['provisions'] for id in r['sources']}|{id for r in record['provisions'] for c in r['conditions'] for id in c['sources']}
        modeled=[dict(file_path=q['file_path'],span=p['span'],text=p['text']) for p in record['passages'] if p['id'] in modeled_ids]
        coverage=score(modeled,gold,texts,types)['recall']
        graph_calls=saved.get('calls',[]);answer=saved['answer']
        metrics=dict(precision=graph_score['precision'],recall=graph_score['recall'],returned_characters=graph_score['returned_characters'],vector_precision=vector_score['precision'],vector_recall=vector_score['recall'],vector_characters=vector_score['returned_characters'],modeled_evidence_recall_ceiling=coverage)
        if client and saved.get('trace_id'):
            for name,value in metrics.items():client.create_score(trace_id=saved['trace_id'],name=name,value=value,data_type='NUMERIC')
        rows.append(dict(**q,metrics=metrics,seconds=saved['seconds'],answer_seconds=answer.get('seconds'),vector_seconds=vectors[str(q['source_index'])].get('seconds'),graph_calls=len(graph_calls),answer_calls=len(answer.get('calls',[])),input_tokens=sum(c['input'] for c in graph_calls+answer.get('calls',[])),output_tokens=sum(c['output'] for c in graph_calls+answer.get('calls',[])),needs_more_context=saved['needs_more_context'],answer=answer,trace_url=saved.get('trace_url'),timing_scope=saved['timing_scope'],scored=graph_score))
    if not rows:raise ValueError('No benchmark queries available')
    summary={k:mean(r['metrics'][k] for r in rows) for k in rows[0]['metrics']}
    for metric,key in [('mean_retrieval_seconds','seconds'),('mean_answer_seconds','answer_seconds'),('mean_vector_seconds','vector_seconds')]:
        values=[r[key] for r in rows if r[key] is not None];summary[metric]=mean(values) if values else None
    summary.update(full_recall=sum(r['metrics']['recall']>=.999999 for r in rows),queries=len(rows),input_tokens=sum(r['input_tokens'] for r in rows),output_tokens=sum(r['output_tokens'] for r in rows),actual_paid_model_api_usd=0)
    report=dict(experiment=cfg['experiment_id'],run_id=folder.name,summary=summary,results=rows,question_sha256=sha(folder/'queries.json'),scorer_sha256=sha(folder/'code/evaluation/v1/scorer.py'),gold_sha256=sha(bank_path),upstream_sha256=sha(folder/'code/upstream.json'),answer_quality='Citation existence checked; factual/legal answer correctness requires human review.')
    save(folder/'results.json',report)
    lines=['# Domain ontology: ten-agreement development experiment','', 'Graphs built from source text and sealed before benchmark question selection. Graph agent reads only TTL; no vector/keyword/raw-source fallback. One sampled question per agreement, all task topics eligible. Correct agreement is supplied: document routing is not measured.', '', '| Source | Agreement | Graph precision | Graph recall | Vector recall | Graph seconds |', '|---|---|---:|---:|---:|---:|']
    for r in rows:
        sec=f"{r['seconds']:.2f}" if r['seconds'] is not None else 'replay'
        lines.append(f"| {r['source_index']} | {r['document_id']} | {r['metrics']['precision']:.1%} | {r['metrics']['recall']:.1%} | {r['metrics']['vector_recall']:.1%} | {sec} |")
    lines+=['',f"Mean graph precision {summary['precision']:.1%}; recall {summary['recall']:.1%}; vector recall {summary['vector_recall']:.1%}. Full evidence: {summary['full_recall']}/{len(rows)}.", '', 'Metrics measure benchmark character overlap, not answer correctness. Graph retrieval and answer generation timings are separate. Extraction/setup is separate in extraction-summary.json. Local paid API cost is zero; hardware/electricity/labor are not priced. No hosted API cost equivalent is asserted.', '', 'Ten short development agreements are not a random or held-out sample. Full source text exists as graph passages, but only modeled, connected evidence is reachable through provision tools. Extraction coverage is not a proof of semantic correctness. Cross-provision links are proposed/unreviewed.', '', '[Detailed results](results.json) · [Frozen graphs](graphs/) · [Selected questions](queries.json) · [Extraction metrics](extraction-summary.json)']
    (folder/'results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return report


def finish(folder,status,error=None):
    save(folder/'manifest.json',dict(status=status,error=error))
    save(folder/'run-lock.json',dict(files={p.relative_to(folder).as_posix():sha(p) for p in folder.rglob('*') if p.is_file() and p.name!='run-lock.json' and '__pycache__' not in p.parts}))


def main(folder,mode,no_langfuse=False):
    root=Path(os.environ['LAB_PROJECT_ROOT']);cfg=read(HERE/'config.json');inputs=read(folder/'inputs.json')
    client=None;model=None
    save(folder/'manifest.json',dict(status='running',mode=mode))
    save(folder/'config.json',dict(experiment=cfg['experiment_id'],mode=mode,settings=cfg))
    try:
        for e in inputs:source_text(root,e['document'])
        if mode=='check':finish(folder,'validated');print('Domain experiment source/config imports validated; no inference.',flush=True);return
        if not no_langfuse:
            from dotenv import load_dotenv
            from langfuse import Langfuse
            from langfuse_retrieval import safe_mask
            load_dotenv(root/'.env')
            client=Langfuse(base_url=os.environ['LANGFUSE_BASE_URL'],environment='local-development',release='domain-ontology-v1',mask=safe_mask)
            if not client.auth_check():raise RuntimeError('Langfuse authentication failed')
        from langfuse import propagate_attributes
        session='domain-ontology-v1-'+folder.name
        if mode=='replay':
            save(folder/'model.json',read(folder/'expected-model.json'));queries=read(folder/'queries.json');verify_graphs(folder)
            for q in queries:
                p=folder/f"output-{q['source_index']}.json";s=read(p);s.update(seconds=None,timing_scope='replay-no-model-calls',trace_id=None,trace_url=None,calls=[]);s['answer'].update(seconds=None,calls=[]);save(p,s)
            vectors=read(folder/'vector-outputs.json')
            for v in vectors.values():v['seconds']=None
            save(folder/'vector-outputs.json',vectors)
        else:
            model=Model(folder,cfg,client);identity=model.identity()
            if (folder/'expected-model.json').exists() and read(folder/'expected-model.json')!=identity:raise ValueError('Model/runtime identity changed')
            save(folder/'model.json',identity)
            records=[];opened=[];extraction_started=time.perf_counter()
            if not (folder/'graph-lock.json').exists():
                with access_guard(root,'extraction') as opened:
                    for e in inputs:
                        doc=e['document']
                        prop=propagate_attributes(session_id=session+'-extraction',tags=['domain-ontology','source-only-extraction']) if client else nullcontext()
                        ctx=client.start_as_current_observation(name='build-domain-ontology',as_type='chain',input={'document_id':doc['id'],'source_sha256':doc['sha256']}) if client else nullcontext(None)
                        with prop,ctx as obs:
                            record=extract_document(root,folder,doc,cfg,model);records.append(record)
                            if obs:obs.update(output=dict(provisions=len(record['provisions']),links=len(record['links']),uncertainties=record['uncertainties']))
                        if client:client.flush()
                save(folder/'extraction-access-audit.json',dict(stage='source-only',files=sorted(set(opened)),benchmark_access_attempts=0))
                freeze_graphs(folder,inputs)
                calls=[c for c in model.calls if c['stage'].startswith('extraction')]
                save(folder/'extraction-summary.json',dict(agreements=len(records),provisions=sum(len(r['provisions']) for r in records),proposed_links=sum(len(r['links']) for r in records),traversable_links=sum(x['traversable'] for r in records for x in r['links']),seconds=time.perf_counter()-extraction_started,input_tokens=sum(c['input'] for c in calls),output_tokens=sum(c['output'] for c in calls),actual_input_tokens=sum(c['input'] for c in calls if not c['cache_hit']),actual_output_tokens=sum(c['output'] for c in calls if not c['cache_hit']),cache_hits=sum(c['cache_hit'] for c in calls),calls=len(calls),api_usd=0,review_status='UNREVIEWED_LOCAL_LLM_PROPOSED'))
            verify_graphs(folder);queries=select_queries(root,folder,inputs,cfg)
            for index,q in enumerate(queries,1):
                print(f"Graph query {index}/{len(queries)}: {q['document_id']} source {q['source_index']}",flush=True)
                graph=Graph().parse(folder/'graphs'/f"{q['document_id']}.ttl")
                prop=propagate_attributes(session_id=session,tags=['domain-ontology','graph-only','development']) if client else nullcontext()
                ctx=client.start_as_current_observation(name='answer-via-domain-graph',as_type='chain',input={'question':q['question'],'document_id':q['document_id']}) if client else nullcontext(None)
                with prop,ctx as obs:
                    with access_guard(root,'graph-search') as access:
                        result=search_graph(q['question'],graph,cfg,model,client)
                        answer=answer_question(q['question'],result,cfg,model)
                    saved=dict(sample=q,**result,answer=answer,trace_id=obs.trace_id if obs else None,trace_url=client.get_trace_url(trace_id=obs.trace_id) if obs else None)
                    save(folder/f"output-{q['source_index']}.json",saved)
                    save(folder/'audits'/f"query-{q['source_index']}.json",dict(raw_source_access=False,gold_access=False,files=sorted(set(access))))
                    if obs:obs.update(output=dict(answer=answer['answer'],evidence=result['output'],needs_more_context=result['needs_more_context']))
                model.unload()
                if client:client.flush()
            verify_graphs(folder)
            # Comparator is intentionally outside graph-only querying and never feeds that agent.
            baseline(root,folder,queries,cfg)
        report=evaluate(root,folder,queries,cfg,client)
        verify_graphs(folder)
        modules={name:str(Path(module.__file__).resolve()) for name,module in list(sys.modules.items()) if getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(folder/'code')}
        save(folder/'execution-proof.json',dict(isolated_python=sys.flags.isolated,modules=modules))
        finish(folder,'complete');print(json.dumps(report['summary'],indent=2));print('Report: '+str(folder/'results.md'),flush=True)
    except Exception as error:
        finish(folder,'failed',str(error));raise
    finally:
        if client:client.flush();client.shutdown()
