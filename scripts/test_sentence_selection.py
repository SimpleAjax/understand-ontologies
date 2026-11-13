import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentence_selection import prepare_input,materialize,expand_context,select


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.text='Background remains stored.\n\nPayment is monthly. Renewal lasts one year. Unless notice is given, renewal happens.\n\nAnother section.'
        self.a=self.text.index('Payment');self.b=self.text.index('\n\nAnother')
        self.passages=[dict(file_path='contract',span=[self.a,self.b],text=self.text[self.a:self.b])]

    def test_full_paragraph_and_neighbors_visible_but_not_eligible(self):
        prepared,path=prepare_input('renewal?',self.passages,self.text)
        self.assertEqual(path,'contract')
        self.assertEqual(len(prepared['reading_context']),3)
        self.assertEqual(''.join(x['text'] for x in prepared['eligible_units']),self.passages[0]['text'])
        self.assertNotIn('Background',''.join(x['text'] for x in prepared['eligible_units']))

    def test_ids_copy_original_conditions_without_rewriting(self):
        prepared,path=prepare_input('renewal?',self.passages,self.text)
        ids=[x['id'] for x in prepared['eligible_units'] if 'Renewal' in x['text'] or 'Unless' in x['text']]
        output=materialize(ids,prepared,path,self.text)
        self.assertTrue(any('Unless' in x['text'] for x in output))
        self.assertTrue(all(self.text[x['span'][0]:x['span'][1]]==x['text'] for x in output))
        with self.assertRaises(ValueError):materialize(['unknown'],prepared,path,self.text)

    def test_surrounding_context_can_be_fetched_later(self):
        prepared,path=prepare_input('renewal?',self.passages,self.text)
        selected=materialize([prepared['eligible_units'][1]['id']],prepared,path,self.text)
        expanded=expand_context(selected,self.text,500)
        self.assertIn('Background',expanded[0]['text'])
        self.assertIn('Unless',expanded[0]['text'])

    def test_model_context_request_keeps_original_evidence(self):
        raw={'done_reason':'stop','message':{'content':json.dumps({'selected_ids':['S002'],'needs_more_context':True,'note':'Need another definition.'})},'prompt_eval_count':100,'eval_count':10}
        with tempfile.TemporaryDirectory() as directory:
            with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())):
                result=select('renewal?',self.passages,self.text,'digest',Path(directory))
        self.assertEqual(result['output'],self.passages)
        self.assertEqual(result['status'],'retained-original-needs-context')


class ExperimentTests(unittest.TestCase):
    def test_new_runs_never_overwrite_and_capture_inputs(self):
        import experiment_lab
        with tempfile.TemporaryDirectory() as directory,patch.object(experiment_lab,'RUNS',Path(directory)):
            a=experiment_lab.new_run('test',{'mode':'test'},[])
            b=experiment_lab.new_run('test',{'mode':'test'},[])
            self.assertNotEqual(a,b)
            self.assertTrue((a/'inputs.json').exists());self.assertTrue((a/'code/sentence_selection.py').exists())
            experiment_lab.finish(a)
            lock=json.loads((a/'run-lock.json').read_text())
            self.assertIn('config.json',lock['files'])

    def test_incomplete_run_cannot_be_replayed(self):
        import experiment_lab
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/'manifest.json').write_text(json.dumps({'status':'failed'}))
            with self.assertRaisesRegex(ValueError,'complete'):experiment_lab.replay(folder)

    def test_comparison_rejects_different_source_versions(self):
        import experiment_lab
        with tempfile.TemporaryDirectory() as directory:
            folders=[Path(directory)/'a',Path(directory)/'b']
            result={'question_sha256':'same','results':[{'source_index':1,'question':'q','document_id':'d'}]}
            for folder,digest in zip(folders,['first','changed']):
                folder.mkdir();(folder/'results.json').write_text(json.dumps(result))
                (folder/'inputs.json').write_text(json.dumps([{'sample':{'source_index':1},'document':{'sha256':digest}}]))
            with self.assertRaisesRegex(ValueError,'versions'):experiment_lab.compare(*folders)


if __name__=='__main__':unittest.main()
