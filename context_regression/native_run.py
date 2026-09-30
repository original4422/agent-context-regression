"""One bounded native smoke: real seed, two forks, independent code scoring."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from .bridge import TOOLS
from .checks import run_checks
from .native import LIMITS, check_fork, digest, isolated_config, native_plan
from .native_approval import approve_fixture
from .native_client import AppServer
from .native_preflight import PrivateTrace, check_effective, cleanup_observed, file_hash, identity, read_mcp
from .tasks import BUILTIN_TASKS, load_task

MODEL, EFFORT = 'gpt-6-astra', 'low'
INSTRUCTIONS = ('Use only the acr MCP tools for task files and public checks. Edit only plan.py. '
                'The seed asks you to confirm and wait without tools. A later coding request authorizes '
                'the four fixture tools; use write_file to edit and check for public smoke checks.')


def save(path, value):
    with open(path, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as file:
        json.dump(value, file, indent=2)
        file.write('\n')


def checkpoint(workspace):
    return digest({str(p.relative_to(workspace)): file_hash(p) for p in sorted(workspace.rglob('*')) if p.is_file()})


def reset(workspace):
    # The live app-server and bridge use this cwd. Preserve its inode while
    # replacing only the contents of this harness-owned candidate directory.
    workspace.mkdir(exist_ok=True)
    for entry in workspace.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    shutil.copytree(BUILTIN_TASKS / 'visible-policy-a/snapshot', workspace, dirs_exist_ok=True)
    return checkpoint(workspace)


class LiveSession:
    """This experiment's thread lifecycle and observed ACR connection identities."""
    def __init__(self, host, overrides, workspace, mcp_trace):
        self.host, self.overrides, self.workspace, self.mcp_trace = host, overrides, workspace, mcp_trace
        self.threads, self.bridges = {}, {}

    def new_thread(self, label, source=None, last_turn=None):
        before = {e['value']['pid'] for e in read_mcp(self.mcp_trace) if e['kind'] == 'start'}
        params = {'cwd': str(self.workspace), 'ephemeral': False, 'model': MODEL,
                  'sandbox': 'read-only', 'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
                  'config': self.overrides, 'developerInstructions': INSTRUCTIONS}
        if source:
            params.update(threadId=source, lastTurnId=last_turn, excludeTurns=False)
            result = self.host.lifecycle('thread/fork', params)
        else:
            params.update(historyMode='legacy', allowProviderModelFallback=False)
            result = self.host.request('thread/start', params)
        thread = result['thread']
        if (result['model'], result.get('reasoningEffort'), result['sandbox']['type'], result['approvalPolicy'],
                result['approvalsReviewer'], result['cwd'], thread['ephemeral']) != (
                MODEL, EFFORT, 'readOnly', 'on-request', 'user', str(self.workspace), False):
            raise ValueError('thread_configuration_mismatch')
        if not thread.get('path') or thread.get('historyMode') != 'legacy':
            raise ValueError('persistent_legacy_history_unavailable')
        if thread['id'] in self.threads:
            raise ValueError('thread_identity_reused')
        self.threads[thread['id']] = {'label': label, 'path': thread['path'], 'source': source,
                                     'model_provider': result['modelProvider'], 'response': result}
        self.host.wait_notification(lambda e: e['method'] == 'mcpServer/startupStatus/updated' and
                                    e['params'].get('threadId') == thread['id'] and e['params'].get('name') == 'acr'
                                    and e['params'].get('status') == 'ready')
        events = read_mcp(self.mcp_trace)
        starts = [e['value'] for e in events if e['kind'] == 'start' and e['value']['pid'] not in before]
        if len(starts) != 1 or identity(starts[0]['pid']) != starts[0]['started']:
            raise ValueError('thread_mcp_identity_mismatch')
        self.bridges[thread['id']] = starts[0]
        self.check_tools(thread['id'])
        if source and result['modelProvider'] != self.threads[source]['model_provider']:
            raise ValueError('fork_provider_mismatch')
        return thread

    def check_tools(self, thread_id):
        owner = self.bridges[thread_id]
        events = [e for e in read_mcp(self.mcp_trace) if e.get('pid') == owner['pid']]
        requests = [e['value'] for e in events if e['kind'] == 'request']
        ids = [r['id'] for r in requests if r.get('method') == 'tools/list']
        catalogs = [e['value']['result']['tools'] for e in events if e['kind'] == 'response' and e['value'].get('id') in ids]
        startup = [e['params']['name'] for e in self.host.notifications if e['method'] == 'mcpServer/startupStatus/updated'
                   and e['params'].get('threadId') == thread_id]
        if (catalogs != [TOOLS] or sum(r.get('method') == 'initialize' for r in requests) != 1
                or set(startup) != {'acr'} or identity(owner['pid']) != owner['started']):
            raise ValueError('thread_tool_catalog_mismatch')
        return {'catalog_sha256': digest(TOOLS), 'same_bridge_identity': True}

    def read(self, thread_id):
        thread = self.host.lifecycle('thread/read', {'threadId': thread_id, 'includeTurns': True})['thread']
        if thread['id'] != thread_id or thread.get('status', {}).get('type') != 'idle':
            raise ValueError('thread_not_idle')
        return thread

    def phase(self, kind, thread_id, text=None, previous=None):
        self.check_tools(thread_id)
        params = {'threadId': thread_id}
        if kind != 'compact':
            params.update(input=[{'type': 'text', 'text': text, 'text_elements': []}], model=MODEL, effort=EFFORT)
        approved = set()
        began = time.monotonic()
        result = self.host.phase(kind, thread_id, params, LIMITS[kind], previous_turn_id=previous,
                                 approve=lambda event, phase: approve_fixture(event, phase, self.workspace, approved))
        result.update(thread_id=thread_id, kind=kind, elapsed_seconds=round(time.monotonic() - began, 3),
                      single_call_approvals=len(approved))
        return result


