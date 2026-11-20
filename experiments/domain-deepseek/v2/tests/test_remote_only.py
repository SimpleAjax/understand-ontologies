import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import pipeline as p


class RemoteOnlyTests(unittest.TestCase):
    def test_identity_and_unload_do_not_touch_local_runtime(self):
        model=p.Hybrid(Path('.'),dict(spend_limit_usd=1,remote_model='deepseek/test',provider='wafer/us'))
        with patch.object(p.e.Model,'api',side_effect=AssertionError('Local runtime called')):
            self.assertEqual(model.identity()['query_model'],'deepseek/test');model.unload()

    def test_all_stages_use_openrouter_and_record_real_cost(self):
        cfg=dict(spend_limit_usd=1,remote_model='deepseek/test',provider='wafer/us',remote_max_tokens=8192,remote_output_retry=16384)
        raw=dict(choices=[dict(finish_reason='stop',message={'content':'{"ok":true}'})],usage=dict(prompt_tokens=10,completion_tokens=5,cost=.00001),provider='Wafer',id='test-generation')
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,OPENROUTER_API_KEY='fixture-only'),patch.object(p.e.Model,'call',side_effect=AssertionError('Local inference called')):
            model=p.Hybrid(Path(tmp),cfg)
            for stage in ('search','answer','extraction'):
                with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(raw).encode())) as api:
                    self.assertEqual(model.call('test','prompt',{'stage':stage},p.e.obj(ok={'type':'boolean'}),stage),{'ok':True})
                    self.assertEqual(api.call_args.args[0].full_url,'https://openrouter.ai/api/v1/chat/completions')
            self.assertAlmostEqual(sum(c['cost_usd'] for c in model.calls),.00003)


if __name__=='__main__':unittest.main()
