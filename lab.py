"""Run versioned experiments from verified code bundles. No retrieval imports here."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(folder):
    return {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def verify_bundle(folder):
    lock = read(folder / 'bundle-lock.json')
    if files(folder / 'code') != lock['files']:
        raise ValueError('Archived bundle changed; refusing to execute it')
    if sha(folder / 'inputs.json') != lock['inputs_sha256']:
        raise ValueError('Archived inputs changed')
    return lock


def activation(lock):
    if platform.python_version() != lock['python'] or platform.system() != lock['system'] or platform.machine() != lock['machine']:
        raise ValueError('Python/platform differs from archived environment; use its pinned Python version')
    paths = set()
    for name, version in lock['packages'].items():
        dist = metadata.distribution(name)
        if dist.version != version:
            raise ValueError(f'Dependency mismatch: {name}; expected {version}, found {dist.version}')
        paths.add(str(Path(dist.locate_file('')).resolve()))
    return sorted(paths)


def new_folder(experiment):
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:6]
    folder = ROOT / 'artifacts/experiment-runs' / experiment / name
    folder.mkdir(parents=True, exist_ok=False)
    return folder


def execute(folder, mode, no_langfuse=False):
    verify_bundle(folder)
    lock = read(folder / 'code/experiment/environment.lock.json')
    try:
        save(folder / 'activation.json', activation(lock))
    except Exception as error:
        save(folder / 'manifest.json', dict(status='failed',mode=mode,error=str(error)))
        raise
    env = os.environ.copy()
    for name in ('PYTHONPATH', 'PYTHONHOME'):
        env.pop(name, None)
    env.update(LAB_PROJECT_ROOT=str(ROOT), LAB_RUN_FOLDER=str(folder), PYTHONDONTWRITEBYTECODE='1', HF_HUB_OFFLINE='1')
    entry=folder/'code/experiment/run.py'
    config=read(folder/'code/experiment/config.json')
    if mode=='replay' and config.get('remote_model'):
        entry=folder/'replay-driver.py'
        shutil.copyfile(ROOT/'scripts/replay_domain_comparison.py',entry)
    command = [sys.executable, '-I', '-B', str(entry),
               '--capsule', str(folder), '--mode', mode]
    if no_langfuse:
        command.append('--no-langfuse')
    print('Run folder: ' + str(folder), flush=True)
    try:
        subprocess.run(command, env=env, check=True, cwd=folder)
    except subprocess.CalledProcessError:
        manifest=folder/'manifest.json'
        if not manifest.exists() or read(manifest).get('status')=='running':
            save(manifest,dict(status='failed',mode=mode,error='Archived worker failed; see terminal error'))
        raise
    verify_bundle(folder)
    return folder


def create(experiment, limit, extraction_cache=None):
    registry = read(ROOT / 'experiments/registry.json')
    spec = registry['experiments'][experiment]
    version = ROOT / spec['version_path']
    cfg = read(version / 'config.json')
    if not 1 <= limit <= cfg['sample_cap']:
        raise ValueError('Choose between one and five development samples' if cfg['sample_cap']==5 else f"Choose 1–{cfg['sample_cap']} agreements")
    folder = new_folder(experiment)
    code = folder / 'code'
    shutil.copytree(version, code / 'experiment', ignore=shutil.ignore_patterns('__pycache__'))
    for area, selected in [('shared', cfg['shared_version']), ('evaluation', cfg['evaluation_version']), ('datasets', cfg['dataset'])]:
        shutil.copytree(ROOT / area / selected, code / area / selected, ignore=shutil.ignore_patterns('__pycache__'))
    # Pin upstream scorer implementation and the sealed graph identity too.
    save(code / 'upstream.json', read(ROOT / 'experiments/legalbenchrag-source.json'))
    save(code / 'graph-lock.json', read(ROOT / 'ontology/experiments/llm100-v1/graph-lock.json'))
    if cfg['kind']=='domain':
        if extraction_cache is not None:
            cache=Path(extraction_cache).resolve()
            if not cache.is_relative_to(ROOT/'artifacts/experiment-runs'):raise ValueError('Extraction cache must be an existing local run')
            receipt={}
            for stage in ('extraction','extraction-links','extraction-expanded'):
                for raw in (cache/'responses'/stage).glob('*.json'):
                    if raw.name.endswith(('-request.json','-error.json','-parse-audit.json')):continue
                    request=raw.with_name(raw.stem+'-request.json')
                    if request.is_file():
                        target=folder/'responses'/stage;target.mkdir(parents=True,exist_ok=True)
                        for path in (raw,request):shutil.copyfile(path,target/path.name);receipt[str(path)]=sha(path)
            save(folder/'cache-reuse.json',dict(source=str(cache),files=receipt,note='Source-only model responses; exact request/payload equality is checked before use.'))
        docs=read(code/'datasets'/cfg['dataset']/'source-manifest.json')['documents'][:limit]
        for doc in docs:
            if sha(ROOT/'data/corpus'/doc['local_file_path'])!=doc['sha256']:
                raise ValueError('Source document changed')
        save(folder/'inputs.json',[dict(document=d) for d in docs])
        if cfg.get('frozen_graph_source'):
            source=ROOT/cfg['frozen_graph_source']
            for name,digest in read(source/'run-lock.json')['files'].items():
                if sha(source/name)!=digest:raise ValueError('Frozen source run changed: '+name)
            if read(source/'inputs.json')!=read(folder/'inputs.json'):raise ValueError('Frozen graph cohort differs')
            for name in ('graphs','variants','graph-lock.json','queries.json','query-bank-identity.json','extraction-summary.json'):
                path=source/name
                if path.is_dir():shutil.copytree(path,folder/name)
                else:shutil.copyfile(path,folder/name)
            save(folder/'graph-provenance.json',dict(source=str(source),source_lock_sha256=sha(source/'run-lock.json'),new_extraction_calls=0))
        save(folder/'bundle-lock.json',dict(files=files(code),inputs_sha256=sha(folder/'inputs.json')))
        return folder
    samples = read(code / 'datasets' / cfg['dataset'] / 'questions.json')[:limit]
    if cfg['kind']=='agentic':
        ids={s['source_index'] for s in samples}
        baseline=read(ROOT/'ontology/experiments/llm100-v1/comparison-v1/results.json')
        save(code/'baseline-results.json',[r for r in baseline['results'] if r['source_index'] in ids])
    docs = {d['id']: d for d in read(ROOT / 'ontology/experiments/llm100-v1/manifest.json')['documents']}
    inputs = []
    for sample in samples:
        doc = docs[sample['document_id']]
        if sha(ROOT / 'data/corpus' / doc['local_file_path']) != doc['sha256']:
            raise ValueError('Source document changed')
        entry = dict(sample=sample, document=doc)
        if cfg['kind'] == 'selection':
            source = ROOT / cfg['source_run']
            receipt = read(source / 'retrieval-complete.json')
            path = source / f"sample-{sample['source_index']}-retrieval.json"
            if sha(path) != receipt['files'][path.name]:
                raise ValueError('Fixed retrieval source changed')
            saved = read(path)
            if saved['sample'] != sample:
                raise ValueError('Fixed source question changed')
            entry.update(before=saved['retrieval']['stages']['iterative'], source_trace_sha256=sha(path))
        inputs.append(entry)
    save(folder / 'inputs.json', inputs)
    save(folder / 'bundle-lock.json', dict(files=files(code), inputs_sha256=sha(folder / 'inputs.json')))
    return folder


def repeat(source, mode, no_langfuse=False):
    source = Path(source).resolve()
    if not (source / 'bundle-lock.json').is_file():
        raise ValueError('Legacy run has no executable bundle. It is preserved; create a new versioned run first.')
    verify_bundle(source)
    run_lock = read(source / 'run-lock.json')['files']
    for name, digest in run_lock.items():
        if sha(source / name) != digest:
            raise ValueError('Saved run changed: ' + name)
    if read(source / 'manifest.json')['status'] != 'complete':
        raise ValueError('Only complete runs can be repeated')
    cfg = read(source / 'code/experiment/config.json')
    folder = new_folder(cfg['experiment_id'])
    shutil.copytree(source / 'code', folder / 'code')
    for name in ('inputs.json', 'bundle-lock.json'):
        shutil.copyfile(source / name, folder / name)
    save(folder / 'lineage.json', dict(mode=mode, source=str(source), source_bundle_sha256=sha(source / 'bundle-lock.json')))
    shutil.copyfile(source / 'model.json', folder / 'expected-model.json')
    if cfg['kind']=='domain':
        if (source/'variants').exists():
            if mode=='replay':shutil.copytree(source/'variants',folder/'variants')
            else:
                # A fresh inference rerun reuses graphs, never prior query responses/cost logs.
                for variant in (source/'variants').iterdir():
                    if not variant.is_dir():continue
                    for name in ('graphs','graph-lock.json','extraction-summary.json'):
                        src=variant/name;dst=folder/'variants'/variant.name/name
                        if src.is_dir():shutil.copytree(src,dst)
                        elif src.exists():dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        for name in ('graphs','graph-lock.json','queries.json','query-bank-identity.json','extraction-summary.json'):
            path=source/name
            if path.is_dir():shutil.copytree(path,folder/name)
            elif path.exists():shutil.copyfile(path,folder/name)
        if mode=='replay':
            for name in ('vector-outputs.json',):
                shutil.copyfile(source/name,folder/name)
    if (source / 'database.json').exists():
        shutil.copyfile(source / 'database.json', folder / 'expected-database.json')
    if mode == 'replay':
        for path in source.glob('output-*.json'):
            value = read(path)
            value.update(seconds=None, timing_scope='replay-no-model-calls', trace_id=None, trace_url=None)
            save(folder / path.name, value)
    return execute(folder, mode, no_langfuse)


def compare(left, right):
    left, right = Path(left).resolve(), Path(right).resolve()
    a, b = read(left / 'results.json'), read(right / 'results.json')
    for name in ('question_sha256', 'scorer_sha256', 'gold_sha256', 'upstream_sha256'):
        if a[name] != b[name]:
            raise ValueError('Different questions/scorer versions')
    inputs = lambda p: [(e.get('sample',{'document_id':e['document']['id']}), e['document']['sha256']) for e in read(p / 'inputs.json')]
    if inputs(left) != inputs(right):
        raise ValueError('Different sample/document versions')
    lines = ['# Matched comparison', '', f'Left: `{left}`', '', f'Right: `{right}`', '',
             '| Source | Precision left / right | Recall left / right | Characters left / right |',
             '|---|---:|---:|---:|']
    for x, y in zip(a['results'], b['results']):
        m, n = x['metrics'], y['metrics']
        lines.append(f"| {x['source_index']} | {m['precision']:.1%} / {n['precision']:.1%} | {m['recall']:.1%} / {n['recall']:.1%} | {m['returned_characters']} / {n['returned_characters']} |")
    lines += ['', 'Timing scopes: ' + str(sorted({r['timing_scope'] for r in a['results']})) + ' versus ' + str(sorted({r['timing_scope'] for r in b['results']})),
              '', 'Known development examples, correct contract supplied. Character overlap is not legal correctness. Local inference has no per-call API fee; hardware/electricity are not measured.']
    path = ROOT / 'artifacts/experiment-comparisons' / ('compare-' + uuid.uuid4().hex[:8] + '.md')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    for name in ('run', 'check'):
        r = sub.add_parser(name); r.add_argument('experiment'); r.add_argument('--limit', type=int); r.add_argument('--no-langfuse', action='store_true')
        r.add_argument('--extraction-cache',type=Path)
    for name in ('rerun', 'replay'):
        r = sub.add_parser(name); r.add_argument('source', type=Path); r.add_argument('--no-langfuse', action='store_true')
    c = sub.add_parser('compare'); c.add_argument('left', type=Path); c.add_argument('right', type=Path)
    args = p.parse_args()
    if args.command == 'list':
        for name, spec in read(ROOT / 'experiments/registry.json')['experiments'].items():
            print(name + ': ' + spec['version_path'])
    elif args.command in ('run', 'check'):
        spec=read(ROOT/'experiments/registry.json')['experiments'][args.experiment]
        cfg=read(ROOT/spec['version_path']/'config.json')
        limit=args.limit if args.limit is not None else (cfg['sample_cap'] if args.command=='run' else 1)
        execute(create(args.experiment, limit,args.extraction_cache), 'fresh' if args.command=='run' else 'check', args.no_langfuse)
    elif args.command in ('rerun', 'replay'):
        repeat(args.source, args.command, args.no_langfuse)
    else:
        compare(args.left, args.right)


if __name__ == '__main__':
    main()
