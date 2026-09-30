from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.native_accept import EXIT_CODES, accept_result

ROOT = Path(__file__).resolve().parents[1]


class WorkAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.measured = json.loads((ROOT / 'reports/native-tool-checkpoint.json').read_text())

    def gate(self, value):
        return accept_result(value, 'tool-checkpoint')

    def test_public_and_private_fields_are_read_only_without_execution(self):
        private = deepcopy(self.measured)
        pair = private['pairs'][0]
        for phase in [pair['work']] + [p for a in pair['arms'] for p in a['phases']]:
            phase['turn_id'] = phase.pop('turn')
            phase['completed_tools'] = [{'id': 'PRIVATE-IGNORE'}]
        private['threads'] = {'PRIVATE-IGNORE': {'path': '/private/example'}}
        for value in (self.measured, private):
            before = deepcopy(value)
            with patch('subprocess.Popen') as process, patch('context_regression.verify.evaluate') as oracle, \
                    patch('pathlib.Path.read_text') as read, patch('pathlib.Path.read_bytes') as read_bytes:
                outcome = self.gate(value)
                self.assertEqual(outcome['verdict'], 'accepted')
                self.assertEqual((outcome['expected_candidates'], outcome['observed_candidates']), (2, 2))
                self.assertNotIn('PRIVATE', json.dumps(outcome))
                for mock in (process, oracle, read, read_bytes):
                    mock.assert_not_called()
            self.assertEqual(value, before)
        # Repeated valid operations are permitted up to the work budget.
        value = deepcopy(self.measured)
        value['pairs'][0]['work']['tool_calls'] = 8
        value['pairs'][0]['work_observation']['completed_tools'] = [
            'list_files', 'read_file', 'read_file', 'write_file', 'check', 'read_file', 'write_file', 'check']
        self.assertEqual(self.gate(value)['verdict'], 'accepted')

    def test_final_failures_ignore_summaries_and_keep_sampling_exit_zero(self):
        value = deepcopy(self.measured)
        # The existing fake 'behavior' case loses these method gates in both arms.
        for arm in value['pairs'][0]['arms']:
            for check in arm['verification']['checks']:
                if check['name'] in ('rejected_post_retry', 'exact_allowed_methods'):
                    check['passed'] = False
            arm.update(classification='task_passed')
            arm['verification']['passed'] = True
        with patch('context_regression.cli.run_native_smoke', return_value=value), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as exited:
                main(['native-run', '--scenario', 'tool-checkpoint', '--allow-model', '--private-dir', '/unused-mocked'])
        self.assertEqual(exited.exception.code, 0)
        outcome = self.gate(value)
        self.assertEqual(outcome['verdict'], 'behavior_failed')
        self.assertEqual(len(outcome['reasons']), 4)
        self.assertTrue(all(r['code'] == 'final_check_failed' for r in outcome['reasons']))
        value = deepcopy(self.measured)
        pair = value['pairs'][0]
        pair.update(work_outcome='prelude_behavior_failed', comparison_established=False)
        pair['work_observation'].update(last_check_after_last_write=False, history_matches_completed_calls=False)
        for arm in pair['arms']:
            arm.update(classification='task_failed'); arm['verification']['passed'] = False
        self.assertEqual(self.gate(value)['verdict'], 'accepted')

    def test_failed_work_precondition_has_specific_reason_and_no_candidates(self):
        # Matches the existing fake prelude-finished failure prefix: all six
        # checks pass too early, and the runner never establishes either arm.
        value = deepcopy(self.measured); value['status'] = 'failed'
        pair = value['pairs'][0]; pair.update(arms=[], work_outcome='prelude_behavior_failed', comparison_established=False)
        pair.pop('work_observation'); pair.pop('boundary_sha256')
        for check in pair['work_verification']['checks']:
            check['passed'] = True
        outcome = self.gate(value)
        self.assertEqual(outcome['verdict'], 'run_incomplete')
        self.assertEqual(outcome['observed_candidates'], 0)
        self.assertEqual([r['check'] for r in outcome['reasons'] if r['code'] == 'work_precondition_failed'],
                         ['rate_limit', 'case_insensitive_method'])
        # An exception does not count as the expected false result.
        value = deepcopy(self.measured)
        value['pairs'][0]['work_verification']['checks'][0]['error'] = 'PRIVATE-ERROR'
        outcome = self.gate(value)
        self.assertEqual(outcome['verdict'], 'run_incomplete')
        self.assertNotIn('PRIVATE', json.dumps(outcome))

    def test_legal_prefixes_and_incomplete_evidence_return_three(self):
        mutations = [lambda d: d.update(status='failed', pairs=[], checks={}),
                     lambda d: d['pairs'][0].update(arms=d['pairs'][0]['arms'][:1]),
                     lambda d: d['pairs'][0]['arms'][1].update(phases=d['pairs'][0]['arms'][1]['phases'][:1]),
                     lambda d: d['pairs'][0]['arms'][1].pop('verification'),
                     lambda d: d['pairs'][0]['arms'][0].update(checkpoint_sha256='different-recorded-value'),
                     lambda d: d['pairs'][0].pop('work_checkpoint_sha256'),
                     lambda d: d['pairs'][0]['work'].update(tool_calls=9),
                     lambda d: d['pairs'][0]['work'].update(status='work_pending_tools'),
                     lambda d: d['pairs'][0]['work_observation'].update(completed_tools=['read_file', 'check', 'write_file']),
                     lambda d: d['pairs'][0]['work_observation'].update(completed_tools=['read_file', 'write_file']),
                     lambda d: d['pairs'][0]['work_observation']['check_results'][0].update(passed=True),
                     lambda d: d['pairs'][0]['arms'][1]['phases'][0].update(evidence=[{'event': 'rpc_ack'}]),
                     lambda d: d['checks'].update(fixture_unchanged=False)]
        for mutate in mutations:
            value = deepcopy(self.measured); mutate(value)
            self.assertEqual(self.gate(value)['verdict'], 'run_incomplete', mutate)
        for work in ({}, {'kind': None, 'status': None, 'tool_calls': None, 'terminal': None, 'cancellation': None}):
            value = deepcopy(self.measured); value['status'] = 'failed'
            value['pairs'] = [{'case_id': 'retry-work', 'task': 'retry-method-policy', 'work': work, 'arms': []}]
            self.assertEqual(self.gate(value)['verdict'], 'run_incomplete')
        value = deepcopy(self.measured); value['pairs'][0]['arms'].pop()
        value['pairs'][0]['arms'][0]['verification']['checks'][0]['passed'] = False
        self.assertEqual(self.gate(value)['verdict'], 'run_incomplete')

    def test_malformed_consumed_fields_return_two_even_in_partial_run(self):
        mutations = [lambda d: d['plan'].update(work_turns=True),
                     lambda d: d['plan']['pairs'][0].update(task='other'),
                     lambda d: d['pairs'].append(deepcopy(d['pairs'][0])),
                     lambda d: d['pairs'][0]['arms'].__setitem__(1, deepcopy(d['pairs'][0]['arms'][0])),
                     lambda d: d['pairs'][0]['work_observation'].update(completed_tools=['unknown-tool']),
                     lambda d: d['pairs'][0]['work_observation']['check_results'].append({'name': 'rate_limit', 'passed': False}),
                     lambda d: d['pairs'][0]['work_verification']['checks'].pop(),
                     lambda d: d['pairs'][0]['arms'][0]['verification']['checks'][0].update(passed=1),
                     lambda d: d['pairs'][0]['arms'][0]['verification']['checks'][0].update(name='unknown-check'),
                     lambda d: d['pairs'][0]['arms'][0].update(checkpoint_sha256=False)]
        for mutate in mutations:
            value = deepcopy(self.measured); value['status'] = 'failed'; mutate(value)
            self.assertEqual(self.gate(value)['verdict'], 'invalid_result', mutate)

    def test_cli_all_codes_duplicate_key_and_input_unchanged(self):
        failed = deepcopy(self.measured); failed['pairs'][0]['arms'][0]['verification']['checks'][0]['passed'] = False
        partial = deepcopy(self.measured); partial['pairs'] = []
        duplicate = json.dumps(self.measured).replace('"passed": true', '"passed": false, "passed": true', 1)
        cases = [(json.dumps(self.measured), 0), (json.dumps(failed), 1), ('not JSON', 2),
                 (json.dumps(partial), 3), (duplicate, 2)]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'saved.json'
            for text, code in cases:
                path.write_text(text); before = path.read_bytes(); output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as exited:
                    main(['native-accept', str(path), '--scenario', 'tool-checkpoint'])
                self.assertEqual(exited.exception.code, code)
                result = json.loads(output.getvalue())
                self.assertEqual(result['expected_candidates'], 2)
                self.assertEqual(EXIT_CODES[result['verdict']], code)
                self.assertEqual(path.read_bytes(), before)
