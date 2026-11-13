"""Source alignment and proposed-output checks; no model or benchmark required."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from rdflib import Graph, RDF

import local_ontology as ontology
from local_ontology import units, windows, TagBatch, validate_tags


class ExtractionChecks(unittest.TestCase):
    def test_source_units_preserve_unicode_and_offsets(self):
        text='Title\n\nThis agreement — ends when notice is given. '*150
        blocks=units(text)
        self.assertTrue(blocks)
        for b in blocks:
            self.assertEqual(text[b['start']:b['end']],b['text'])
            self.assertLessEqual(b['end']-b['start'],1400)

    def test_each_focus_unit_processed_once_without_other_passages(self):
        blocks=units('\n\n'.join(f'Clause {i}: this agreement terminates on notice.' for i in range(20)))
        packs=list(windows(blocks));ids=[i for focus,_ in packs for i in focus]
        self.assertEqual(sorted(ids),list(range(1,21)))
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(all(len(focus)==1 and len(context)==1 for focus,context in packs))

    def test_unknown_evidence_and_unsolicited_fact_fields_are_rejected(self):
        parsed=TagBatch(tags=[dict(a=99,b=['INITIAL_TERM'],c=[])])
        blocks=[dict(id=1,text='The term is redacted ***.')]
        accepted,rejected=validate_tags(parsed,[1],blocks)
        self.assertEqual(accepted,[]);self.assertEqual(len(rejected),1)
        with self.assertRaises(ValueError):
            TagBatch(tags=[dict(a=1,b=['INITIAL_TERM'],c=[],date_quote='2030-01-01')])

    def test_complex_condition_can_retain_original_source(self):
        parsed=TagBatch(tags=[dict(a=1,b=['TERMINATION'],c=[1])])
        blocks=[dict(id=1,text='Subject to Section 11, either party may terminate unless notice has not been served.')]
        accepted,rejected=validate_tags(parsed,[1],blocks)
        self.assertEqual(len(accepted),1);self.assertFalse(rejected)
        self.assertEqual(accepted[0]['reference_labels'],['Section 11'])

    def test_turtle_roundtrip_keeps_exact_source_and_unreviewed_status(self):
        from build_sample_ontology import DOCS
        file_path=DOCS[10]  # Previously inspected development contract only.
        path=ontology.ROOT/'data/corpus'/file_path
        blocks=units(path.read_text(encoding='utf-8'))
        doc=dict(id='TEST',file_path=file_path,local_file_path=file_path,sha256=ontology.file_hash(path))
        proposal=dict(passage_id=1,kind='INITIAL_TERM',label='Test proposal',condition_ids=[1],
                      reference_labels=[],scope_quote='',date_quote='',duration_quote='')
        with tempfile.TemporaryDirectory(dir=ontology.ROOT/'artifacts',prefix='ontology-test-') as folder:
            destination=Path(folder).resolve()
            self.assertTrue(destination.is_relative_to((ontology.ROOT/'artifacts').resolve()))
            (destination/'schema.ttl').write_bytes((ontology.ROOT/'ontology/experiments/holdout20-v1/schema.ttl').read_bytes())
            with patch.object(ontology,'RUN',destination):
                info=ontology.materialize(doc,blocks,[proposal],[],dict(model_digest='test-digest'))
                graph=Graph().parse(ontology.ROOT/info['turtle_path'])
                self.assertEqual(info['rule_count'],1)
                rule=next(graph.subjects(RDF.type,ontology.CT.Rule))
                self.assertEqual(str(graph.value(rule,ontology.META.review_status)),'UNREVIEWED')
                ontology.validate_graph(doc,ontology.ROOT/info['turtle_path'])


if __name__=='__main__':unittest.main()