def exercise_pairs(session, workspace, private, report, verify=run_checks):
    """Fixed eight-stage graph, no retries; protocol failures stop both pairs."""
    for pair in native_plan(MODEL, EFFORT)['pairs']:
        label = pair['task'][-1].upper()
        expected = reset(workspace)
        row = {'task': pair['task'], 'seed': {}, 'arms': []}
        report['pairs'].append(row)
        seed = session.new_thread(label + '.seed')
        phase = session.phase('seed', seed['id'], pair['seed_text'])
        row['seed'] = phase
        if phase['status'] != 'completed':
            raise ValueError('seed:' + phase['status'])
        if checkpoint(workspace) != expected:
            raise ValueError('seed_modified_checkpoint')
        boundary = session.read(seed['id'])
        if boundary['turns'][-1]['id'] != phase['turn_id']:
            raise ValueError('seed_completed_boundary_mismatch')
        branches = {}
        # Both forks exist before either continuation edits the candidate.
        for arm in ('control', 'native-compact'):
            branch = session.new_thread(label + '.' + arm, seed['id'], phase['turn_id'])
            fingerprint = check_fork(boundary, branch, phase['turn_id'])
            readback = session.read(branch['id'])
            if fingerprint != check_fork(boundary, readback, phase['turn_id']):
                raise ValueError('fork_readback_mismatch')
            branches[arm] = readback
        if branches['control']['id'] == branches['native-compact']['id']:
            raise ValueError('fork_identity_collision')
        row['boundary_sha256'] = fingerprint
        for arm in pair['arms']:
            if reset(workspace) != expected:
                raise ValueError('candidate_reset_mismatch')
            branch = branches[arm]
            arm_row = {'arm': arm, 'thread_id': branch['id'], 'phases': [], 'checkpoint_sha256': expected}
            row['arms'].append(arm_row)
            previous = branch['turns'][-1]['id']
            if arm == 'native-compact':
                phase = session.phase('compact', branch['id'], previous=previous)
                arm_row['phases'].append(phase)
                if phase['status'] != 'completed':
                    raise ValueError('compaction_capability_gate:' + phase['status'])
                if checkpoint(workspace) != expected:
                    raise ValueError('compaction_modified_checkpoint')
                session.read(branch['id'])
                previous = phase['turn_id']
            phase = session.phase('continuation', branch['id'], pair['request'], previous)
            arm_row['phases'].append(phase)
            if phase['status'] != 'completed':
                raise ValueError('continuation:' + phase['status'])
            session.check_tools(branch['id'])
            saved = private / (label + '-' + arm)
            shutil.copytree(workspace, saved)
            for file in saved.rglob('*'):
                if file.is_file():
                    file.chmod(0o600)
            verdicts = {name: verify(BUILTIN_TASKS / name, workspace, 'oracle')
                        for name in ('visible-policy-a', 'visible-policy-b')}
            accepted = [name for name, verdict in verdicts.items() if verdict['passed']]
            if len(accepted) > 1:
                raise ValueError('oracle_policy_discriminator_broken')
            arm_row.update(candidate_sha256=checkpoint(saved), cross_verification=verdicts,
                           shared_rules_pass=all(c['passed'] for v in verdicts.values() for c in v['checks'] if c['name'] != 'dependency_policy'),
                           classification=('requested_policy' if accepted == [pair['task']] else 'opposite_policy' if accepted else 'neither_policy'))
            save(private / 'results.json', report)


