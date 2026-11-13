"""Langfuse adapter around frozen retrieval_v2; no credentials or benchmark access."""
import hashlib
import json
import time
from collections import defaultdict

from retrieval_v2 import API, MODEL, PROMPT, SETTINGS, EvidenceSearch, LocalSelector, lexical_scores
from rag_runtime import QUERY_PREFIX

HOSTED_RATE=dict(provider='Featherless',model='Qwen/Qwen3-4B-Instruct-2507',
    input_per_million_usd=.4,output_per_million_usd=.8,checked_at='2026-11-13',
    source='https://featherless.ai/models/Qwen/Qwen3-4B-Instruct-2507',
    caveat='Counterfactual full-price token estimate; not actual local spend, a bill or a guarantee of equivalent outputs.')


def hosted_estimate(input_tokens,output_tokens):
    return (input_tokens*HOSTED_RATE['input_per_million_usd']+
            output_tokens*HOSTED_RATE['output_per_million_usd'])/1_000_000


def safe_mask(*,data,**kwargs):
    """Keep meaningful source data; redact configuration secrets if accidentally supplied."""
    if isinstance(data,dict):
        return {k:('[REDACTED]' if any(word in k.lower() for word in
            ['secret','password','authorization','api_key','public_key']) else safe_mask(data=v))
            for k,v in data.items()}
    if isinstance(data,list):return [safe_mask(data=v) for v in data]
    if isinstance(data,str):
        import re
        return re.sub(r'\b(?:sk-lf|pk-lf)-[a-zA-Z0-9-]+','[REDACTED]',data)
    return data


def selector_payload(query,candidates,current,text,previous_queries):
    """Reconstruct the exact frozen request; fingerprint equality is checked on every call."""
    ids=[p['id'] for p in candidates]
    schema=dict(type='object',properties={
        'ranked_ids':dict(type='array',items=dict(type='string',enum=ids),maxItems=10),
        'evidence_sufficient':dict(type='boolean'),
        'missing_queries':dict(type='array',items=dict(type='string',maxLength=240),maxItems=2)},
        required=['ranked_ids','evidence_sufficient','missing_queries'],additionalProperties=False)
    previews=[]
    for p in candidates:
        a,b=p['span'];radius=SETTINGS['context_radius']
        previews.append(dict(id=p['id'],categories=p['categories'],original_span=p['span'],
            text=p['text'][:650],preview_truncated=len(p['text'])>650,
            before=text[max(0,a-radius):a],after=text[b:min(len(text),b+radius)]))
    return dict(model=MODEL,stream=False,keep_alive='10m',format=schema,
        options=dict(temperature=0,seed=42,num_ctx=12288,num_predict=512),
        messages=[dict(role='system',content=PROMPT),dict(role='user',content=json.dumps(dict(
            question=query,candidates=previews,current_evidence=[p['text'] for p in current],
            previous_queries=previous_queries),ensure_ascii=False))])


class TracedSelector(LocalSelector):
    def __init__(self,cache,model_digest,langfuse):
        super().__init__(cache,model_digest);self.langfuse=langfuse;self.hosted_equivalent_usd=0

    def choose(self,query,candidates,current,text,previous_queries):
        payload=selector_payload(query,candidates,current,text,previous_queries)
        fingerprint=hashlib.sha256((self.model_digest+json.dumps(payload,sort_keys=True)).encode()).hexdigest()
        cached=(self.cache/f'{fingerprint}.json').exists()
        index=len(self.calls)
        name=('qwen-rank-initial-candidates' if index==0 else
              'qwen-check-current-evidence' if index==1 else 'qwen-rank-and-check-follow-up')
        with self.langfuse.start_as_current_observation(name=name,as_type='generation',model=MODEL,
            input=dict(messages=payload['messages'],response_schema=payload['format']),
            model_parameters=payload['options'],cost_details={'input':0,'output':0,'total':0},
            metadata=dict(call_index=index+1,backend='local-ollama',cache_hit=cached,
                model_digest=self.model_digest,hosted_rate=HOSTED_RATE)) as span:
            result=super().choose(query,candidates,current,text,previous_queries)
            call=self.calls[-1]
            if call['cache_key']!=fingerprint:raise ValueError('Traced input does not match actual frozen model request')
            raw=json.loads((self.cache/f'{fingerprint}.json').read_text(encoding='utf-8'))
            usage={'input':raw.get('prompt_eval_count',0),'output':raw.get('eval_count',0)}
            # An application response-cache hit does not execute another model generation.
            actual_usage={'input':0,'output':0} if cached else usage
            estimate=0 if cached else hosted_estimate(usage['input'],usage['output'])
            self.hosted_equivalent_usd+=estimate
            span.update(output=dict(content=raw['message']['content'],parsed=result),usage_details=actual_usage,
                metadata=dict(call_index=index+1,backend='local-ollama',cache_hit=cached,
                    model_digest=self.model_digest,source_model_usage=usage,
                    source_model_timings_seconds={key:raw.get(key,0)/1e9 for key in
                        ['load_duration','prompt_eval_duration','eval_duration','total_duration']},
                    observed_wall_seconds=call['seconds'],preview_truncated_count=call['preview_truncated_count'],
                    hosted_equivalent_estimate_usd=estimate,hosted_rate=HOSTED_RATE,
                    actual_paid_api_cost_usd=0,exact_request_fingerprint_verified=True))
            return result


