"""Entry point for the source-only domain-ontology experiment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
if '--capsule' not in sys.argv:
    raise SystemExit(subprocess.call([sys.executable,str(HERE.parents[2]/'lab.py'),'run','domain-deepseek-v3',*sys.argv[1:]]))
p=argparse.ArgumentParser();p.add_argument('--capsule',type=Path,required=True)
p.add_argument('--mode',choices=['fresh','rerun','replay','check'],required=True)
p.add_argument('--no-langfuse',action='store_true');args=p.parse_args()
folder=args.capsule.resolve()
if HERE!=folder/'code/experiment':raise ValueError('Wrong archived entry point')
sys.path.extend(json.loads((folder/'activation.json').read_text()))
sys.path[:0]=[str(HERE),str(folder/'code/evaluation/v1'),str(folder/'code/shared/v1')]
os.environ['LAB_BUNDLE']=str(folder/'code')
from pipeline import main
main(folder,args.mode,args.no_langfuse)
