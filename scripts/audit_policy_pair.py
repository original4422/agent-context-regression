"""Fingerprint the policy-neutral inputs of the built-in release-plan pair."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_regression.bridge import TOOLS
from context_regression.runner import continuation_prompt
from context_regression.tasks import BUILTIN_TASKS, load_task, recent_turns, render_history


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def audit(prefix="wave-policy"):
    tasks = [load_task(BUILTIN_TASKS / f'{prefix}-{version}') for version in ('a', 'b')]
    common = []
    for task in tasks:
        history = task['history']
        values = {
            'recent_continuation_prompt': continuation_prompt(task, render_history(recent_turns(history, 1))).encode(),
            'snapshot_plan.py': (task['path'] / 'snapshot/plan.py').read_bytes(),
            'public.py': (task['path'] / 'public.py').read_bytes(),
            'tool_metadata': encode(TOOLS),
            'editable_files': encode(task['spec']['editable']),
            'task_spec_without_id': encode({k:v for k,v in task['spec'].items() if k != 'id'}),
            'history_without_policy_decision': encode(history[:2] + history[3:]),
        }
        common.append(values)
    assert common[0] == common[1]
    assert tasks[0]['history'][2]['role'] == tasks[1]['history'][2]['role'] == 'user'
    assert tasks[0]['history'][2] != tasks[1]['history'][2]
    return {
        'pair': [t['spec']['id'] for t in tasks],
        'only_differing_history_message_index': 2,
        'common_inputs_sha256': {name:digest(value) for name,value in common[0].items()},
        'policy_decision_sha256': {t['spec']['id']:digest(encode(t['history'][2])) for t in tasks},
        'task_sha256': {t['spec']['id']:t['digest'] for t in tasks},
        'model_surface': 'The prompt omits task id/title. MCP tools expose only neutral file names/content and policy-neutral public check outcomes. Per-attempt working directories use random acr- names; task paths in CLI process configuration are not tool metadata.',
    }


if __name__ == '__main__':
    print(json.dumps(audit(sys.argv[1] if len(sys.argv) > 1 else "wave-policy"), indent=2))