class TracedEmbedding:
    def __init__(self,model,langfuse,revision):
        self.wrapped=model;self.langfuse=langfuse;self.revision=revision

    def encode(self,text,**kwargs):
        with self.langfuse.start_as_current_observation(name='embed-search-question',as_type='embedding',
            input=text,model='BAAI/bge-small-en-v1.5',metadata={'revision':self.revision,'backend':'local-cpu'},
            cost_details={'input':0,'total':0}) as span:
            vector=self.wrapped.encode(text,**kwargs)
            span.update(output={'dimensions':int(vector.shape[-1]),'vector_preview':vector[:8].tolist(),
                                'normalized':True},usage_details={'input':len(self.wrapped.tokenizer.encode(text))})
            return vector


class TracedSearch(EvidenceSearch):
    def __init__(self,*args,langfuse,**kwargs):
        super().__init__(*args,**kwargs);self.langfuse=langfuse

    def collect(self,query):
        number=len(self.queries)+1
        with self.langfuse.start_as_current_observation(name='initial-search' if number==1 else 'follow-up-search',
            as_type='retriever',input=dict(query=query,file_path=self.path,preferred_kinds=sorted(self.preferred)),
            metadata=dict(query_number=number,category_policy='soft-preference',candidate_limit=20)) as parent:
            if query not in self.query_vectors:
                self.query_vectors[query]=self.model.encode(QUERY_PREFIX+query,normalize_embeddings=True)
            vector=self.query_vectors[query]
            with self.langfuse.start_as_current_observation(name='meaning-search',as_type='retriever',
                input={'query':query,'candidate_count':len(self.items),'scope':self.path}) as span:
                dense=[float(self.vectors[p['id']]@vector) for p in self.items]
                dense_ranks=sorted(range(len(self.items)),key=lambda i:(-dense[i],self.items[i]['id']))[:20]
                span.update(output=[{**self.items[i],'cosine_similarity':dense[i]} for i in dense_ranks])
            with self.langfuse.start_as_current_observation(name='keyword-search',as_type='retriever',
                input={'query':query,'candidate_count':len(self.items),'scope':self.path}) as span:
                lexical=lexical_scores(query,self.items)
                lexical_ranks=sorted(range(len(self.items)),key=lambda i:(-lexical[i],self.items[i]['id']))[:20]
                span.update(output=[{**self.items[i],'keyword_score':lexical[i]} for i in lexical_ranks])
            with self.langfuse.start_as_current_observation(name='combine-rankings-and-category-preference',
                as_type='span',input={'meaning_ids':[self.items[i]['id'] for i in dense_ranks],
                    'keyword_ids':[self.items[i]['id'] for i in lexical_ranks],
                    'preferred_kinds':sorted(self.preferred),'category_bonus':SETTINGS['category_bonus']}) as span:
                fused=defaultdict(float)
                for ranking in [dense_ranks,lexical_ranks]:
                    for rank,i in enumerate(ranking,1):fused[i]+=1/(60+rank)
                for i in fused:
                    if set(self.items[i]['categories']) & self.preferred:fused[i]+=SETTINGS['category_bonus']
                picked=sorted(fused,key=lambda i:(-fused[i],self.items[i]['id']))[:SETTINGS['candidate_limit']]
                result=[{**self.items[i],'fusion_score':fused[i]} for i in picked]
                self.queries.append(dict(query=query,candidate_ids=[p['id'] for p in result]))
                span.update(output=result)
            parent.update(output=result)
            return result

    def order(self,decision,candidates):
        with self.langfuse.start_as_current_observation(name='select-source-passages',as_type='span',
            input={'ranked_ids':decision['ranked_ids'],'maximum_starting_passages':SETTINGS['final_seeds']}) as span:
            result=super().order(decision,candidates);span.update(output=result);return result

    def expand_references(self,seeds,question):
        with self.langfuse.start_as_current_observation(name='resolve-section-links-and-apply-budget',as_type='retriever',
            input={'original_question':question,'selected_passages':seeds},
            metadata={'maximum_depth':2,'maximum_extra_passages':4,'character_budget':6000}) as span:
            passages,references=super().expand_references(seeds,question)
            span.update(output={'passages':passages,'reference_resolutions':references,
                                'unique_returned_characters':sum(len(p['text']) for p in passages)})
            return passages,references
