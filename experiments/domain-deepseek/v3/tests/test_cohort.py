import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import engine as e
from pipeline import parse_content


class CohortTests(unittest.TestCase):
    def test_preserve_literal_tab_and_reject_other_invalid_json(self):
        content='{"text":"contract\tquote"}'
        with self.assertRaises(json.JSONDecodeError):json.loads(content)
        parsed,recovered=parse_content(content,e.obj(text=e.string(50)))
        self.assertEqual(parsed['text'],'contract\tquote');self.assertTrue(recovered)
        with self.assertRaises(json.JSONDecodeError):parse_content('{"text":}',e.obj(text=e.string(50)))
        with self.assertRaises(ValueError):parse_content('{"text":7}',e.obj(text=e.string(50)))

    def test_all_topics_and_questions_are_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'run';folder.mkdir();(root/'experiments/cuad-100').mkdir(parents=True)
            tests=[dict(source_index=i,query=q,snippets=[{'file_path':'doc'}]) for i,q in [(1,'expiry'),(2,'audit'),(3,'governing law')]]
            e.save(root/'experiments/cuad-100/questions.json',{'tests':tests})
            with patch.object(e,'verify_graphs',return_value={}):
                queries=e.select_queries(root,folder,[{'document':{'id':'D','file_path':'doc'}}],dict(query_seed=20261115,questions_per_agreement='all'))
            self.assertEqual([q['source_index'] for q in queries],[1,2,3])

    def test_selected_documents_exclude_previous_ten(self):
        root=HERE.parents[2]
        current=e.read(root/'datasets/domain-random20/source-manifest.json')
        old=e.read(root/'datasets/domain-10/source-manifest.json')
        self.assertEqual(len({d['id'] for d in current['documents']}),20)
        self.assertFalse({d['id'] for d in current['documents']} & {d['id'] for d in old['documents']})

    def test_model_prompts_and_limits_are_unchanged(self):
        previous=HERE.parent/'v2';current=e.read(HERE/'config.json');old=e.read(previous/'config.json')
        for key in ['model','provider','extraction_batch_characters','unit_characters','max_provisions_per_batch','agent_rounds','inspect_limit','neighbor_limit','character_budget']:
            self.assertEqual(current[key],old[key],key)
        for file in ['prompt.txt','relations-prompt.txt','expanded-prompt.txt','search-prompt.txt','answer-prompt.txt']:
            self.assertEqual((HERE/file).read_bytes(),(previous/file).read_bytes(),file)

if __name__=='__main__':unittest.main()