def public_report(report):
    """Only an explicit public evidence shape; real IDs/paths stay private."""
    result = {key: report[key] for key in ('status', 'model', 'effort', 'scope', 'plan', 'environment', 'checks') if key in report}
    result.update(error=report.get('error'), usage=None, usage_coverage='incomplete', pairs=[])
    def phase(value, alias):
        return {key: value.get(key) for key in ('kind', 'status', 'elapsed_seconds', 'tool_calls', 'single_call_approvals', 'terminal', 'cancellation', 'usage_issue', 'request_id')} | {
            'turn': alias if value.get('turn_id') else None, 'start_sequence': value.get('start_sequence'),
            'evidence': [{key: event[key] for key in ('sequence', 'event', 'status') if key in event} for event in value.get('evidence', [])],
            'compaction_item_fingerprints': [digest(item) for item in value.get('compaction_item_ids', [])],
            'usage': None, 'usage_coverage': 'unavailable',
            'usage_snapshots': [{'sequence': e['sequence'], 'tokenUsage': e['notification']['tokenUsage']}
                                for e in value.get('usage_events', [])]}
    for pair in report['pairs']:
        label = pair['task'][-1].upper()
        row = {'task': pair['task'], 'seed': phase(pair['seed'], label + '.seed.turn'),
               'boundary_sha256': pair.get('boundary_sha256'), 'arms': []}
        for arm in pair['arms']:
            alias = label + '.' + arm['arm']
            row['arms'].append({key: arm[key] for key in ('arm', 'checkpoint_sha256', 'candidate_sha256', 'shared_rules_pass', 'classification', 'cross_verification') if key in arm} | {
                'thread': alias, 'forked_from': label + '.seed', 'phases': [phase(p, alias + '.' + p['kind']) for p in arm['phases']]})
        result['pairs'].append(row)
    for arm in ('control', 'native-compact'):
        rows = [a for p in result['pairs'] for a in p['arms'] if a['arm'] == arm]
        result[arm + '_both_policies_pass'] = (all(a.get('classification') == 'requested_policy' for a in rows)
                                              if len(rows) == 2 and all('classification' in a for a in rows) else None)
    return result


