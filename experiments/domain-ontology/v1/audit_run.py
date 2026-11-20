"""Independent local audit of a completed domain-ontology run, no model calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from rdflib import Graph, Namespace, RDF

D=Namespace('https://cimulink.local/ontology/domain-contract/1#')


def audit(folder,root):
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert read(folder/'manifest.json')['status']=='complete'
    for name,digest in read(folder/'run-lock.json')['files'].items():assert sha(folder/name)==digest,name
    for name,digest in read(folder/'bundle-lock.json')['files'].items():assert sha(folder/'code'/name)==digest,name
    lock=read(folder/'graph-lock.json')
    for name,digest in lock['files'].items():assert sha(folder/name)==digest,name
    inputs=read(folder/'inputs.json');graphs=[]
    for entry in inputs:
        doc=entry['document'];source=root/'data/corpus'/doc['local_file_path']
        assert sha(source)==doc['sha256'];text=source.read_text(encoding='utf-8')
        g=Graph().parse(folder/'graphs'/f"{doc['id']}.ttl")
        coverage=set()
        for p in g.subjects(D.exactText,None):
            a,b=int(g.value(p,D.startChar)),int(g.value(p,D.endChar))
            assert text[a:b]==str(g.value(p,D.exactText));coverage.update(range(a,b))
        assert all(i in coverage for i,c in enumerate(text) if not c.isspace())
        records=read(folder/'graphs'/f"{doc['id']}.json")
        assert len(records['provisions'])==len(list(g.objects(None,D.hasProvision)))
        for proposal in records['links']:
            base='https://cimulink.local/agreements/domain10/'+doc['id']+'#'
            from rdflib import URIRef
            triple=(URIRef(base+proposal['source']),D[proposal['relation']],URIRef(base+proposal['target']))
            assert (triple in g)==proposal['traversable']
        graphs.append(dict(document_id=doc['id'],provisions=len(records['provisions']),proposed_links=len(records['links']),traversable_links=sum(p['traversable'] for p in records['links']),source_text_matches=True))
    queries=read(folder/'queries.json');outputs=[]
    for q in queries:
        saved=read(folder/f"output-{q['source_index']}.json")
        assert set(saved['selected_ids'])<=set(saved['revealed_ids'])
        ids={p['id'] for p in saved['output']}
        assert set(saved['answer']['citations'])<=ids
        source=(root/'data/corpus'/q['file_path']).read_text(encoding='utf-8')
        assert sum(len(p['text']) for p in saved['output'])<=6000
        for p in saved['output']:assert source[slice(*p['span'])]==p['text']
        guard=read(folder/'audits'/f"query-{q['source_index']}.json")
        assert not guard['raw_source_access'] and not guard['gold_access']
        assert not any('/data/corpus/' in p.replace('\\','/').lower() for p in guard['files'])
        outputs.append(dict(source_index=q['source_index'],exact_source_evidence=True,citation_ids_valid=True))
    proof=read(folder/'execution-proof.json');assert proof['isolated_python']==1
    assert all(Path(path).is_relative_to(folder/'code') for path in proof['modules'].values())
    return dict(passed=True,agreements=len(graphs),queries=len(queries),graph_freeze_before_selection=lock['created_before_question_selection'],graphs=graphs,outputs=outputs,
                limitation='Checks syntax, archive/source integrity, tool boundaries and citation existence; not factual/legal answer correctness or semantic completeness.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run_folder',type=Path);args=p.parse_args()
    folder=args.run_folder.resolve();root=Path(__file__).resolve().parents[3]
    report=audit(folder,root)
    target=root/'artifacts/experiment-comparisons'/('domain-audit-'+folder.name+'.json')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'agreements':report['agreements'],'queries':report['queries'],'report':str(target)},indent=2))
