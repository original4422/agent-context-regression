import ast
import runpy

from context_regression.release_checks import SHARED_CHECKS
import test_paired_tasks
from test_regression import direct_checks
from visible_fixtures import SOLUTIONS


class VisiblePolicyTests(test_paired_tasks.PairedTaskTests):
    solutions = SOLUTIONS

    def test_shared_executable_contract_requires_only_the_policy_hook(self):
        for task in self.tasks:
            with self.subTest(task=task['spec']['id']):
                checkpoint = ast.parse((task['path']/'snapshot/plan.py').read_text())
                completed = ast.parse(SOLUTIONS[task['spec']['id']])
                # The references used by inherited execution tests only change
                # the hook. Every executable statement of shared policy remains.
                for tree in (checkpoint, completed):
                    hook = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_dependencies_satisfied')
                    hook.body = []
                self.assertEqual(ast.dump(checkpoint), ast.dump(completed))
                checks = runpy.run_path(str(task['path']/'oracle.py'))['CHECKS']
                self.assertEqual(set(checks), set(SHARED_CHECKS) | {'dependency_policy'})
                self.assertTrue(all(checks[name] is check for name,check in SHARED_CHECKS.items()))
                workspace = self.root/task['spec']['id']
                workspace.mkdir()
                (workspace/'plan.py').write_text(SOLUTIONS[task['spec']['id']])
                verdict = direct_checks(task['path'], workspace, 'oracle')
                self.assertTrue(verdict['passed'])
