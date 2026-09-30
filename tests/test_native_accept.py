from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.native_accept import EXIT_CODES, INTEGRITY, accept_result
from context_regression.native_run import public_report
import test_native_revision

ROOT = Path(__file__).resolve().parents[1]


class NativeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixed = json.loads((ROOT / 'reports/native-smoke.json').read_text())
        cls.revision = json.loads((ROOT / 'reports/native-revision.json').read_text())
        cls.failed_setup = json.loads((ROOT / 'reports/native-smoke-initial.json').read_text())

    def verdict(self, value, scenario='policy-revision'):
        return accept_result(value, scenario)['verdict']

    def test_published_reports_and_identity_variants_without_execution_or_io(self):
        for source, scenario in ((self.fixed, 'fixed-policy'), (self.revision, 'policy-revision')):
            value = deepcopy(source)
            for pair in value['pairs']:
                for arm in pair['arms']:
                    arm['thread_id'] = 'PRIVATE-DO-NOT-OUTPUT'
                    arm.pop('thread')
                    for phase in arm['phases']:
                        phase['turn_id'] = phase.pop('turn')
                        phase['compaction_item_ids'] = ['PRIVATE-DO-NOT-OUTPUT']
            value['threads'] = {'PRIVATE-DO-NOT-OUTPUT': {'path': '/private/example'}}
            value['audit'] = {'ignored': 'PRIVATE-DO-NOT-OUTPUT'}
            before = deepcopy(value)
            with patch('subprocess.Popen') as process, patch('context_regression.verify.evaluate') as oracle, \
                    patch('context_regression.cli.run_native_smoke') as runner, patch('builtins.open') as opened:
                result = accept_result(value, scenario)
                self.assertEqual(result['verdict'], 'accepted')
                self.assertEqual(result['observed_candidates'], 4)
                self.assertNotIn('PRIVATE', json.dumps(result))
                for mock in (process, oracle, runner, opened):
                    mock.assert_not_called()
            self.assertEqual(value, before)

    def test_existing_fake_old_policy_keeps_sampling_zero_but_gate_fails(self):
        fake = test_native_revision.NativeRevisionTests()
        try:
            _, raw = fake.run_graph('old-policy')
            # FakeSession has no wire transport. Supply synthetic completion
            # fields solely for this static acceptance test, keeping its real
            # worker-computed old-policy verdicts unchanged.
            raw.update(status='completed', checks={k: True for k in (*INTEGRITY, 'fixture_unchanged')})
            for pair in raw['pairs']:
                for phase in [pair['seed'], pair['revision']] + [p for a in pair['arms'] for p in a['phases']]:
                    phase.update(terminal='completed', cancellation='not_requested')
                    if phase['kind'] == 'compact':
                        phase['evidence'] = [{'event': 'compaction_completed'}, {'event': 'turn_completed', 'status': 'completed'}]
            saved = public_report(raw)
            with patch('context_regression.cli.run_native_smoke', return_value=saved), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exit:
                    main(['native-run', '--scenario', 'policy-revision', '--allow-model', '--private-dir', '/unused-mocked'])
            self.assertEqual(exit.exception.code, 0)
            result = accept_result(saved, 'policy-revision')
            self.assertEqual(result['verdict'], 'behavior_failed')
            self.assertEqual(len(result['reasons']), 4)
            self.assertTrue(all(r['code'] == 'old_or_opposite_policy' for r in result['reasons']))
            self.assertEqual(EXIT_CODES[result['verdict']], 1)
        finally:
            fake.doCleanups()

    def test_detailed_behavior_wins_over_every_summary(self):
        for kind in ('shared', 'neither', 'old'):
            value = deepcopy(self.revision)
            arm = value['pairs'][0]['arms'][0]
            oracles = arm['cross_verification']
            if kind == 'shared':
                oracles['visible-policy-a']['checks'][0]['passed'] = False
            else:
                oracles['visible-policy-b']['checks'][-1]['passed'] = False
                oracles['visible-policy-a']['checks'][-1]['passed'] = kind == 'old'
            # All saved summaries continue claiming success; the gate ignores them.
            arm.update(classification='latest_policy', shared_rules_pass=True)
            for verdict in oracles.values():
                verdict['passed'] = True
            self.assertEqual(self.verdict(value), 'behavior_failed', kind)

    def test_actual_failed_setup_and_legal_partial_prefixes_are_incomplete(self):
        self.assertEqual(self.verdict(self.failed_setup, 'fixed-policy'), 'run_incomplete')
        before_pairs = deepcopy(self.failed_setup)
        before_pairs.update(pairs=[], checks={})
        self.assertEqual(self.verdict(before_pairs, 'fixed-policy'), 'run_incomplete')
        private_placeholder = deepcopy(self.failed_setup)
        private_placeholder['pairs'][0]['seed'] = {}
        self.assertEqual(self.verdict(private_placeholder, 'fixed-policy'), 'run_incomplete')
        mutations = [lambda d: d.update(pairs=d['pairs'][:1]),
                     lambda d: d['pairs'][1].update(arms=d['pairs'][1]['arms'][:1]),
                     lambda d: d['pairs'][0]['arms'][0].update(phases=[]),
                     lambda d: d['pairs'][0]['arms'][0].pop('cross_verification'),
                     lambda d: d['pairs'][0]['arms'][0]['cross_verification'].pop('visible-policy-a'),
                     lambda d: d['pairs'][0]['arms'][1]['phases'][0].update(evidence=[{'event':'rpc_ack'}]),
                     lambda d: d['pairs'][0]['arms'][0]['phases'][0].update(tool_calls=17),
                     lambda d: d['checks'].update(bridges_cleaned=False),
                     lambda d: d.update(status='running'), lambda d: d.update(status='failed')]
        for change in mutations:
            value = deepcopy(self.revision); change(value)
            with self.subTest(change=change):
                self.assertEqual(self.verdict(value), 'run_incomplete')
        value = deepcopy(self.revision)
        value['status'] = 'failed'
        value['pairs'][0]['arms'][0]['cross_verification']['visible-policy-b']['checks'][-1]['passed'] = False
        self.assertEqual(self.verdict(value), 'run_incomplete')

    def test_wrong_types_duplicate_unknown_and_incomplete_checks_are_invalid(self):
        mutations = [lambda d: d.pop('plan'), lambda d: d.update(pairs=None),
                     lambda d: d['plan'].update(protocol='unknown'),
                     lambda d: d['plan'].update(seeds=True),
                     lambda d: d['pairs'].__setitem__(1, deepcopy(d['pairs'][0])),
                     lambda d: d['pairs'][0]['arms'].__setitem__(1, deepcopy(d['pairs'][0]['arms'][0])),
                     lambda d: d['pairs'][0].update(task='visible-policy-a'),
                     lambda d: d['pairs'][0]['arms'][0]['phases'][0].update(tool_calls=True),
                     lambda d: d['pairs'][0]['arms'][0]['phases'][0].update(status=[]),
                     lambda d: d['checks'].update(config_unchanged='true')]
        for change in mutations:
            value = deepcopy(self.revision); change(value)
            self.assertEqual(self.verdict(value), 'invalid_result')
        for kind in ('missing', 'duplicate', 'unknown', 'string', 'error', 'both'):
            value = deepcopy(self.revision)
            checks = value['pairs'][0]['arms'][0]['cross_verification']['visible-policy-a']['checks']
            if kind == 'missing': checks.pop()
            elif kind == 'duplicate': checks.append(deepcopy(checks[0]))
            elif kind == 'unknown': checks[0]['name'] = 'unexpected'
            elif kind == 'string': checks[0]['passed'] = 'true'
            elif kind == 'error': checks[0]['error'] = 'private error not to echo'
            else: checks[-1]['passed'] = True
            result = accept_result(value, 'policy-revision')
            self.assertEqual(result['verdict'], 'invalid_result', kind)
            self.assertNotIn('private error', json.dumps(result))

    def test_cli_codes_and_input_bytes_unchanged(self):
        failed = deepcopy(self.revision)
        failed['pairs'][0]['arms'][0]['cross_verification']['visible-policy-b']['checks'][-1]['passed'] = False
        partial = deepcopy(self.revision); partial['pairs'] = []
        cases = [(json.dumps(self.revision), 0), (json.dumps(failed), 1), ('not json', 2), (json.dumps(partial), 3)]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'saved.json'
            for text, code in cases:
                path.write_text(text); before = path.read_bytes(); output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as exit:
                    main(['native-accept', str(path), '--scenario', 'policy-revision'])
                self.assertEqual(exit.exception.code, code)
                self.assertEqual(EXIT_CODES[json.loads(output.getvalue())['verdict']], code)
                self.assertEqual(path.read_bytes(), before)

    def test_cli_rejects_duplicate_json_keys_before_overwrite(self):
        saved = json.dumps(self.revision)
        cases = [saved.replace('"passed": true', '"passed": false, "passed": true', 1),
                 saved.replace('"status": "completed"', '"status": "failed", "status": "completed"', 1)]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'saved.json'
            for text in cases:
                self.assertNotEqual(text, saved)
                path.write_text(text); before = path.read_bytes(); output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(SystemExit) as exit:
                    main(['native-accept', str(path), '--scenario', 'policy-revision'])
                self.assertEqual(exit.exception.code, 2)
                self.assertEqual(json.loads(output.getvalue())['reasons'], [{'code': 'duplicate_json_key'}])
                self.assertEqual(path.read_bytes(), before)
