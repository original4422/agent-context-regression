from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.planning import select_tasks
from context_regression.runner import execution_plan, schedule
from context_regression.tasks import BUILTIN_TASKS


class PlanningTests(unittest.TestCase):
    def invoke(self, args):
        out = io.StringIO()
        with redirect_stdout(out):
            main(args)
        return out.getvalue()

    def test_preview_defaults_and_all_do_not_invoke_codex_or_create_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = Path(temporary) / 'private'
            with patch('subprocess.Popen', side_effect=AssertionError('preview launched a process')), patch('context_regression.cli.run_batch', side_effect=AssertionError('preview ran a batch')):
                default = self.invoke(['plan', '--private-dir', str(result), '--codex', '/missing/codex'])
                dry = self.invoke(['run', '--dry-run', '--private-dir', str(result)])
                all_tasks = self.invoke(['plan', '--suite', 'all'])
            self.assertEqual(default, dry)
            self.assertIn('6 continuations + 2 summaries', default)
            self.assertIn('1260 s', default)
            self.assertIn('visible-policy-a, visible-policy-b', default)
            self.assertIn('60 continuations + 20 summaries', all_tasks)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_explicit_suites_and_tasks_keep_two_repetitions(self):
        expected = {'micro': (24,8), 'software-policy': (12,4), 'paired': (12,4), 'visible-policy': (12,4), 'all': (60,20)}
        for suite, counts in expected.items():
            with self.subTest(suite=suite):
                tasks, repeats, _ = select_tasks(BUILTIN_TASKS, suite)
                config = dict(repetitions=repeats, seed=20260930, timeout=180, summary_timeout=90)
                plan = execution_plan(tasks, config)
                self.assertEqual((plan['continuations'], plan['summaries']), counts)
                self.assertEqual(plan['runs'], schedule(tasks, 2, 20260930))
        tasks, repeats, _ = select_tasks(BUILTIN_TASKS, ids=['retry-method-policy'])
        self.assertEqual(repeats, 2)
        self.assertEqual([t['spec']['id'] for t in tasks], ['retry-method-policy'])

    def test_historical_explicit_selections_keep_order_and_task_fingerprints(self):
        reports = Path(__file__).resolve().parents[1] / 'reports'
        for filename in ('pilot-02.json','software-policy-results.json','paired-policy-results.json','visible-policy-results.json'):
            with self.subTest(report=filename):
                report = json.loads((reports/filename).read_text())
                tasks, repeats, _ = select_tasks(BUILTIN_TASKS, ids=[t['id'] for t in report['tasks']])
                self.assertEqual(repeats, 2)
                plan = execution_plan(tasks, report['config'])
                order = [{'task':t['spec']['id'],'repeat':r+1,'strategy':s} for t,r,s in plan['runs']]
                self.assertEqual(order, report['order'])
                self.assertEqual({t['spec']['id']:t['digest'] for t in tasks}, {t['id']:t['sha256'] for t in report['tasks']})

    def test_external_directory_keeps_all_and_rejects_named_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(BUILTIN_TASKS/'retry-method-policy', root/'one')
            tasks, repeats, _ = select_tasks(root)
            self.assertEqual(len(tasks), 1)
            self.assertEqual(repeats, 2)
            with self.assertRaisesRegex(ValueError, 'external'):
                select_tasks(root, 'all')

    def test_run_receives_same_schedule_and_can_override_quickstart_repetitions(self):
        captured = {}
        def fake_run(tasks, config, private):
            captured.update(tasks=tasks, config=config, private=private)
            return {}
        with patch('context_regression.cli.run_batch', side_effect=fake_run), patch('context_regression.cli.summarize', return_value='done'):
            output = self.invoke(['run','--model','test-model','--repetitions','3'])
        self.assertEqual(captured['config']['repetitions'], 3)
        self.assertEqual(len(captured['tasks']), 2)
        self.assertIn('18 continuations + 6 summaries', output)

    def test_invalid_selection_and_missing_execution_model_exit_two(self):
        for args in (['plan','--suite','micro','--task','retry-method-policy'], ['plan','--task','missing'], ['plan','--repetitions','0'], ['run']):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    main(args)
                self.assertEqual(result.exception.code, 2)
