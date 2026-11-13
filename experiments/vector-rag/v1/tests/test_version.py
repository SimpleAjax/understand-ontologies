import json
from pathlib import Path
import unittest
class VersionContractTests(unittest.TestCase):
    def test_version_has_complete_runnable_contract(self):
        here=Path(__file__).resolve().parents[1]
        config=json.loads((here/'config.json').read_text())
        self.assertEqual(config['sample_cap'],5)
        self.assertEqual(config['character_budget'],6000)
        lock=json.loads((here/'environment.lock.json').read_text())
        self.assertIn('sentence-transformers',lock['packages'])
        for name in ['run.py','pipeline.py','prompt.txt','requirements.lock']:
            self.assertTrue((here/name).is_file(),name)
