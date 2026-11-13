import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from retrieval_v2 import EvidenceSearch,LocalSelector
from langfuse_retrieval import TracedSearch,TracedSelector,selector_payload,safe_mask,hosted_estimate


class Observation:
    def __init__(self,record):self.record=record
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def update(self,**kwargs):self.record.update(kwargs)


class Client:
    def __init__(self):self.records=[]
    def start_as_current_observation(self,**kwargs):
        self.records.append(kwargs);return Observation(kwargs)


class Embedding:
    def encode(self,*args,**kwargs):return np.array([1.,0.])


class LangfuseTests(unittest.TestCase):
    def test_tracing_keeps_identical_search_ranking(self):
        items=[dict(id='a',file_path='doc',span=[0,10],text='term renew',categories=['INITIAL_TERM']),
               dict(id='b',file_path='doc',span=[11,24],text='renewal dates',categories=[])]
        vectors={'a':np.array([.7,.3]),'b':np.array([1.,0.])}
        args=('doc','term renew\nrenewal dates',items,vectors,Embedding(),['INITIAL_TERM'],None)
        plain=EvidenceSearch(*args);client=Client();traced=TracedSearch(*args,langfuse=client)
        self.assertEqual(plain.collect('renewal dates'),traced.collect('renewal dates'))
        names={x['name'] for x in client.records}
        self.assertTrue({'meaning-search','keyword-search','combine-rankings-and-category-preference'}<=names)

    def test_recorded_prompt_matches_real_request_and_cache_cost_is_zero(self):
        text='Contract term is annual.'
        items=[dict(id='a',file_path='doc',span=[0,len(text)],text=text,categories=['INITIAL_TERM'])]
        raw={'done_reason':'stop','message':{'content':json.dumps(dict(ranked_ids=['a'],evidence_sufficient=True,missing_queries=[]))},
             'prompt_eval_count':100,'eval_count':20}
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);base=LocalSelector(cache,'digest')
            with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
                base.choose('term?',items,[],text,[])
            expected=selector_payload('term?',items,[],text,[])
            fingerprint=hashlib.sha256(('digest'+json.dumps(expected,sort_keys=True)).encode()).hexdigest()
            self.assertEqual(base.calls[0]['cache_key'],fingerprint)
            client=Client();traced=TracedSelector(cache,'digest',client)
            with patch('urllib.request.urlopen',side_effect=AssertionError('cache must not call model')):
                traced.choose('term?',items,[],text,[])
            generation=client.records[0]
            self.assertEqual(generation['input']['messages'],expected['messages'])
            self.assertEqual(generation['usage_details'],{'input':0,'output':0})
            self.assertEqual(generation['cost_details']['total'],0)
            self.assertEqual(generation['metadata']['source_model_usage'],{'input':100,'output':20})
            self.assertEqual(traced.hosted_equivalent_usd,0)

    def test_secret_mask_preserves_evidence(self):
        masked=safe_mask(data={'password':'hidden','nested':[{'text':'evidence','api_key':'hidden'}],
                               'note':'sk-lf-not-a-real-key'})
        self.assertEqual(masked['password'],'[REDACTED]')
        self.assertEqual(masked['nested'][0]['text'],'evidence')
        self.assertNotIn('sk-lf-',masked['note'])

    def test_hosted_estimate_is_separate_calculation(self):
        self.assertAlmostEqual(hosted_estimate(1_000_000,1_000_000),1.2)


if __name__=='__main__':unittest.main()
