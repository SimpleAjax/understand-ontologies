import importlib.util
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import pipeline as p


class BudgetTests(unittest.TestCase):
    def test_concurrent_reservations_cannot_exceed_cap(self):
        b=p.Budget(.1);b.reserve(.08)
        with self.assertRaises(RuntimeError):b.reserve(.03)
        b.settle(.08,dict(cost_usd=.02));b.reserve(.07)

    def test_settlement_uses_reported_cost(self):
        b=p.Budget(1);b.reserve(.1);b.settle(.1,dict(cost_usd=.03))
        self.assertAlmostEqual(b.total,.03);self.assertAlmostEqual(b.reserved,0)

class ExpansionTests(unittest.TestCase):
    def record(self):
        def rule(id,action):return dict(id=id,kind='Permission',actor='Party',actor_kind='PartyRole',action=action,target='Agreement',target_kind='Agreement',meaning=action,sources=['P1'],conditions=[],references=[])
        return dict(document=dict(id='T',file_path='t',sha256='hash'),passages=[dict(id='P1',span=[0,36],text='Renewal requires prior written notice.')],provisions=[rule('R1','renew'),rule('R2','provide notice')],links=[],uncertainties=[])
    def test_additive_expansion_preserves_base_nodes_and_rejects_bad_quote(self):
        r=self.record();base=p.e.to_graph(r)
        class Fake:
            def call(self,*args):return dict(links=[dict(source='R2',relation='notice_for',target='R1',sources=['P1'],quote='prior written notice',explanation='notice required'),dict(source='R1',relation='amends',target='R2',sources=['P1'],quote='invented quote',explanation='unsupported')],uncertainties=[])
        graph,record=p.expand(r,base,Fake())
        self.assertTrue(set(base)<=set(graph));self.assertTrue(record['expanded_links'][0]['traversable']);self.assertFalse(record['expanded_links'][1]['traversable'])
        self.assertEqual(record['provisions'],r['provisions'])
    def test_query_calls_keep_the_original_local_model(self):
        with patch.object(p.e.Model,'call',return_value={'local':True}) as call:
            model=p.Hybrid(Path('.'),dict(spend_limit_usd=1))
            self.assertEqual(model.call('plan','prompt',{}, {},'search'),{'local':True})
            call.assert_called_once()

if __name__=='__main__':unittest.main()
