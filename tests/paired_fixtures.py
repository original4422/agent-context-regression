from policy_fixtures import SOLUTIONS as POLICY_SOLUTIONS

REFERENCE = POLICY_SOLUTIONS['rollout-dependency-admission'].replace('select_batch', 'select_plan')
SOLUTIONS = {
    'wave-policy-a': REFERENCE,
    'wave-policy-b': REFERENCE.replace('selected.append(job["id"])', 'selected.append(job["id"]); completed.add(job["id"])'),
}
