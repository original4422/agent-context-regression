from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.native import Phase, native_plan
from context_regression.native_approval import approve_fixture
from context_regression.native_run import checkpoint, exercise_pairs, public_report, reset
from context_regression.native_work import INTERMEDIATE, TASK
from context_regression.tasks import BUILTIN_TASKS
import test_native_run
from test_regression import direct_checks, SOLUTIONS

FINAL = SOLUTIONS[TASK]
PARTIAL = FINAL.replace('429,', '')
REGRESSED = 'def should_retry(status, method):\n    return status in {429,500,502,503,504}\n'


def item(tool, args, value):
    return {'id': 'private-' + tool, 'type': 'mcpToolCall', 'server': 'acr', 'tool': tool,
            'arguments': args, 'status': 'completed', 'error': None,
            'result': {'content': [{'type': 'text', 'text': json.dumps(value)}]}}


class WorkSession(test_native_run.FakeSession):
    def __init__(self, workspace, failure=None):
        super().__init__(workspace, failure)
        self.starts = []

    def phase(self, kind, thread_id, text=None, previous=None):
        self.events.append((kind, thread_id, previous))
        calls = []
        if kind == 'work':
            before = (self.workspace / 'retry.py').read_text()
            source = FINAL if self.failure == 'prelude-finished' else PARTIAL
            (self.workspace / 'retry.py').write_text(source)
            public = direct_checks(BUILTIN_TASKS / TASK, self.workspace, 'public')
            calls = [item('read_file', {'path': 'retry.py'}, {'content': before}),
                     item('write_file', {'path': 'retry.py', 'content': source}, {'written': 'retry.py'}),
                     item('check', {}, public)]
            if self.failure == 'check-before-write':
                calls[1], calls[2] = calls[2], calls[1]
        else:
            self.starts.append((kind, thread_id, (self.workspace / 'retry.py').read_bytes(), self.workspace.stat().st_ino))
            if kind == 'continuation':
                self.inputs.append(text)
                (self.workspace / 'retry.py').write_text(REGRESSED if self.failure == 'behavior' else FINAL)
        turn_id = thread_id + '.' + kind
        history = deepcopy(calls)
        if kind == 'work' and self.failure == 'tool-history':
            history[-1]['result']['content'][0]['text'] = 'changed'
        self.threads[thread_id]['turns'].append({'id': turn_id, 'status': 'completed', 'items': history})
        if kind == 'compact' and self.failure == 'compact-write':
            (self.workspace / 'retry.py').write_text('changed')
        return {'kind': kind, 'thread_id': thread_id, 'turn_id': turn_id,
                'status': 'phase_timeout' if kind == 'compact' and self.failure == 'ack-only' else 'completed',
                'tool_calls': len(calls), 'completed_tools': calls}


