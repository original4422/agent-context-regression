"""Recompute the four published native candidates with the frozen Python oracle."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TASKS = ('visible-policy-a', 'visible-policy-b')
LABELS = ('A-control', 'A-native-compact', 'B-native-compact', 'B-control')
SCENARIOS = {
    'fixed-policy': ('native-smoke.json', 'native-candidates', TASKS, LABELS),
    'policy-revision': ('native-revision.json', 'native-revision-candidates', TASKS[::-1],
                        ('A-to-B-control', 'A-to-B-native-compact', 'B-to-A-native-compact', 'B-to-A-control')),
}


def file_hash(path):
    if not path.is_file():
        raise ValueError(f'missing file: {path.relative_to(ROOT)}')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_hash(path):
    if not path.is_dir() or sorted(p.name for p in path.iterdir()) != ['plan.py']:
        raise ValueError(f'candidate contents mismatch: {path.relative_to(ROOT)}')
    files = {'plan.py': file_hash(path / 'plan.py')}
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(report, scenario='fixed-policy'):
    _, directory, tasks, labels = SCENARIOS[scenario]
    if ([p['task'] for p in report['plan']['pairs']] != list(tasks)
            or [p['task'] for p in report['pairs']] != list(tasks)):
        raise ValueError('report task set mismatch')
    # Check executable dependencies before importing any repository Python code.
    for name in ('__init__.py', 'tasks.py', 'verify.py', 'worker.py', 'release_checks.py'):
        if file_hash(ROOT / 'context_regression' / name) != report['environment']['source_sha256'][name]:
            raise ValueError(f'verifier version mismatch: context_regression/{name}')
    sys.path.insert(0, str(ROOT))
    from context_regression.tasks import task_digest
    for pair in report['plan']['pairs']:
        if task_digest(ROOT / 'context_regression/tasks' / pair['task']) != pair['task_sha256']:
            raise ValueError(f'task version mismatch: {pair["task"]}')
    rows = []
    for pair in report['pairs']:
        for arm in pair['arms']:
            case = pair['case_id'] if scenario == 'policy-revision' else pair['task'][-1].upper()
            label = case + '-' + arm['arm']
            path = ROOT / 'reports' / directory / label
            sha = candidate_hash(path)
            if sha != arm['candidate_sha256']:
                raise ValueError(f'candidate hash mismatch: {label}')
            rows.append((label, path, sha, arm['cross_verification']))
    if tuple(row[0] for row in rows) != labels:
        raise ValueError('report candidate set mismatch')
    return rows


def recheck(scenario='fixed-policy'):
    report = json.loads((ROOT / 'reports' / SCENARIOS[scenario][0]).read_text())
    rows = validate(report, scenario)
    from context_regression.verify import WORKER, evaluate
    results = []
    for label, path, sha, expected in rows:
        command = [sys.executable, '-I', '-B', str(WORKER), str(path / 'plan.py')]
        actual = {task: evaluate(ROOT / 'context_regression/tasks' / task, path, 'oracle', command, timeout=15)
                  for task in TASKS}
        results.append({'candidate': label, 'candidate_sha256': sha, 'cross_verification': actual,
                        'matches_recorded_results': actual == expected,
                        'differences': {task: {'expected': expected.get(task), 'actual': actual.get(task)}
                                        for task in sorted(actual.keys() | expected.keys())
                                        if actual.get(task) != expected.get(task)}})
    validate(report, scenario)
    matched = all(row['matches_recorded_results'] for row in results)
    return {'status': 'completed' if matched else 'mismatch',
            'scope': 'Offline Python candidate behavior recheck; no native lifecycle or sandbox measurement',
            'candidates': results, 'oracle_evaluations': len(results) * len(TASKS),
            'inputs_unchanged': True, 'matches_recorded_results': matched}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=SCENARIOS, default='fixed-policy')
    args = parser.parse_args()
    try:
        result = recheck(args.scenario)
    except ValueError as error:
        print(json.dumps({'status': 'rejected', 'error': str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result['matches_recorded_results'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
