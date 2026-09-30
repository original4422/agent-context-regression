from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from context_regression.native import native_plan
from context_regression.native_run import exercise_pairs, public_report
from test_native_run import FakeSession
from test_regression import direct_checks
from visible_fixtures import SOLUTIONS


class RevisionSession(FakeSession):
    def phase(self, kind, thread_id, text=None, previous=None):
        revision = kind == 'seed' and bool(self.threads[thread_id]['turns'])
        result = super().phase(kind, thread_id, text, previous)
        if revision:
            result['turn_id'] += '.revision'
            self.threads[thread_id]['turns'][-1]['id'] = result['turn_id']
            if self.failure in ('revision-failed', 'revision-tools', 'revision-auto-compact'):
                result['status'] = {'revision-failed': 'turn_failed', 'revision-tools': 'tool_budget',
                                    'revision-auto-compact': 'comparison_contaminated'}[self.failure]
        if kind == 'continuation' and self.failure != 'old-policy':
            final = 'b' if thread_id.startswith('A-to-B') else 'a'
            (self.workspace / 'plan.py').write_text(SOLUTIONS['visible-policy-' + final])
        return result

    def new_thread(self, label, source=None, last_turn=None):
        thread = super().new_thread(label, source, last_turn)
        if source and self.failure == 'fork-initial-only':
            thread['turns'] = thread['turns'][:1]
            self.threads[label] = deepcopy(thread)
        return thread


class NativeRevisionTests(unittest.TestCase):
    def test_plan_keeps_default_and_freezes_distinct_revision_turns(self):
        old = json.loads((Path(__file__).parents[1] / 'reports/native-smoke.json').read_text())
        self.assertEqual(native_plan('gpt-6-astra', 'low'), old['plan'])
        plan = native_plan('gpt-6-astra', 'low', 'policy-revision')
        self.assertEqual((plan['seeds'], plan['compactions'], plan['continuations']), (4, 2, 4))
        self.assertEqual(plan['model_phase_timeout_budget_seconds'], 1140)
        self.assertEqual([p['case_id'] for p in plan['pairs']], ['A-to-B', 'B-to-A'])
        self.assertEqual(plan['pairs'][0]['request'], plan['pairs'][1]['request'])
        for pair in plan['pairs']:
            old_seed = next(p for p in old['plan']['pairs'] if p['task'] == pair['initial_task'])
            self.assertEqual(pair['seed_text'], old_seed['seed_text'])
            self.assertNotEqual(pair['initial_task'], pair['task'])
            self.assertNotIn(pair['revision_text'], pair['seed_text'])

    def run_graph(self, failure=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name); private = root / 'private'; private.mkdir()
        session = RevisionSession(root / 'candidate', failure)
        report = {'plan': native_plan('gpt-6-astra', 'low', 'policy-revision'), 'pairs': []}
        exercise_pairs(session, root / 'candidate', private, report, direct_checks)
        return session, report

    def test_ten_phase_graph_forks_only_after_real_revision_and_cross_scores(self):
        session, report = self.run_graph()
        phases = [e for e in session.events if e[0] not in ('start', 'fork')]
        self.assertEqual([e[0] for e in phases], ['seed', 'seed', 'continuation', 'compact', 'continuation',
                                               'seed', 'seed', 'compact', 'continuation', 'continuation'])
        self.assertEqual(len(session.threads), 6)
        for case in ('A-to-B', 'B-to-A'):
            seed, first, revision = case + '.seed', case + '.seed.seed', case + '.seed.seed.revision'
            self.assertIn(('seed', seed, first), session.events)
            forks = [e for e in session.events if e[0] == 'fork' and e[1].startswith(case)]
            self.assertEqual(len(forks), 2)
            self.assertTrue(all(e[2:] == (seed, revision) for e in forks))
            first_action = next(i for i, e in enumerate(session.events) if e[0] in ('compact', 'continuation') and e[1].startswith(case))
            self.assertTrue(all(session.events.index(e) < first_action for e in forks))
        self.assertEqual(session.inputs, [report['plan']['pairs'][0]['request']] * 4)
        self.assertTrue(all(a['classification'] == 'latest_policy' and a['shared_rules_pass'] for p in report['pairs'] for a in p['arms']))
        public = public_report(report)
        self.assertEqual([p['revision']['turn'] for p in public['pairs']], ['A-to-B.revision.turn', 'B-to-A.revision.turn'])
        self.assertTrue(public['native-compact_both_policies_pass'])

    def test_old_policy_is_behavioral_failure_and_does_not_replace_samples(self):
        session, report = self.run_graph('old-policy')
        self.assertEqual(sum(e[0] in ('seed', 'compact', 'continuation') for e in session.events), 10)
        self.assertTrue(all(a['classification'] == 'superseded_policy' and a['shared_rules_pass'] for p in report['pairs'] for a in p['arms']))
        self.assertFalse(public_report(report)['control_both_policies_pass'])

    def test_revision_protocol_failures_stop_before_second_direction(self):
        for failure, expected in [('revision-failed', 'revision:turn_failed'), ('revision-tools', 'revision:tool_budget'),
                                  ('revision-auto-compact', 'revision:comparison_contaminated'),
                                  ('fork-initial-only', 'fork_boundary_mismatch'), ('ack-only', 'compaction_capability_gate')]:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); private = root / 'private'; private.mkdir()
                session = RevisionSession(root / 'candidate', failure)
                report = {'plan': native_plan(scenario='policy-revision'), 'pairs': []}
                with self.assertRaisesRegex(ValueError, expected):
                    exercise_pairs(session, root / 'candidate', private, report, direct_checks)
                self.assertFalse(any(e[1].startswith('B-to-A') for e in session.events))
