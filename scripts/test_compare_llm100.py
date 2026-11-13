import unittest

import numpy as np
from rdflib import Graph, Literal, RDF

from compare_llm100 import CT, EX, catalogue, graph_candidates, rank_passages, topic
from compare_retrieval import apply_budget


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.g=Graph()
        for id,start,text in [('p1',0,'term'),('p2',4,'renew'),('p3',9,'exception')]:
            p=EX[id]
            for predicate,value in [(RDF.type,CT.SourcePassage),(CT.source_path,Literal('doc')),
                                    (CT.start_char,Literal(start)),(CT.end_char,Literal(start+len(text))),
                                    (CT.exact_text,Literal(text))]:
                self.g.add((p,predicate,value))
        for rule,kind,p in [('r1','INITIAL_TERM','p1'),('r2','AUTOMATIC_RENEWAL','p2')]:
            self.g.add((EX.C001,CT.has_rule,EX[rule]))
            self.g.add((EX[rule],CT.kind,Literal(kind)))
            self.g.add((EX[rule],CT.supported_by,EX[p]))
        self.items=catalogue(self.g)
        self.vectors={str(EX.p1):np.array([.5,.5]),str(EX.p2):np.array([1.,0.]),str(EX.p3):np.array([0.,1.])}
        self.query=np.array([1.,0.])

    def test_topic_uses_question_and_rejects_other_tasks(self):
        self.assertEqual(topic('What is the expiration date?'),'expiry')
        self.assertEqual(topic('What is the notice period required to terminate the renewal?'),'renewal_notice')
        self.assertIsNone(topic('What is the governing law?'))

    def test_kind_filter_and_real_link_traversal(self):
        self.g.add((EX.r1,CT.subject_to,EX.condition))
        self.g.add((EX.condition,CT.supported_by,EX.p3))
        raw,seeds,_=graph_candidates(self.g,'C001','expiry',self.items,self.vectors,self.query)
        self.assertEqual([p['evidence_id'] for p in seeds],[str(EX.p1)])
        self.assertEqual([p['evidence_id'] for p in raw],[str(EX.p1),str(EX.p3)])
        self.assertEqual(rank_passages(self.items,self.vectors,self.query)[0]['evidence_id'],str(EX.p2))

    def test_no_fallback_for_empty_graph(self):
        raw,seeds,_=graph_candidates(self.g,'C002','expiry',self.items,self.vectors,self.query)
        self.assertEqual((raw,seeds),([],[]))

    def test_budget_removes_overlap_and_caps_unique_chars(self):
        text='abcdefghijklmnop'
        candidates=[dict(file_path='doc',span=[0,10],text=text[:10]),
                    dict(file_path='doc',span=[5,16],text=text[5:])]
        got=apply_budget(candidates,{'doc':text},12)
        self.assertEqual([p['span'] for p in got],[[0,10],[10,12]])


if __name__=='__main__':
    unittest.main()
