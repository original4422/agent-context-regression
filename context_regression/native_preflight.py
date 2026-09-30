"""Real app-server/MCP preflight; never sends model-producing requests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .bridge import TOOLS
from .native import digest, isolated_config
from .native_client import AppServer
from .tasks import BUILTIN_TASKS


class PrivateTrace:
    def __init__(self, path):
        self.file = open(path, 'x', opener=lambda p, flags: os.open(p, flags, 0o600))

    def append(self, event):
        self.file.write(json.dumps(event) + '\n')
        self.file.flush()

    def close(self):
        self.file.close()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def identity(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=', '-o', 'lstart='], text=True, capture_output=True, timeout=3)
    fields = result.stdout.strip().split(maxsplit=1)
    return fields[1] if len(fields) == 2 and not fields[0].startswith('Z') else None


def stop_observed(pid, started):
    """Only a bridge observed in this run, while its process identity still matches."""
    if identity(pid) != started:
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and identity(pid) == started:
        time.sleep(.05)
    if identity(pid) == started:
        os.kill(pid, signal.SIGKILL)
    return identity(pid) != started


def cleanup_observed(bridge_ids):
    # Evaluate every owned PID even if an earlier exit remains unconfirmed.
    outcomes = [stop_observed(pid, born) if born else True for pid, born in bridge_ids.items()]
    return all(outcomes)


def read_mcp(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def check_effective(config, expected):
    """Compare overrides in memory; publish only a small boolean/enum allowlist."""
    for key, wanted in expected.items():
        pieces = key.split('.')
        if pieces[0] in ('mcp_servers', 'plugins'):
            pieces = [pieces[0], '.'.join(pieces[1:-1]), pieces[-1]]
        value = config
        for name in pieces:
            value = value[name]
        if value != wanted:
            raise ValueError('effective_config_mismatch:' + pieces[0])
    return {'disabled_features': [key.split('.', 1)[1] for key, value in expected.items()
                                  if key.startswith('features.') and value is False],
            'approval_policy': config['approval_policy'], 'approvals_reviewer': config['approvals_reviewer'],
            'sandbox_mode': config['sandbox_mode'], 'web_search': config['web_search'],
            'unrelated_mcp_disabled': sum(k != 'acr' and v.get('enabled') is False for k, v in config.get('mcp_servers', {}).items()),
            'plugins_disabled': sum(v.get('enabled') is False for v in config.get('plugins', {}).values())}


def preflight(private, codex='codex'):
    private = Path(private).resolve()
    private.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(private, 0o700)
    binary = Path(shutil.which(codex) or codex).resolve()
    config_path = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    before = file_hash(config_path)
    report = {'scope': 'Real app-server/MCP preflight; no model, fork or compaction requests',
              'status': 'running', 'model_requests': 0, 'checks': {}, 'config_sha256_before': before}
    host, trace = None, None
    bridge_ids = {}
    trace_path = private / 'mcp.jsonl'
    started_at = time.monotonic()
    try:
        report['codex_version'] = subprocess.check_output([str(binary), '--version'], text=True, timeout=10).strip()
        report['binary_sha256'] = file_hash(binary)
        schema = private / 'schema'
        subprocess.run([str(binary), 'app-server', 'generate-json-schema', '--experimental', '--out', str(schema)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        schema_hashes = {str(p.relative_to(schema)): file_hash(p) for p in sorted(schema.rglob('*.json'))}
        report['schema'] = {'files': len(schema_hashes), 'bundle_sha256': digest(schema_hashes),
                            'interfaces': {name: schema_hashes[name] for name in (
                                'ClientRequest.json', 'ServerNotification.json', 'v2/ThreadStartParams.json',
                                'v2/ThreadForkResponse.json', 'v2/ItemCompletedNotification.json',
                                'v2/TurnCompletedNotification.json', 'v2/ThreadTokenUsageUpdatedNotification.json')}}
        report['source_sha256'] = {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
        with tempfile.TemporaryDirectory(prefix='acr-native-preflight-') as temporary:
            workspace = Path(temporary) / 'candidate'
            task = BUILTIN_TASKS / 'visible-policy-a'
            shutil.copytree(task / 'snapshot', workspace)
            source_before = file_hash(workspace / 'plan.py')
            bridge = [sys.executable, '-I', '-B', str(Path(__file__).with_name('native_bridge.py')),
                      str(task), str(workspace), str(binary), str(os.getpid()), str(trace_path)]
            # Discovery starts no thread and invokes no MCP status or tool request.
            # Features are already disabled; the second process also disables each
            # inherited server/plugin by name before creating the actual thread.
            _, bootstrap_args = isolated_config({}, bridge, None, 'low')
            trace = PrivateTrace(private / 'discovery.jsonl')
            host = AppServer([str(binary), *bootstrap_args], workspace, trace)
            host.initialize()
            inherited = host.request('config/read', {'cwd': str(workspace), 'includeLayers': False})['config']
            overrides, args = isolated_config(inherited, bridge, None, 'low')
            report['checks']['discovery_no_mcp'] = not read_mcp(trace_path)
            report['discovery_exit_code'] = host.close()
            trace.close()
            host = trace = None
            if not report['checks']['discovery_no_mcp']:
                raise ValueError('discovery_started_mcp')
            trace = PrivateTrace(private / 'app-server.jsonl')
            host = AppServer([str(binary), *args], workspace, trace)
            host.initialize()
            effective = host.request('config/read', {'cwd': str(workspace), 'includeLayers': False})['config']
            report['effective_config'] = check_effective(effective, overrides)
            del inherited, effective
            started = host.request('thread/start', {'cwd': str(workspace), 'ephemeral': True,
                                   'sandbox': 'read-only', 'approvalPolicy': 'on-request', 'approvalsReviewer': 'user',
                                   'config': overrides})
            thread_id = started['thread']['id']
            report['thread'] = {'ephemeral': started['thread']['ephemeral'],
                               'path_is_null': started['thread']['path'] is None,
                               'sandbox': started['sandbox']['type'], 'approval_policy': started['approvalPolicy'],
                               'approvals_reviewer': started['approvalsReviewer'],
                               'model': started['model'], 'effort': started.get('reasoningEffort')}
            if (report['thread']['ephemeral'], report['thread']['path_is_null'], report['thread']['sandbox'],
                    report['thread']['approval_policy'], report['thread']['approvals_reviewer']) != (True, True, 'readOnly', 'on-request', 'user'):
                raise ValueError('thread_isolation_mismatch')
            host.wait_notification(lambda e: e['method'] == 'mcpServer/startupStatus/updated' and
                                   e['params'].get('threadId') == thread_id and e['params'].get('name') == 'acr' and
                                   e['params'].get('status') == 'ready')
            observed = read_mcp(trace_path)
            starts = [e['value'] for e in observed if e['kind'] == 'start']
            for value in starts:
                bridge_ids[value['pid']] = value['started']
            if len(starts) != 1 or not all(bridge_ids.values()):
                raise ValueError('mcp_connection_count')
            for tool, arguments in (('list_files', {}), ('read_file', {'path': 'plan.py'})):
                reply = host.request('mcpServer/tool/call', {'threadId': thread_id, 'server': 'acr', 'tool': tool, 'arguments': arguments})
                if reply.get('isError'):
                    raise ValueError('preflight_tool_failed')
                value = json.loads(reply['content'][0]['text'])
                if value != ({'files': ['plan.py']} if tool == 'list_files' else {'content': (workspace / 'plan.py').read_text()}):
                    raise ValueError('preflight_tool_content_mismatch')
            observed = read_mcp(trace_path)
            requests = [e['value'] for e in observed if e['kind'] == 'request']
            responses = [e['value'] for e in observed if e['kind'] == 'response']
            list_ids = [r['id'] for r in requests if r.get('method') == 'tools/list']
            catalogs = [r['result']['tools'] for r in responses if r.get('id') in list_ids]
            if catalogs != [TOOLS]:
                raise ValueError('catalog_mismatch')
            ready = [e['params']['name'] for e in host.notifications if e['method'] == 'mcpServer/startupStatus/updated'
                     and e['params'].get('threadId') == thread_id and e['params'].get('status') == 'ready']
            if ready != ['acr']:
                raise ValueError('unrelated_mcp_ready')
            report['catalog'] = {'tools': [t['name'] for t in catalogs[0]], 'sha256': digest(catalogs[0]),
                                 'initialize_requests': sum(r.get('method') == 'initialize' for r in requests),
                                 'tools_list_requests': len(list_ids), 'bridge_starts': len(starts),
                                 'read_calls': [r['params']['name'] for r in requests if r.get('method') == 'tools/call']}
            report['checks']['one_connection'] = (report['catalog']['initialize_requests'] == 1 and
                len([e for e in observed if e['kind'] == 'start']) == 1 and
                all(identity(pid) == born for pid, born in bridge_ids.items()))
            report['checks']['checkpoint_unchanged'] = source_before == file_hash(workspace / 'plan.py')
            report['checks']['only_acr_ready'] = True
            report['checks']['thread_isolation'] = True
            report['checks']['effective_overrides'] = True
            if not all(report['checks'].values()):
                raise ValueError('preflight_check_failed')
        report['checks']['candidate_cleaned'] = not Path(temporary).exists()
        report['status'] = 'completed'
    except (Exception, KeyboardInterrupt) as error:
        # Public report records controlled category text, never RPC error bodies.
        report['status'] = 'failed'
        report['error'] = str(error) if isinstance(error, (ValueError, RuntimeError, TimeoutError)) else type(error).__name__
    finally:
        # Even initialization failures and early MCP readiness failures clean only
        # children observed in this dedicated process/trace, never global Codex.
        if host:
            report['app_server_exit_code'] = host.close()
        if trace:
            trace.close()
        for event in read_mcp(trace_path):
            if event['kind'] == 'start' and event['value']['pid'] not in bridge_ids:
                pid = event['value']['pid']
                bridge_ids[pid] = event['value']['started']
        report['checks']['bridges_cleaned'] = cleanup_observed(bridge_ids)
        sent = [event['message']['method'] for path in (private / 'discovery.jsonl', private / 'app-server.jsonl')
                if path.exists() for event in map(json.loads, path.read_text().splitlines())
                if event.get('direction') == 'send']
        report['rpc_methods'] = sorted(set(sent))
        report['model_requests'] = sum(method in ('turn/start', 'thread/compact/start') for method in sent)
        report['checks']['no_model_requests'] = report['model_requests'] == 0
        report['config_sha256_after'] = file_hash(config_path)
        report['checks']['config_unchanged'] = before == report['config_sha256_after']
        report['elapsed_seconds'] = round(time.monotonic() - started_at, 3)
        if not all(report['checks'].values()):
            report['status'] = 'failed'
        result = PrivateTrace(private / 'result.json')
        result.append(report)
        result.close()
    return report