class NativeWorkTests(unittest.TestCase):
    def graph(self, root, failure=None):
        workspace, private = root / 'candidate', root / 'private'
        private.mkdir()
        session = WorkSession(workspace, failure)
        report = {'status': 'running', 'plan': native_plan(scenario='tool-checkpoint'), 'pairs': []}
        return session, workspace, private, report

    def test_plan_and_cli_accept_work_result(self):
        with patch('subprocess.Popen', side_effect=AssertionError('execution')), redirect_stdout(io.StringIO()) as output:
            main(['native-plan', '--scenario', 'tool-checkpoint'])
        plan = json.loads(output.getvalue())
        self.assertEqual((plan['work_turns'], plan['compactions'], plan['continuations']), (1, 1, 2))
        self.assertEqual(plan['model_phase_timeout_budget_seconds'], 630)
        self.assertEqual(plan['work_tool_budget'], 8)
        self.assertNotIn('429', plan['pairs'][0]['request'])
        self.assertNotIn('POST', plan['pairs'][0]['request'])
        with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as error:
            report = Path(__file__).resolve().parents[1] / 'reports/native-tool-checkpoint.json'
            main(['native-accept', str(report), '--scenario', 'tool-checkpoint'])
        self.assertEqual(error.exception.code, 0)
        self.assertEqual(json.loads(output.getvalue())['expected_candidates'], 2)

    def test_reference_discriminates_partial_and_lost_work(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            for source, expected in ((PARTIAL, INTERMEDIATE), (FINAL, {k: True for k in INTERMEDIATE})):
                (workspace / 'retry.py').write_text(source)
                value = direct_checks(BUILTIN_TASKS / TASK, workspace, 'oracle')
                self.assertEqual({c['name']: c['passed'] for c in value['checks']}, expected)
            (workspace / 'retry.py').write_text(REGRESSED)
            self.assertTrue(direct_checks(BUILTIN_TASKS / TASK, workspace, 'public')['passed'])
            bad = direct_checks(BUILTIN_TASKS / TASK, workspace, 'oracle')
            self.assertEqual([c['name'] for c in bad['checks'] if not c['passed']],
                             ['rejected_post_retry', 'exact_allowed_methods'])

    def test_four_phase_graph_preserves_exact_work_bytes_for_both_forks(self):
        with tempfile.TemporaryDirectory() as root:
            session, workspace, private, report = self.graph(Path(root))
            exercise_pairs(session, workspace, private, report, direct_checks)
            actions = [e[0] for e in session.events]
            self.assertEqual(actions, ['start', 'work', 'fork', 'fork', 'continuation', 'compact', 'continuation'])
            self.assertEqual(len(session.threads), 3)
            self.assertTrue(all(e[2:] == ('retry-work.work', 'retry-work.work.work') for e in session.events if e[0] == 'fork'))
            self.assertTrue(all(s[2] == PARTIAL.encode() for s in session.starts))
            self.assertEqual(len({s[3] for s in session.starts}), 1)
            self.assertEqual(session.inputs, [report['plan']['pairs'][0]['request']] * 2)
            saved = private / 'work-checkpoint'
            self.assertEqual((saved / 'retry.py').read_bytes(), PARTIAL.encode())
            row = report['pairs'][0]
            self.assertNotEqual(checkpoint(saved), checkpoint(workspace))
            self.assertTrue(row['comparison_established'])
            self.assertEqual(row['work_checkpoint_sha256'], checkpoint(saved))
            self.assertTrue(all(a['checkpoint_sha256'] == checkpoint(saved) and a['verification']['passed'] for a in row['arms']))
            public = public_report(report)
            self.assertNotIn('private-read_file', json.dumps(public))
            self.assertNotIn('completed_tools', public['pairs'][0]['work'])
            self.assertNotIn('seed', public['pairs'][0])
            self.assertNotIn('control_both_policies_pass', public)

    def test_precondition_failure_stops_without_forks_and_preserves_candidate(self):
        with tempfile.TemporaryDirectory() as root:
            session, workspace, private, report = self.graph(Path(root), 'prelude-finished')
            with self.assertRaisesRegex(ValueError, 'work_checkpoint_precondition_failed'):
                exercise_pairs(session, workspace, private, report, direct_checks)
            self.assertEqual([e[0] for e in session.events], ['start', 'work'])
            self.assertEqual((private / 'work-checkpoint/retry.py').read_bytes(), FINAL.encode())
            self.assertEqual(report['pairs'][0]['work_outcome'], 'prelude_behavior_failed')
            self.assertFalse(public_report(report)['pairs'][0]['comparison_established'])

    def test_bad_tool_history_fork_and_compaction_stop_without_retry(self):
        for failure, message in [('check-before-write', 'work_read_write_check_order'), ('tool-history', 'work_tool_history_mismatch'),
                                 ('fork-content', 'fork_boundary_mismatch'), ('compact-write', 'compaction_modified_checkpoint'),
                                 ('ack-only', 'compaction_capability_gate')]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                session, workspace, private, report = self.graph(Path(root), failure)
                with self.assertRaisesRegex(ValueError, message):
                    exercise_pairs(session, workspace, private, report, direct_checks)
                self.assertEqual(sum(e[0] == 'work' for e in session.events), 1)
                self.assertLessEqual(sum(e[0] == 'continuation' for e in session.events), 1)

    def test_behavior_failure_still_completes_both_arms(self):
        with tempfile.TemporaryDirectory() as root:
            session, workspace, private, report = self.graph(Path(root), 'behavior')
            exercise_pairs(session, workspace, private, report, direct_checks)
            self.assertEqual([a['classification'] for a in report['pairs'][0]['arms']], ['task_failed'] * 2)
            self.assertEqual(sum(e[0] == 'continuation' for e in session.events), 2)

    def test_work_budget_pending_terminal_and_scoped_approval(self):
        p = Phase('work', 'thread', 1, 0)
        p.consume({'id': 1, 'result': {'turn': {'id': 'turn'}}}, 1)
        call = item('read_file', {'path': 'retry.py'}, {'content': 'source'})
        def event(method, **extra):
            return {'method': method, 'params': {'threadId': 'thread', 'turnId': 'turn', **extra}}
        p.consume(event('item/started', item=call), 2)
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root); (workspace / 'retry.py').write_text('source')
            request = test_native_run.ApprovalTests().request('read_file', {'path': 'retry.py'})
            with self.assertRaisesRegex(ValueError, 'out_of_scope'):
                approve_fixture(request, p, workspace, set())
            self.assertEqual(approve_fixture(request, p, workspace, set(), task=TASK), {'action': 'accept', 'content': {}})
        p.consume(event('turn/completed', turn={'id': 'turn', 'status': 'completed'}), 3)
        self.assertEqual(p.failure, 'work_pending_tools')
        p = Phase('work', 'thread', 1, 0); p.turn_id = 'turn'
        for n in range(9):
            p.consume(event('item/started', item={**call, 'id': str(n)}), n + 1)
            if n == 7:
                self.assertIsNone(p.failure)
        self.assertEqual(p.failure, 'tool_budget')
