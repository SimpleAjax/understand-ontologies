import tempfile
import unittest
from pathlib import Path

import numpy as np

from retrieval_v2 import EvidenceSearch, LocalSelector, SectionIndex, SETTINGS, identity, embedding_array


class FakeEmbedding:
    def encode(self,*args,**kwargs):return np.array([1.,0.])


class FakeSelector:
    def __init__(self):self.calls=[]
    def choose(self,query,candidates,current,text,previous_queries):
        self.calls.append(dict(previous_queries=previous_queries))
        return dict(ranked_ids=[candidates[0]['id']],evidence_sufficient=False,
                    missing_queries=['missing notice period'])


def item(text,a,b,category=None):
    return dict(id=identity('doc',[a,b]),file_path='doc',span=[a,b],text=text[a:b],
                categories=[category] if category else [],origin='test')


class RetrievalTests(unittest.TestCase):
    def test_pgvector_wrapper_becomes_numeric_array(self):
        from pgvector import Vector
        vector=embedding_array(Vector([.1]*384))
        self.assertEqual(vector.shape,(384,))
        self.assertAlmostEqual(float(vector@np.ones(384)),38.4,places=4)
        with self.assertRaises(ValueError):embedding_array([1,2])

    def test_section_resolution_and_ambiguity(self):
        index=SectionIndex('1. Term\nSee Section 9.\n9. Notice\nThirty days.\n')
        ref=index.resolve('9')
        self.assertEqual(ref['status'],'resolved')
        self.assertTrue(index.text[ref['span'][0]:ref['span'][1]].startswith('9. Notice'))
        self.assertEqual(SectionIndex('9. Notice\nBody\n9. Notice\nAgain\n').resolve('9')['status'],'ambiguous')
        self.assertEqual(index.resolve('12')['status'],'unresolved')

    def test_calendar_date_is_not_a_heading(self):
        index=SectionIndex('1.1.2020 - 31.12.2020: Prices\n9. Notice\n')
        self.assertNotIn('1.1',index.entries)

    def test_soft_categories_do_not_drop_uncategorized_evidence(self):
        text='renewal notice\nother text'
        a=item(text,0,14);b=item(text,15,len(text),'INITIAL_TERM')
        engine=EvidenceSearch('doc',text,[a,b],{a['id']:np.array([1.,0.]),b['id']:np.array([0.,1.])},
                              FakeEmbedding(),['INITIAL_TERM'],FakeSelector())
        candidates=engine.collect('renewal notice')
        self.assertIn(a['id'],[p['id'] for p in candidates])

    def test_two_section_hops_have_exact_evidence(self):
        text='1. Term\nSee Section 9.\n9. Ending\nSee Section 12.\n12. Notice\nThirty days.\n'
        a=item(text,0,text.index('9. Ending'))
        engine=EvidenceSearch('doc',text,[a],{a['id']:np.array([1.,0.])},FakeEmbedding(),[],FakeSelector())
        result,trace=engine.expand_references([a],'termination notice')
        self.assertEqual({r['reference'] for r in trace},{'9','12'})
        self.assertEqual(len(result),3)
        self.assertTrue(all(text[p['span'][0]:p['span'][1]]==p['text'] for p in result))
        self.assertLessEqual(sum(len(p['text']) for p in result),6000)

    def test_missing_reference_does_not_invent_evidence(self):
        text='1. Term\nSee Section 88.\n';a=item(text,0,len(text))
        engine=EvidenceSearch('doc',text,[a],{a['id']:np.array([1.,0.])},FakeEmbedding(),[],FakeSelector())
        got,trace=engine.expand_references([a],'term')
        self.assertEqual(len(got),1);self.assertEqual(trace[0]['status'],'unresolved')

    def test_repeated_search_stops_without_a_full_benchmark(self):
        text='1. Term\nRenewal is annual.';a=item(text,0,len(text))
        selector=FakeSelector()
        engine=EvidenceSearch('doc',text,[a],{a['id']:np.array([1.,0.])},FakeEmbedding(),[],selector)
        got=engine.run('renewal?')
        self.assertEqual(got['stop_reason'],'no_evidence_change')
        self.assertEqual(len(got['queries']),2)
        self.assertLessEqual(len(got['rounds']),1+SETTINGS['max_followup_rounds'])


if __name__=='__main__':unittest.main()
