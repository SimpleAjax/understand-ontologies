"""Reproduce the saved graph-search failure without inference or paid requests."""
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'artifacts/experiment-runs/domain-deepseek-v1/20261115T095703165091Z-08ab55'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
os.environ['LAB_PROJECT_ROOT']=str(ROOT)
sys.path[:0]=[str(RUN/'code/experiment'),str(RUN/'code/shared/v1')]
spec=importlib.util.spec_from_file_location('archived_domain_engine',RUN/'code/experiment/engine.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
cfg=read(RUN/'code/experiment/config.json')
reproductions=[]
for source,doc,rule in [(1456,'C082','R0008'),(1028,'C087','R0015')]:
    saved=read(RUN/f'output-{source}.json');graph=e.Graph().parse(RUN/'graphs'/f'{doc}.ttl')
    class RecordedChoice:
        def __init__(self):self.calls=[]
        def call(self,*args,**kwargs):self.calls.append({'stage':'search'});return saved['decision']
    reproduced=e.search_graph(saved['sample']['question'],graph,cfg,RecordedChoice())
    assert reproduced['stop']=='empty_inspection' and reproduced['output']==[] and reproduced['tool_steps']==[]
    # Exact same graph contains the necessary source evidence when inspected directly.
    tool=e.GraphTools(graph,cfg);packet=tool.inspect([rule])
    row=next(r for r in read(RUN/'results.json')['results'] if r['source_index']==source)
    assert all(any(p['span'][0]<=g['span'][0] and p['span'][1]>=g['span'][1] for p in tool.revealed.values()) for g in row['scored']['expected'])
    directory=next(r for r in tool.directory() if r['id']==rule)
    record=next(r for r in read(RUN/'graphs'/f'{doc}.json')['provisions'] if r['id']==rule)
    reproductions.append(dict(source_index=source,stop=reproduced['stop'],inspections=0,required_rule=rule,directory=directory,meaning_hidden_from_directory=record['meaning'],direct_inspection_recovers_expected_evidence=True))

omissions=[]
for source,doc,pid in [(1382,'C028','P0111'),(1455,'C081','P0059')]:
    record=read(RUN/'graphs'/f'{doc}.json')
    assert not any(pid in r['sources'] or any(pid in c['sources'] for c in r['conditions']) for r in record['provisions'])
    for request in (RUN/'responses/extraction').glob('*-request.json'):
        data=json.loads(read(request)['messages'][1]['content'])
        if data['document']==doc and pid in {p['id'] for p in data['passages']}:
            response=read(request.with_name(request.name.replace('-request','')))
            output=json.loads(response['choices'][0]['message']['content'])
            assert len(output['provisions'])==cfg['max_provisions_per_batch']==14
            omissions.append(dict(source_index=source,passage_id=pid,source_units_in_batch=len(data['passages']),provisions_returned=14,output_cap=14,omitted_from_model=True,causal_note='Saturation and omission observed together; increasing the cap has not been tested.'))
assert len(omissions)==2
result=dict(saved_failures_reproduced=True,new_model_calls=0,early_abstention=reproductions,extraction_omissions=omissions)
target=ROOT/'artifacts/experiment-comparisons/deepseek-rca-reproduction-20261115.json'
target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
