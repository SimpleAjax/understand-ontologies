"""Replay B/C scores with the original archived engine and scorer; no inference."""
import argparse
import json
import os
from pathlib import Path
import sys

p=argparse.ArgumentParser();p.add_argument('--capsule',type=Path,required=True);p.add_argument('--mode');p.add_argument('--no-langfuse',action='store_true');args=p.parse_args()
folder=args.capsule.resolve();code=folder/'code'
sys.path.extend(json.loads((folder/'activation.json').read_text()))
sys.path[:0]=[str(code/'experiment'),str(code/'evaluation/v1'),str(code/'shared/v1')]
os.environ['LAB_BUNDLE']=str(code)
import engine as e
cfg=e.read(code/'experiment/config.json');root=Path(os.environ['LAB_PROJECT_ROOT']);inputs=e.read(folder/'inputs.json');queries=e.read(folder/'queries.json')
for entry in inputs:e.source_text(root,entry['document'])
e.save(folder/'model.json',e.read(folder/'expected-model.json'))
reports={}
for variant,sub in [('existing',folder),('expanded',folder/'variants/expanded')]:
    e.verify_graphs(sub)
    for q in queries:
        path=sub/f"output-{q['source_index']}.json";s=e.read(path)
        s.update(seconds=None,calls=[],trace_id=None,trace_url=None,timing_scope='replay-no-model-calls');s['answer'].update(seconds=None,calls=[]);e.save(path,s)
    vectors=e.read(sub/'vector-outputs.json')
    for row in vectors.values():row['seconds']=None
    e.save(sub/'vector-outputs.json',vectors)
    e.save(sub/'config.json',dict(experiment=cfg['experiment_id']+'-'+variant,mode='replay',settings=cfg))
    reports[variant]=e.evaluate(root,sub,queries,cfg)
e.save(folder/'comparison.json',dict(existing=reports['existing']['summary'],expanded=reports['expanded']['summary'],mode='replay',new_model_calls=0,new_api_cost_usd=0))
e.save(folder/'execution-proof.json',dict(isolated_python=sys.flags.isolated,archived_engine=str(Path(e.__file__).resolve()),engine_sha256=e.sha(Path(e.__file__)),replay_driver_sha256=e.sha(Path(__file__))))
e.finish(folder/'variants/expanded','complete');e.finish(folder,'complete')
print(json.dumps(e.read(folder/'comparison.json'),indent=2))
