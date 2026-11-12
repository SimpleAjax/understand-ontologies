"""UI adapter checks for the new batch without model inference."""
import unittest

from holdout_workbench import HoldoutWorkbench
from holdout20 import verify_seal


class BatchAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch = HoldoutWorkbench()

    def test_exposes_all_evaluated_questions_and_twenty_graph_documents(self):
        self.assertEqual(len(self.batch.questions),31)
        self.assertEqual(len(self.batch.documents),20)
        self.assertEqual(len({r['document_id'] for r in self.batch.questions.values()}),16)

    def test_every_supported_question_has_displayable_graph_paths(self):
        for row in self.batch.questions.values():
            details=self.batch.details(row['document_id'])
            self.assertTrue(details['rules'])
            self.assertTrue(any(p['relationship']=='supported_by' for p in details['paths']))
            self.assertEqual(details['graph_sha256'],self.batch.graph_hash)

    def test_first_evaluation_and_graph_are_still_sealed(self):
        verify_seal()


if __name__=='__main__':
    unittest.main()
