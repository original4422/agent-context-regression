import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from context_regression.native import isolated_config
from context_regression.native_client import AppServer
from context_regression.native_preflight import PrivateTrace, check_effective, cleanup_observed, identity

PEER = '''
import json,sys,time
mode=sys.argv[1]
for line in sys.stdin:
 q=json.loads(line)
 if q['method']=='initialized': continue
 if mode=='hang': continue
 if mode=='approval' and q['method']!='initialize':
  print(json.dumps({'id':500,'method':'mcpServer/elicitation/request','params':{}}),flush=True);continue
 if q['method']=='config/read':
  if mode=='late': time.sleep(.15)
  value={'error':{'message':'DO_NOT_RECORD_CONFIG_SECRET'}} if mode=='error' else {'result':{'config':{'secret':'DO_NOT_RECORD_CONFIG_SECRET'}}}
  print(json.dumps({'id':q['id'],**value}),flush=True)
 else:
  print(json.dumps({'id':q['id'],'result':{}}),flush=True)
'''


class PreflightTests(unittest.TestCase):
    def host(self, root, mode):
        trace = PrivateTrace(Path(root) / 'events.jsonl')
        return AppServer([sys.executable, '-u', '-c', PEER, mode], root, trace), trace

    def test_config_response_and_error_never_enter_private_log(self):
        for mode in ('normal', 'error', 'late'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                host, trace = self.host(root, mode)
                try:
                    host.initialize()
                    if mode == 'normal':
                        self.assertEqual(host.request('config/read', {})['config']['secret'], 'DO_NOT_RECORD_CONFIG_SECRET')
                    elif mode == 'error':
                        with self.assertRaisesRegex(RuntimeError, '^rpc_error:config/read$'):
                            host.request('config/read', {})
                    else:
                        with self.assertRaises(TimeoutError):
                            host.request('config/read', {}, timeout=.02)
                        # A later request drains the delayed sensitive response.
                        self.assertEqual(host.request('thread/start', {}, timeout=2), {})
                finally:
                    host.close()
                    trace.close()
                path = Path(root) / 'events.jsonl'
                self.assertNotIn('DO_NOT_RECORD', path.read_text())
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                config_id = next(e['message']['id'] for e in map(json.loads, path.read_text().splitlines())
                                 if e['direction'] == 'send' and e['message']['method'] == 'config/read')
                self.assertFalse(any(e['direction'] == 'receive' and e['message'].get('id') == config_id
                                     for e in map(json.loads, path.read_text().splitlines())))

    def test_unexpected_preflight_approval_closes_without_accepting(self):
        with tempfile.TemporaryDirectory() as root:
            host, trace = self.host(root, 'approval')
            try:
                host.initialize()
                with self.assertRaisesRegex(RuntimeError, 'unexpected_server_request'):
                    host.request('thread/start', {})
                self.assertIsNotNone(host.process.poll())
                self.assertNotIn('accept', (Path(root) / 'events.jsonl').read_text())
            finally:
                host.close()
                trace.close()

    def test_unconfirmed_cleanup_still_attempts_remaining_owned_pids(self):
        with patch('context_regression.native_preflight.stop_observed', side_effect=[False, True]) as stop:
            self.assertFalse(cleanup_observed({100: 'first-start', 200: 'second-start'}))
        self.assertEqual([call.args for call in stop.call_args_list], [(100, 'first-start'), (200, 'second-start')])

    def test_initialization_timeout_reaps_owned_process(self):
        with tempfile.TemporaryDirectory() as root:
            host, trace = self.host(root, 'hang')
            try:
                with self.assertRaises(TimeoutError):
                    host.initialize(.1)
                self.assertIsNotNone(host.process.poll())
                self.assertIsNone(identity(host.process.pid))
            finally:
                host.close()
                trace.close()

    def test_preflight_rpc_surface_excludes_model_and_status_calls(self):
        with tempfile.TemporaryDirectory() as root:
            host, trace = self.host(root, 'normal')
            try:
                for method in ('turn/start', 'thread/compact/start', 'mcpServerStatus/list', 'thread/fork'):
                    with self.assertRaisesRegex(ValueError, 'unsupported_preflight_method'):
                        host.request(method, {})
                self.assertEqual((Path(root) / 'events.jsonl').read_text(), '')
            finally:
                host.close()
                trace.close()

    def test_effective_config_checks_all_overrides_and_exports_allowlist(self):
        overrides, _ = isolated_config({'mcp_servers': {'unrelated': {}}, 'plugins': {'demo@market': {}}}, ['/python', '/bridge'], None, 'low')
        config = {'secret': 'DO_NOT_EXPORT'}
        for key, value in overrides.items():
            pieces = key.split('.')
            target = config
            for name in pieces[:-1]:
                target = target.setdefault(name, {})
            target[pieces[-1]] = value
        result = check_effective(config, overrides)
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(result))
        self.assertEqual(result['unrelated_mcp_disabled'], 1)
        config['features']['apps'] = True
        with self.assertRaisesRegex(ValueError, 'effective_config_mismatch'):
            check_effective(config, overrides)
        with self.assertRaisesRegex(ValueError, 'inherited_hooks_require_review'):
            isolated_config({'hooks': {'command':'must not run'}}, ['/python'], None, 'low')
