"""Inspect graph-expansion contribution from saved steps, without model calls.

This is an evidence-path diagnostic, not a counterfactual rerun of the agent.
"""
import argparse
import json
from pathlib import Path
from rdflib import Graph, Namespace

D=Namespace('https://cimulink.local/ontology/domain-contract/1#')


def analyze(folder):
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    results=[]
    for query in read(folder/'queries.json'):
        saved=read(folder/f"output-{query['source_index']}.json")
        graph=Graph().parse(folder/'graphs'/f"{query['document_id']}.ttl")
        rules={str(n).split('#')[-1]:n for n in graph.objects(None,D.hasProvision)}
        seeds=set();expanded=set();paths=[]
        for step in saved['tool_steps']:
            for id in step['request']:
                n=rules[id];seeds.update(str(p).split('#')[-1] for p in graph.objects(n,D.supportedBy))
                for rel in ('condition','exception','time','scope'):
                    for condition in graph.objects(n,D[rel]):seeds.update(str(p).split('#')[-1] for p in graph.objects(condition,D.supportedBy))
            for provision in step['response']['provisions']:expanded.update(p['id'] for p in provision['passages'])
            paths.extend(step['response']['paths'])
        extra=expanded-seeds
        results.append(dict(source_index=query['source_index'],document_id=query['document_id'],explicit_paths=paths,
                            passages_from_seed_provisions=sorted(seeds),additional_passages_from_links=sorted(extra),
                            selected_additional_passages=sorted(extra & set(saved['selected_ids']))))
    return dict(note='Saved-step path diagnostic only. Same selected seeds; no new ranking/inference and no causal recall claim.',results=results,
                questions_with_added_evidence=sum(bool(r['additional_passages_from_links']) for r in results),
                questions_selecting_added_evidence=sum(bool(r['selected_additional_passages']) for r in results))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_folder',type=Path);args=p.parse_args()
    report=analyze(args.run_folder.resolve())
    # Keep diagnostics separate from the sealed execution folder.
    target=args.run_folder.resolve().parents[2]/'experiment-comparisons'/('domain-paths-'+args.run_folder.name+'.json')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(target)
