"""Explicitly regenerate dependency locks when creating a NEW experiment version."""
import importlib.metadata as metadata
import argparse
import json
from pathlib import Path
import platform
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('version_folder',type=Path,help='NEW version folder without existing environment lock files')
args=parser.parse_args()
target=args.version_folder.resolve()
if not target.is_relative_to(ROOT/'experiments') or not (target/'config.json').exists():
    raise ValueError('Choose an experiment version folder inside this project')
if any((target/name).exists() for name in ('environment.lock.json','requirements.lock')):
    raise ValueError('Existing version locks are immutable; use a new version folder')
pending = ['sentence-transformers', 'langfuse', 'psycopg[binary]', 'pgvector', 'python-dotenv', 'pydantic', 'rdflib', 'packaging']
seen, packages = set(), {}
while pending:
    req = Requirement(pending.pop())
    name = canonicalize_name(req.name)
    extras = tuple(sorted(req.extras))
    if (name, extras) in seen:
        continue
    seen.add((name, extras))
    dist = metadata.distribution(name)
    if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
        raise ValueError(f'Installed dependency does not satisfy {req}: {dist.version}')
    packages[name] = dist.version
    for raw in dist.requires or []:
        child = Requirement(raw)
        if child.marker is None or any(child.marker.evaluate({'extra': extra}) for extra in ('', *extras)):
            pending.append(raw)
lock = {'python': platform.python_version(), 'system': platform.system(), 'machine': platform.machine(),
        'packages': dict(sorted(packages.items())),
        'note': 'Exact installed transitive dependency versions; model weights and services are separately identified. Packages are not vendored.'}
(target/'environment.lock.json').write_text(json.dumps(lock, indent=2)+'\n')
(target/'requirements.lock').write_text('# Python '+lock['python']+'; '+lock['system']+' '+lock['machine']+'\n'+'\n'.join(f'{k}=={v}' for k,v in lock['packages'].items())+'\n')
print(f'Pinned {len(packages)} packages in {target}')
