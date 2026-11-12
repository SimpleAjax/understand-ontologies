"""Source-only holdout checks. This test never opens benchmark questions."""
import unittest

from rdflib import Graph

from holdout20 import FOLDER, documents, graph_retrieve, locate, validate_graph
from compare_retrieval import apply_budget


class SourceOnlyChecks(unittest.TestCase):
    def test_anchor_whitespace_and_explicit_occurrence(self):
        text='start  clause\nend start clause end'
        with self.assertRaises(ValueError):
            locate(text,'start clause','end')
        self.assertEqual(locate(text,('start clause',0),'end'),(0,13))

    def test_all_twenty_return_only_their_own_original_text(self):
        graph=validate_graph()
        docs=documents()
        texts={d['file_path']:t for d,t in docs.values()}
        for id,(doc,_) in docs.items():
            candidates,_=graph_retrieve(graph,id,texts)
            self.assertTrue(candidates,id)
            self.assertEqual({p['file_path'] for p in candidates},{doc['file_path']})
            returned=apply_budget(candidates,texts,6000)
            self.assertLessEqual(sum(len(p['text']) for p in returned),6000)
            positions=[i for p in returned for i in range(*p['span'])]
            self.assertEqual(len(positions),len(set(positions)))


if __name__=='__main__':
    unittest.main()
