import shutil
import tempfile
from pathlib import Path
import unittest

from context_regression.checks import run_checks
from context_regression.tasks import BUILTIN_TASKS, tasks_in
from policy_fixtures import MUTATIONS, SOLUTIONS
from test_regression import direct_checks


class PolicyTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = [task for task in tasks_in(BUILTIN_TASKS) if task['spec']['id'] in SOLUTIONS]

    def test_each_corrected_requirement_has_a_detected_counterexample(self):
        for task in self.tasks:
            task_id = task['spec']['id']
            workspace = self.root / task_id
            shutil.copytree(task['path'] / 'snapshot', workspace)
            covered = set()
            for name, before, after, check in MUTATIONS[task_id]:
                with self.subTest(task=task_id, mutation=name):
                    self.assertIn(before, SOLUTIONS[task_id])
                    (workspace / task['spec']['module']).write_text(SOLUTIONS[task_id].replace(before, after))
                    result = direct_checks(task['path'], workspace, 'oracle')
                    failed = {item['name'] for item in result['checks'] if not item['passed']}
                    self.assertIn(check, failed)
                    if check in task['spec']['regression_checks']:
                        self.assertTrue(direct_checks(task['path'], workspace, 'public')['passed'])
                    covered.update(failed)
            self.assertTrue(set(task['spec']['regression_checks']) <= covered)

    @unittest.skipUnless(shutil.which('codex'), 'Codex sandbox not installed')
    def test_references_pass_real_read_only_sandbox(self):
        for task in self.tasks:
            with self.subTest(task=task['spec']['id']):
                workspace = self.root / task['spec']['id']
                shutil.copytree(task['path'] / 'snapshot', workspace)
                (workspace / task['spec']['module']).write_text(SOLUTIONS[task['spec']['id']])
                self.assertTrue(run_checks(task['path'], workspace, 'oracle')['passed'])
