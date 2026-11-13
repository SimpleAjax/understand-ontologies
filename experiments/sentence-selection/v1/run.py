"""Run this version through a frozen capsule; direct execution delegates to lab.py."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
if '--capsule' not in sys.argv:
    root=HERE.parents[2]
    cfg=json.loads((HERE/'config.json').read_text())
    raise SystemExit(subprocess.call([sys.executable,str(root/'lab.py'),'run',cfg['experiment_id'],*sys.argv[1:]]))
p=argparse.ArgumentParser()
p.add_argument('--capsule',type=Path,required=True)
p.add_argument('--mode',choices=['fresh','rerun','replay','check'],required=True)
p.add_argument('--no-langfuse',action='store_true')
args=p.parse_args()
folder=args.capsule.resolve()
if HERE!=folder/'code/experiment':raise ValueError('Wrong capsule entrypoint')
cfg=json.loads((HERE/'config.json').read_text())
# Explicit package locations; no PYTHONPATH, user .pth files or live scripts.
sys.path.extend(json.loads((folder/'activation.json').read_text()))
sys.path[:0]=[str(folder/'code/shared'/cfg['shared_version']),str(folder/'code/evaluation'/cfg['evaluation_version'])]
os.environ['LAB_DATASET']=str(folder/'code/datasets'/cfg['dataset'])
os.environ['LAB_BUNDLE']=str(folder/'code')
from worker import main
main(folder,args.mode,args.no_langfuse)
