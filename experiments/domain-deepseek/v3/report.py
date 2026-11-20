"""Describe the broader cohort including operational failures; never tune/retry queries."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import mean

read=lambda p:json.loads(p.read_text(encoding='utf-8'))


def summarize(folder):
    inputs=read(folder/'inputs.json');reports={};outputs={};details={}
    for variant,sub in [('existing',folder),('expanded',folder/'variants/expanded')]:
        report=read(sub/'results.json');reports[variant]=report
        saved={r['source_index']:read(sub/f"output-{r['source_index']}.json") for r in report['results']};outputs[variant]=saved
        errors=Counter(s['error'] for s in saved.values() if s.get('error'))
        good=[r for r in report['results'] if not saved[r['source_index']].get('error')]
        details[variant]=dict(queries=len(saved),failed=sum(errors.values()),errors=dict(errors),successfully_executed=len(good),successful_query_precision=mean(r['metrics']['precision'] for r in good) if good else None,successful_query_recall=mean(r['metrics']['recall'] for r in good) if good else None,matched_vector_precision=mean(r['metrics']['vector_precision'] for r in good) if good else None,matched_vector_recall=mean(r['metrics']['vector_recall'] for r in good) if good else None,successful_retrieval_seconds=mean(r['seconds'] for r in good) if good else None,successful_answer_seconds=mean(r['answer_seconds'] for r in good) if good else None,stops=dict(Counter(s['stop'] for s in saved.values())))
    rows=reports['existing']['results'];other={r['source_index']:r for r in reports['expanded']['results']}
    paired=dict(improved=sum(other[r['source_index']]['metrics']['recall']>r['metrics']['recall']+1e-9 for r in rows),worse=sum(other[r['source_index']]['metrics']['recall']<r['metrics']['recall']-1e-9 for r in rows))
    calls=[c for sub in [folder,folder/'variants/expanded'] for p in sub.glob('api-calls-*.json') for c in read(p)]
    inherited=0.;origin=None
    if (folder/'cache-reuse.json').exists():
        origin=Path(read(folder/'cache-reuse.json')['source'])
        inherited=sum(c['cost_usd'] for p in origin.glob('api-calls-*.json') for c in read(p))
    money=dict(new_paid_usd=sum(c['cost_usd'] for c in calls),previous_attempt_paid_usd=inherited,combined_paid_usd=inherited+sum(c['cost_usd'] for c in calls),paid_calls=sum(not c['cache_hit'] for c in calls),cached_generations=sum(c['cache_hit'] for c in calls))
    table=[]
    for entry in inputs:
        doc=entry['document'];selected=[r for r in rows if r['document_id']==doc['id']]
        record=read(folder/'graphs'/f"{doc['id']}.json");expanded=read(folder/'variants/expanded/graphs'/f"{doc['id']}.json")
        table.append(dict(document_id=doc['id'],provisions=len(record['provisions']),extra_links=sum(l['traversable'] for l in expanded['expanded_links']),questions=len(selected),failed_queries=sum(bool(outputs['existing'][r['source_index']].get('error')) for r in selected),vector_recall=mean(r['metrics']['vector_recall'] for r in selected) if selected else None,existing_recall=mean(r['metrics']['recall'] for r in selected) if selected else None,expanded_recall=mean(other[r['source_index']]['metrics']['recall'] for r in selected) if selected else None))
    data=dict(run=str(folder),agreements=len(inputs),questions=len(rows),variants=details,relationship_recall_effect=paired,cost=money,documents=table)
    out=folder.parents[2]/'experiment-comparisons';out.mkdir(exist_ok=True)
    target=out/('random20-'+folder.name)
    target.with_suffix('.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    pct=lambda v:'n/a' if v is None else f'{v:.1%}'
    s=reports['existing']['summary']
    lines=['# Twenty additional random agreements','',f"Run: `{folder.name}`. {len(inputs)} agreements, {len(rows)} questions. Uniform document sample seed 20261115; excludes previous ten. All eligible questions, no topic filter. Frozen source-only graphs precede question selection.",'','## Overall results, including failures','','| Method | Precision | Recall | Retrieval seconds/query | Failed queries |','|---|---:|---:|---:|---:|',f"| Normal RAG | {pct(s['vector_precision'])} | {pct(s['vector_recall'])} | {s['mean_vector_seconds']:.3f} | 0 |"]
    for variant in reports:
        s=reports[variant]['summary'];d=details[variant]
        lines.append(f"| {variant.title()} ontology | {pct(s['precision'])} | {pct(s['recall'])} | {s['mean_retrieval_seconds']:.3f} | {d['failed']}/{d['queries']} |")
    lines+=['','Failures return no evidence and count as zero. Very fast failed attempts must not be read as useful low-latency retrieval. Normal RAG measures retrieval only; ontology answer-generation timing and API costs are separate in results.json. All methods receive the correct agreement: this does not test routing across documents or legal-answer accuracy.','', '## Successfully executed graph queries (diagnostic subset only)','']
    for variant,d in details.items():
        lines.append(f"- {variant.title()}: {d['successfully_executed']}/{d['queries']} executed without a validation/limit error; precision {pct(d['successful_query_precision'])}, recall {pct(d['successful_query_recall'])}. Normal RAG on these same questions: precision {pct(d['matched_vector_precision'])}, recall {pct(d['matched_vector_recall'])}. Retrieval/answer seconds per successfully executed query: {d['successful_retrieval_seconds']}/{d['successful_answer_seconds']}. Errors: `{json.dumps(d['errors'])}`.")
    lines+=['',f"Expanded relationships improved recall for {paired['improved']} questions and reduced it for {paired['worse']}. Both variants use identical extracted provisions and source passages. This comparison tests only the current bounded query agent's use of the added edges.",'','## Agreement breakdown','','| Agreement | Rules | Added links | Questions | Existing failures | RAG recall | Existing recall | Expanded recall |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in table:lines.append(f"| {r['document_id']} | {r['provisions']} | {r['extra_links']} | {r['questions']} | {r['failed_queries']} | {pct(r['vector_recall'])} | {pct(r['existing_recall'])} | {pct(r['expanded_recall'])} |")
    lines+=['','## Spend and reproducibility','',f"Original interrupted attempt: ${inherited:.6f}. Continuation: ${money['new_paid_usd']:.6f}. Combined actual provider spend: ${money['combined_paid_usd']:.6f}. Continuation reused {money['cached_generations']} exact cached responses and made {money['paid_calls']} paid calls. Infrastructure, electricity and labor are not priced.",'','The first attempt stopped on literal tab characters inside two model JSON strings. A logged parser fallback preserves string values and the original responses while retaining schema validation. Other malformed JSON fails. No prompts, semantic limits or document selection were changed. The raw failed attempt and exact cache provenance remain available.','', 'These agreements are new to this experiment, but may have appeared in earlier experiments. They are not an independently blind evaluation. Source/quote checks and valid citations do not establish semantic completeness or correct legal interpretation.','',f"Rerun inference: `.\\.venv\\Scripts\\python.exe lab.py rerun {folder.relative_to(folder.parents[3]).as_posix()}`",f"Replay scores without inference: `.\\.venv\\Scripts\\python.exe lab.py replay {folder.relative_to(folder.parents[3]).as_posix()} --no-langfuse`",'','The archived code, prompts, dependency locks, source fingerprints, request/response payloads, graph locks and per-question outputs are in the run folder.']
    target.with_suffix('.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(data,indent=2));print('Report: '+str(target.with_suffix('.md')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_folder',type=Path);summarize(p.parse_args().run_folder.resolve())
