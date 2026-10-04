from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.native import Phase, native_plan
from context_regression.native_approval import approve_fixture
from context_regression.native_run import exercise_pairs, public_report, reset
from test_regression import direct_checks
from visible_fixtures import SOLUTIONS


class FakeSession:
    def __init__(self, workspace, failure=None):
        self.workspace, self.failure = workspace, failure
        self.threads, self.events, self.inputs = {}, [], []

    def new_thread(self, label, source=None, last_turn=None):
        self.events.append(('fork' if source else 'start', label, source, last_turn))
        turns = deepcopy(self.threads[source]['turns']) if source else []
        if source and self.failure == 'fork-content':
            turns[-1]['items'][0]['text'] = 'wrong history'
        thread = {'id': label, 'forkedFromId': source, 'turns': turns, 'status': {'type': 'idle'}}
        self.threads[label] = thread
        return deepcopy(thread)

    def read(self, thread_id):
        return deepcopy(self.threads[thread_id])

    def check_tools(self, thread_id):
        return {'catalog_sha256': 'same', 'same_bridge_identity': True}

    def phase(self, kind, thread_id, text=None, previous=None):
        self.events.append((kind, thread_id, previous))
        if kind in ('seed', 'compact'):
            self.assert_checkpoint_unmodified()
        if kind == 'continuation':
            self.assert_checkpoint_unmodified()
            version = 'a' if thread_id.startswith('A') else 'b'
            (self.workspace / 'plan.py').write_text(SOLUTIONS['visible-policy-' + version])
            self.inputs.append(text)
        turn_id = thread_id + '.' + kind
        self.threads[thread_id]['turns'].append({'id': turn_id, 'status': 'completed', 'items': [{'id': 'generated', 'type': 'agentMessage', 'text': text or 'compact'}]})
        status = 'completed'
        if kind == 'compact' and self.failure == 'ack-only':
            status = 'phase_timeout'
        if kind == 'continuation' and self.failure == 'auto-compact':
            status = 'comparison_contaminated'
        if kind == 'seed' and self.failure == 'seed-write':
            (self.workspace / 'plan.py').write_text('changed')
        return {'kind': kind, 'thread_id': thread_id, 'turn_id': turn_id, 'status': status,
                'usage': None, 'compaction_item_ids': ['private-item'] if kind == 'compact' else [], 'tool_calls': 0}

    def assert_checkpoint_unmodified(self):
        from context_regression.tasks import BUILTIN_TASKS
        assert (self.workspace / 'plan.py').read_bytes() == (BUILTIN_TASKS / 'visible-policy-a/snapshot/plan.py').read_bytes()


