"""Reconcile a saved pair batch and cross-score every private candidate.

Usage: python3 scripts/score_policy_pair.py /private/batch/results.json
Writes the public audit as JSON to stdout. Source candidates/traces stay private.
"""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_policy_pair import audit
from context_regression.checks import run_checks
from context_regression.runner import USAGE_KEYS, phase_total
from context_regression.tasks import BUILTIN_TASKS, load_task


def score(results_path):
    results_path = Path(results_path).resolve()
    report = json.loads(results_path.read_text())
    prefix = report['tasks'][0]['id'].rsplit('-', 1)[0]
    assert prefix in {'wave-policy', 'visible-policy'}
    pair = audit(prefix)
    tasks = {name:load_task(BUILTIN_TASKS / name) for name in pair['pair']}
    assert report['status'] == 'completed'
    assert report['planned_runs'] == len(report['rows']) == 12
    assert {t['id']:t['sha256'] for t in report['tasks']} == pair['task_sha256']
    sources = sorted(BUILTIN_TASKS.parent.glob('*.py'))
    runner_hash = hashlib.sha256(b''.join(p.name.encode() + p.read_bytes() for p in sources)).hexdigest()
    assert report['runner_sha256'] == runner_hash
    candidates, phases, recent_prompts = [], 0, []
    for row in report['rows']:
        attempt = results_path.parent / f"{row['index']:02d}-{row['task']}-{row['strategy']}"
        for phase_name, phase in row['phases'].items():
            events = [json.loads(line) for line in (attempt / phase_name / 'events.jsonl').read_text().splitlines()]
            completed = [e for e in events if e['type'] == 'turn.completed']
            assert len(completed) == 1
            assert {k:completed[0]['usage'][k] for k in USAGE_KEYS} == phase['usage']
            phases += 1
        assert phase_total(row['phases']) == row['total']
        if row['strategy'] == 'recent':
            prompt = (attempt / 'continuation/prompt.txt').read_bytes()
            recent_prompts.append(hashlib.sha256(prompt).hexdigest())
        verdicts = {name:run_checks(task['path'], attempt / 'candidate', 'oracle') for name,task in tasks.items()}
        assert verdicts[row['task']] == row['verification']
        accepted = [name for name,verdict in verdicts.items() if verdict['passed']]
        assert len(accepted) <= 1
        classification = ('requested_policy' if accepted == [row['task']]
                          else 'opposite_policy' if accepted else 'neither_policy')
        candidates.append({
            'index':row['index'], 'task':row['task'], 'strategy':row['strategy'], 'repeat':row['repeat'],
            'source_sha256':hashlib.sha256((attempt / 'candidate/plan.py').read_bytes()).hexdigest(),
            'classification':classification,
            'shared_rules_pass':all(c['passed'] for c in verdicts[row['task']]['checks'] if c['name'] != 'dependency_policy'),
            'policy_discriminator':{name:next(c['passed'] for c in verdict['checks'] if c['name'] == 'dependency_policy') for name,verdict in verdicts.items()},
            'cross_verification':verdicts,
        })
    assert phases == 16
    assert len(recent_prompts) == 4
    assert set(recent_prompts) == {pair['common_inputs_sha256']['recent_continuation_prompt']}
    pairs = []
    for strategy in ('full', 'recent', 'structured'):
        for repeat in (1, 2):
            rows = [r for r in report['rows'] if r['strategy'] == strategy and r['repeat'] == repeat]
            assert {r['task'] for r in rows} == set(tasks)
            pairs.append({'strategy':strategy, 'repeat':repeat,
                          'both_requested_policies_pass':all(r['verification']['passed'] for r in rows)})
    return {
        'results_sha256':hashlib.sha256(results_path.read_bytes()).hexdigest(),
        'runner_sha256':runner_hash,
        'phase_usage_records_reconciled':phases,
        'actual_recent_prompt_sha256':recent_prompts[0],
        'actual_recent_prompts_identical':True,
        'all_own_oracle_rechecks_match':True,
        'pair_outcomes':pairs,
        'candidates':candidates,
    }


if __name__ == '__main__':
    print(json.dumps(score(sys.argv[1]), indent=2))
