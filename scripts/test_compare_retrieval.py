"""Focused checks for evidence budgeting and graph traversal; no model inference."""
import unittest

from compare_retrieval import OntologySearch, apply_budget


class BudgetTests(unittest.TestCase):
    def test_overlapping_ranked_chunks_do_not_spend_budget_twice(self):
        text = 'abcdefghijklmnop'
        candidates = [{'file_path': 'a', 'span': [a,b], 'text': text[a:b]}
                      for a,b in [(4,10), (0,8), (8,16), (4,10)]]
        result = apply_budget(candidates, {'a': text}, 12)
        positions = [i for p in result for i in range(*p['span'])]
        self.assertEqual(len(positions), 12)
        self.assertEqual(len(set(positions)), 12)
        self.assertEqual(result[0]['span'], [4,10])
        self.assertEqual(result[-1]['span'], [10,12])

    def test_separate_documents_keep_their_own_ranges(self):
        rows = [{'file_path': p, 'span': [0,4], 'text': 'abcd'} for p in ['a','b']]
        result = apply_budget(rows, {'a':'abcd','b':'abcd'}, 8)
        self.assertEqual(len(result), 2)

    def test_wrong_source_text_is_rejected(self):
        with self.assertRaises(ValueError):
            apply_budget([{'file_path':'a','span':[0,4],'text':'wrong'}], {'a':'abcd'}, 4)


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.search = OntologySearch()

    def test_incoming_qualifications_retrieve_renewal_and_continuation(self):
        passages, details = self.search.retrieve(10)
        self.assertEqual({r['id'] for r in details['rules']},
                         {'InitialTerm10','Renewal10','Continuation10'})
        self.assertEqual({p['evidence_id'] for p in passages}, {'P10a','P10b'})
        self.assertTrue(any(p['relationship']=='qualifies' for p in details['paths']))

    def test_redaction_and_local_payment_exclusion_are_preserved(self):
        _, details = self.search.retrieve(268)
        initial = next(r for r in details['rules'] if r['id']=='InitialTerm268')
        self.assertIn({'field':'duration_status','value':'REDACTED'}, initial['fields'])
        breach = next(r for r in details['rules'] if r['id']=='BreachTermination268')
        self.assertTrue(any('not a global exclusion' in c for c in breach['conditions']))
        self.assertTrue(any(r['status']=='UNRESOLVED' for r in details['references']))


if __name__ == '__main__':
    unittest.main()