class NativeRunTests(unittest.TestCase):
    def test_full_fixed_graph_reset_and_independent_cross_scores(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            workspace, private = root / 'candidate', root / 'private'
            private.mkdir()
            session = FakeSession(workspace)
            report = {'status': 'running', 'pairs': []}
            verified_paths = []
            def verify(task, candidate, mode):
                verified_paths.append(candidate)
                return direct_checks(task, candidate, mode)
            exercise_pairs(session, workspace, private, report, verify)
            phases = [(e[0], e[1]) for e in session.events if e[0] not in ('start', 'fork')]
            self.assertEqual(phases, [('seed','A.seed'),('continuation','A.control'),('compact','A.native-compact'),('continuation','A.native-compact'),
                                     ('seed','B.seed'),('compact','B.native-compact'),('continuation','B.native-compact'),('continuation','B.control')])
            self.assertEqual(len(session.threads), 6)
            for prefix in ('A', 'B'):
                forks = [e for e in session.events if e[0]=='fork' and e[1].startswith(prefix)]
                self.assertEqual(len(forks), 2)
                self.assertTrue(all(e[2:] == (prefix+'.seed', prefix+'.seed.seed') for e in forks))
                first_action = next(i for i,e in enumerate(session.events) if e[0] in ('compact','continuation') and e[1].startswith(prefix))
                self.assertTrue(all(session.events.index(e) < first_action for e in forks))
            self.assertEqual(session.inputs, [native_plan()['pairs'][0]['request']] * 4)
            self.assertEqual(verified_paths, [workspace] * 8)
            self.assertTrue(all(a['classification']=='requested_policy' and a['shared_rules_pass'] for p in report['pairs'] for a in p['arms']))
            public = public_report(report)
            self.assertNotIn('private-item', str(public))
            self.assertTrue(all(p['seed']['turn'].endswith('.turn') for p in public['pairs']))

    def test_first_protocol_failure_stops_batch_without_retry(self):
        for failure, message in [('fork-content','fork_boundary_mismatch'),('ack-only','compaction_capability_gate'),
                                 ('auto-compact','comparison_contaminated'),('seed-write','seed_modified_checkpoint')]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                root = Path(root);private = root/'private';private.mkdir()
                session = FakeSession(root/'candidate', failure)
                report = {'pairs': []}
                with self.assertRaisesRegex(ValueError, message):
                    exercise_pairs(session, root/'candidate', private, report, direct_checks)
                self.assertFalse(any(e[1].startswith('B') for e in session.events))
                self.assertLessEqual(sum(e[0]=='compact' for e in session.events), 1)

    def test_reset_keeps_live_child_cwd_and_restores_only_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / 'candidate'
            expected = reset(workspace)
            inode = workspace.stat().st_ino
            (workspace / 'extra').mkdir()
            (workspace / 'extra' / 'discard').write_text('old')
            source = "import os,sys; print('ready',flush=True); sys.stdin.readline(); print(os.getcwd(),flush=True)"
            with subprocess.Popen([sys.executable, '-u', '-c', source], cwd=workspace,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
                self.assertEqual(child.stdout.readline().strip(), 'ready')
                self.assertEqual(reset(workspace), expected)
                output, _ = child.communicate('check\n', timeout=2)
                self.assertEqual(child.returncode, 0)
                self.assertEqual(output.strip(), str(workspace.resolve()))
            self.assertEqual(workspace.stat().st_ino, inode)
            self.assertEqual([p.name for p in workspace.iterdir()], ['plan.py'])

    def test_cli_requires_explicit_model_opt_in(self):
        with patch('context_regression.cli.run_native_smoke') as run, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(['native-run'])
        self.assertEqual(error.exception.code, 2)
        run.assert_not_called()


class ApprovalTests(unittest.TestCase):
    def request(self, tool, args):
        return {'id': 50, 'method':'mcpServer/elicitation/request','params': {
            'threadId':'thread','turnId':'turn','serverName':'acr','mode':'form',
            'message':f'Allow the acr MCP server to run tool "{tool}"?',
            'requestedSchema':{'type':'object','properties':{}},
            '_meta':{'codex_approval_kind':'mcp_tool_call','tool_params':args,'persist':['session','always']}}}

    def phase(self, tool, args):
        p = Phase('continuation','thread',1,0)
        p.turn_id='turn'
        p.pending_tools={'call':{'id':'call','server':'acr','tool':tool,'arguments':args}}
        return p

    def test_four_exact_single_call_approvals_without_persistence(self):
        with tempfile.TemporaryDirectory() as root:
            workspace=Path(root);(workspace/'plan.py').write_text('old')
            for tool,args in [('list_files',{}),('check',{}),('read_file',{'path':'plan.py'}),('write_file',{'path':'plan.py','content':'new'})]:
                approved=set();p=self.phase(tool,args);event=self.request(tool,args)
                self.assertEqual(approve_fixture(event,p,workspace,approved),{'action':'accept','content':{}})
                with self.assertRaises(ValueError):
                    approve_fixture(event,p,workspace,approved)
            self.assertEqual((workspace/'plan.py').read_text(),'old')

    def test_wrong_scope_arguments_multiple_pending_and_noncontinuation_refused(self):
        with tempfile.TemporaryDirectory() as root:
            workspace=Path(root);(workspace/'plan.py').write_text('old')
            args={'path':'plan.py','content':'new'};baseline=self.request('write_file',args)
            changes=[lambda e:e['params'].update(threadId='other'),lambda e:e['params'].update(turnId=None),
                     lambda e:e['params'].update(serverName='other'),lambda e:e['params'].update(mode='url'),
                     lambda e:e['params']['requestedSchema'].update(properties={'password':{'type':'string'}}),
                     lambda e:e['params']['_meta'].update(tool_params={'path':'../oracle.py','content':'bad'}),
                     lambda e:e['params']['_meta'].update(tool_params={**args,'extra':True}),
                     lambda e:e['params']['_meta'].update(codex_approval_kind='other')]
            for change in changes:
                event=deepcopy(baseline);change(event)
                with self.assertRaises(ValueError): approve_fixture(event,self.phase('write_file',args),workspace,set())
            for kind in ('seed','compact'):
                p=self.phase('write_file',args);p.kind=kind
                with self.assertRaises(ValueError): approve_fixture(baseline,p,workspace,set())
            p=self.phase('write_file',args);p.pending_tools['second']={'id':'second'}
            with self.assertRaises(ValueError): approve_fixture(baseline,p,workspace,set())
            (workspace/'plan.py').unlink();(workspace/'plan.py').symlink_to(workspace/'outside')
            with self.assertRaises(ValueError): approve_fixture(baseline,self.phase('write_file',args),workspace,set())