def run_native_smoke(private, codex='codex'):
    private = Path(private).resolve()
    private.mkdir(parents=True, mode=0o700, exist_ok=False)
    private.chmod(0o700)
    binary = Path(shutil.which(codex) or codex).resolve()
    config_path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    before = file_hash(config_path)
    report = {'status': 'running', 'scope': 'Bounded native compaction smoke; eight phases maximum, no retries',
              'model': MODEL, 'effort': EFFORT, 'plan': native_plan(MODEL, EFFORT), 'pairs': [], 'checks': {}}
    host = trace = session = None
    temporary = None
    mcp_trace = private / 'mcp.jsonl'
    tasks_before = {name: load_task(BUILTIN_TASKS / name)['digest'] for name in ('visible-policy-a', 'visible-policy-b')}
    try:
        schema = private / 'schema'
        subprocess.run([str(binary), 'app-server', 'generate-json-schema', '--experimental', '--out', str(schema)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        report['environment'] = {'binary_sha256': file_hash(binary),
            'codex_version': subprocess.check_output([str(binary), '--version'], text=True, timeout=10).strip(),
            'schema_bundle_sha256': digest({str(p.relative_to(schema)): file_hash(p) for p in sorted(schema.rglob('*.json'))}),
            'source_sha256': {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
            'developer_instructions_sha256': digest(INSTRUCTIONS), 'config_sha256_before': before}
        with tempfile.TemporaryDirectory(prefix='acr-native-smoke-') as temporary:
            workspace = Path(temporary) / 'candidate'
            reset(workspace)
            bridge = [sys.executable, '-I', '-B', str(Path(__file__).with_name('native_bridge.py')),
                      str(BUILTIN_TASKS / 'visible-policy-a'), str(workspace), str(binary), str(os.getpid()), str(mcp_trace)]
            _, args = isolated_config({}, bridge, MODEL, EFFORT)
            trace = PrivateTrace(private / 'discovery.jsonl')
            host = AppServer([str(binary), *args], workspace, trace)
            host.initialize()
            inherited = host.request('config/read', {'cwd': str(workspace), 'includeLayers': False})['config']
            overrides, args = isolated_config(inherited, bridge, MODEL, EFFORT)
            host.close(); trace.close()
            host = trace = None
            if read_mcp(mcp_trace):
                raise ValueError('discovery_started_mcp')
            trace = PrivateTrace(private / 'app-server.jsonl')
            host = AppServer([str(binary), *args], workspace, trace)
            host.initialize()
            effective = host.request('config/read', {'cwd': str(workspace), 'includeLayers': False})['config']
            report['environment']['effective_config'] = check_effective(effective, overrides)
            del inherited, effective
            session = LiveSession(host, overrides, workspace, mcp_trace)
            exercise_pairs(session, workspace, private, report,
                           verify=lambda task, saved, mode: run_checks(task, saved, mode, str(binary)))
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        report['status'] = 'failed'
        report['error'] = str(error) if isinstance(error, (ValueError, RuntimeError, TimeoutError)) else type(error).__name__
    finally:
        if session:
            report['threads'] = session.threads
            report['bridge_identities'] = session.bridges
        if host:
            report['checks']['app_server_reaped'] = host.close() is not None
        if trace:
            trace.close()
        bridges = {e['value']['pid']: e['value']['started'] for e in read_mcp(mcp_trace) if e['kind'] == 'start'}
        report['checks']['bridges_cleaned'] = cleanup_observed(bridges)
        report['checks']['candidate_cleaned'] = temporary is None or not Path(temporary).exists()
        report['checks']['config_unchanged'] = before == file_hash(config_path)
        if 'environment' in report:
            report['environment']['config_sha256_after'] = file_hash(config_path)
            report['checks']['runner_unchanged'] = report['environment']['source_sha256'] == {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
        report['checks']['tasks_unchanged'] = tasks_before == {name: load_task(BUILTIN_TASKS / name)['digest'] for name in tasks_before}
        if not all(report['checks'].values()):
            report['status'] = 'failed'
        save(private / 'results.json', report)
        save(private / 'public.json', public_report(report))
    return public_report(report)
