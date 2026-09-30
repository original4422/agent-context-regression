"""Evidence for the single retry-helper work checkpoint."""
import hashlib
import json

from .native import digest

TASK = 'retry-method-policy'
INTERMEDIATE = {'rate_limit': False, 'server_error': True, 'rejected_post_retry': True,
                'exact_allowed_methods': True, 'case_insensitive_method': False, 'exact_status_set': True}
INSTRUCTIONS = ('Use only the acr MCP tools for task files and public checks. Edit only retry.py. '
                'Follow the two-step work request: create the partial checkpoint, then wait for continuation. '
                'Use write_file to edit and check for public smoke checks.')


def intermediate_matches(verdict):
    checks = verdict.get('checks', [])
    return (verdict.get('status') == 'completed' and len(checks) == len(INTERMEDIATE)
            and {c['name']: c['passed'] for c in checks} == INTERMEDIATE
            and all(type(c['passed']) is bool and not c.get('error') for c in checks))


def work_observation(boundary, phase, workspace):
    calls = phase['completed_tools']
    history = [i for i in boundary['turns'][-1]['items'] if i['type'] == 'mcpToolCall']
    fields = ('id', 'server', 'tool', 'arguments', 'status', 'result', 'error')
    projection = lambda items: [{k: i.get(k) for k in fields} for i in items]
    if (not calls or len(calls) != phase['tool_calls'] or projection(calls) != projection(history)
            or any(i['server'] != 'acr' or i['status'] != 'completed' or i.get('error') for i in calls)):
        raise ValueError('work_tool_history_mismatch')
    names = [i['tool'] for i in calls]
    if not {'read_file', 'write_file', 'check'} <= set(names):
        raise ValueError('work_read_write_check_missing')
    last_write = max(i for i, name in enumerate(names) if name == 'write_file')
    last_check = max(i for i, name in enumerate(names) if name == 'check')
    if names.index('read_file') >= names.index('write_file') or last_check <= last_write:
        raise ValueError('work_read_write_check_order')
    source = (workspace / 'retry.py').read_bytes()
    if calls[last_write]['arguments']['content'].encode() != source:
        raise ValueError('work_last_write_mismatch')
    content = calls[last_check]['result']['content']
    if len(content) != 1 or content[0].get('type') != 'text':
        raise ValueError('work_check_result_unavailable')
    verdict = json.loads(content[0]['text'])
    checks = verdict.get('checks', [])
    if (verdict.get('status') != 'completed' or len(checks) != 2
            or {c['name']: c['passed'] for c in checks} != {'rate_limit': False, 'not_found': True}
            or any(type(c['passed']) is not bool or c.get('error') for c in checks)):
        raise ValueError('work_public_checkpoint_mismatch')
    return {'completed_tools': names, 'history_matches_completed_calls': True,
            'last_check_after_last_write': True, 'check_results': checks,
            'tool_history_sha256': digest(projection(calls)),
            'file_sha256': hashlib.sha256(source).hexdigest()}
