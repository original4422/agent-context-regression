import json
import shutil
import tempfile
from pathlib import Path
import unittest

from context_regression.bridge import TOOLS, Workspace
from context_regression.runner import continuation_prompt
from context_regression.tasks import BUILTIN_TASKS, recent_turns, render_history, tasks_in
from paired_fixtures import SOLUTIONS
from test_regression import direct_checks


class PairedTaskTests(unittest.TestCase):
    solutions = SOLUTIONS

    def setUp(self):
        self.tasks = [t for t in tasks_in(BUILTIN_TASKS) if t['spec']['id'] in self.solutions]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_recent_observation_has_no_policy_signal(self):
        a, b = self.tasks
        self.assertEqual(len(a['history']), len(b['history']))
        differing = [i for i, pair in enumerate(zip(a['history'], b['history'])) if pair[0] != pair[1]]
        self.assertEqual(differing, [2])
        self.assertEqual(a['history'][2]['role'], 'user')
        self.assertEqual({k:v for k,v in a['spec'].items() if k != 'id'}, {k:v for k,v in b['spec'].items() if k != 'id'})
        prompts = [continuation_prompt(t, render_history(recent_turns(t['history'], 1))) for t in self.tasks]
        self.assertEqual(prompts[0].encode(), prompts[1].encode())
        self.assertEqual((a['path']/'public.py').read_bytes(), (b['path']/'public.py').read_bytes())
        observations=[]
        for task in self.tasks:
            workspace=self.root/task['spec']['id']
            shutil.copytree(task['path']/'snapshot', workspace)
            bridge=Workspace(task, workspace)
            observations.append({'tools': TOOLS, 'list': bridge.call('list_files', {}), 'read': bridge.call('read_file', {'path':'plan.py'}), 'check':direct_checks(task['path'], workspace, 'public')})
        self.assertEqual(json.dumps(observations[0], sort_keys=True).encode(), json.dumps(observations[1], sort_keys=True).encode())

    def test_reference_passes_own_policy_and_fails_the_other(self):
        for selected in self.tasks:
            workspace=self.root/selected['spec']['id']
            workspace.mkdir()
            (workspace/'plan.py').write_text(self.solutions[selected['spec']['id']])
            for oracle in self.tasks:
                with self.subTest(candidate=selected['spec']['id'], oracle=oracle['spec']['id']):
                    self.assertTrue(direct_checks(oracle['path'], workspace, 'public')['passed'])
                    verdict=direct_checks(oracle['path'], workspace, 'oracle')
                    failed=[c['name'] for c in verdict['checks'] if not c['passed']]
                    self.assertEqual(failed, [] if selected['spec']['id']==oracle['spec']['id'] else ['dependency_policy'])
