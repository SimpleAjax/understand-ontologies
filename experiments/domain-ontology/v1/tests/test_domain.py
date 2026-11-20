import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'shared/v1')]
import os
os.environ['LAB_PROJECT_ROOT']=str(ROOT)
spec=importlib.util.spec_from_file_location('domain_pipeline',HERE/'pipeline.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
    text='Supplier may sell. Unless consent is withheld. Orders remain after termination.'
    passages=[dict(id='P0001',span=[0,18],text=text[:18]),dict(id='P0002',span=[18,len(text)],text=text[18:])]
    rules=[dict(id='R0001',kind='Permission',actor='Supplier',actor_kind='PartyRole',action='sell',target='Products',target_kind='Product',meaning='may sell',sources=['P0001'],conditions=[],references=[]),dict(id='R0002',kind='Permission',actor='Supplier',actor_kind='PartyRole',action='fulfil prior orders',target='Orders',target_kind='GenericScope',meaning='orders after termination',sources=['P0002'],conditions=[dict(text='consent condition',kind='condition',sources=['P0002'])],references=[])]
    return text,dict(document=dict(id='TEST',file_path='contract',sha256='test'),passages=passages,provisions=rules,links=[dict(source='R0002',relation='qualifies',target='R0001',sources=['P0002'],traversable=True)],uncertainties=[])


class DomainTests(unittest.TestCase):
    def test_compact_relation_context_preserves_all_source_quotes(self):
        text,record=fixture()
        records=[dict(record['provisions'][0],id=f'R{i:04}',actor='x'*1000,target='y'*1000) for i in range(30)]
        data=m.relation_context(records,record['passages'])
        self.assertEqual([p['text'] for p in data['passages']],[p['text'] for p in record['passages']])
        self.assertEqual(len(data['provisions']),30)
        self.assertNotIn('actor',data['provisions'][0])

    def test_unsupported_cross_provision_link_stays_review_only(self):
        _,record=fixture();m.screen_links(record)
        self.assertFalse(record['links'][0]['traversable'])
        graph=m.to_graph(record)
        self.assertFalse(list(graph.triples((None,m.D.qualifies,None))))

    def test_same_passage_with_explicit_qualification_cue_can_be_traversed(self):
        _,record=fixture();record['provisions'][0]['sources']=['P0002'];m.screen_links(record)
        self.assertTrue(record['links'][0]['traversable'])
        self.assertTrue(list(m.to_graph(record).triples((None,m.D.qualifies,None))))

    def test_truncated_generation_is_saved_and_retried_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg=dict(model='test',model_digest='test',options=dict(num_predict=512))
            model=m.Model(Path(tmp),cfg)
            calls=[]
            def api(path,payload):
                calls.append(payload['options']['num_predict'])
                return dict(done_reason='length' if len(calls)==1 else 'stop',message={'content':'{"ok":true}'},prompt_eval_count=10,eval_count=20)
            model.api=api
            result=model.call('test','prompt',{},m.obj(ok={'type':'boolean'}),'test')
            self.assertEqual(result,{'ok':True});self.assertEqual(calls,[512,4096])
            self.assertEqual(len(model.calls),2)

    def test_persistent_truncation_stops_at_bounded_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=m.Model(Path(tmp),dict(model='test',model_digest='test',options=dict(num_predict=4096)))
            model.api=lambda path,payload:dict(done_reason='length',message={'content':'{'})
            with self.assertRaisesRegex(ValueError,'bounded retry'):model.call('test','prompt',{},m.obj(ok={'type':'boolean'}),'test')

    def test_units_preserve_every_nonwhitespace_character(self):
        text='First sentence. '+('A long term and condition; '*90)+'\n\nFinal clause.'
        units=m.units(text,700);covered=set()
        for p in units:
            a,b=p['span'];self.assertEqual(p['text'],text[a:b]);covered.update(range(a,b))
        self.assertTrue(all(i in covered for i,c in enumerate(text) if not c.isspace()))

    def test_graph_inspection_follows_typed_links_and_conditions(self):
        text,record=fixture();m.validate_record(record,text)
        tool=m.GraphTools(m.to_graph(record),dict(inspect_limit=5,neighbor_limit=6))
        result=tool.inspect(['R0001'])
        self.assertEqual(set(tool.revealed),{'P0001','P0002'})
        self.assertEqual(result['paths'],[['R0002','qualifies','R0001']])

    def test_unrevealed_and_outside_agreement_ids_rejected(self):
        _,record=fixture();tool=m.GraphTools(m.to_graph(record),dict(inspect_limit=5,neighbor_limit=6))
        with self.assertRaises(ValueError):m.evidence_output(tool,['P0002'],6000)
        with self.assertRaises(ValueError):tool.inspect(['OTHER:R0001'])

    def test_evidence_budget_keeps_exact_text(self):
        text,record=fixture();tool=m.GraphTools(m.to_graph(record),dict(inspect_limit=5,neighbor_limit=6));tool.inspect(['R0001'])
        passages=m.evidence_output(tool,['P0001','P0002'],25)
        self.assertEqual(sum(len(p['text']) for p in passages),25)
        for p in passages:self.assertEqual(p['text'],text[slice(*p['span'])])

    def test_file_guard_blocks_benchmark_and_raw_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'data/corpus').mkdir(parents=True);p=root/'data/corpus/contract';p.write_text('text')
            with m.access_guard(root,'graph-search'):
                with self.assertRaises(RuntimeError):p.read_text()
                with self.assertRaises(RuntimeError):(root/'questions.json').read_text()
            with m.access_guard(root,'extraction'):
                self.assertEqual(p.read_text(),'text')

    def test_unknown_model_id_rejected(self):
        with self.assertRaises(ValueError):m.validate_shape(['unknown'],m.array(m.enum(['R0001']),5))

    def test_self_links_are_preserved_for_review_but_not_traversable(self):
        text,record=fixture();record['links'][0]['target']='R0002'
        m.validate_record(record,text);m.screen_links(record)
        self.assertFalse(record['links'][0]['traversable'])


if __name__=='__main__':unittest.main()
