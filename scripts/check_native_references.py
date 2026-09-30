"""Cross-score the two trusted references in the real read-only OS sandbox.

No model request. Run from the repository: python3 -B scripts/check_native_references.py
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from context_regression.checks import run_checks
from context_regression.tasks import BUILTIN_TASKS, load_task
from visible_fixtures import SOLUTIONS


def check():
    rows = []
    tasks = {name: load_task(BUILTIN_TASKS / name) for name in SOLUTIONS}
    with tempfile.TemporaryDirectory(prefix='acr-native-reference-') as temporary:
        candidate = Path(temporary) / 'candidate'
        candidate.mkdir()
        for name, source in SOLUTIONS.items():
            (candidate / 'plan.py').write_text(source)
            verdicts = {other: run_checks(task['path'], candidate, 'oracle') for other, task in tasks.items()}
            assert all(c['passed'] for v in verdicts.values() for c in v['checks'] if c['name'] != 'dependency_policy')
            assert [other for other, v in verdicts.items() if v['passed']] == [name]
            rows.append({'reference': name, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                         'shared_rules_pass': True, 'cross_verification': verdicts})
    return {'scope': 'Trusted references only; real read-only sandbox, no model or native compaction run',
            'codex_version': subprocess.check_output(['codex', '--version'], text=True).strip(),
            'task_sha256': {name: task['digest'] for name, task in tasks.items()},
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted([*ROOT.glob('context_regression/*.py'), ROOT / 'tests/visible_fixtures.py', Path(__file__).resolve()])},
            'references': rows}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
