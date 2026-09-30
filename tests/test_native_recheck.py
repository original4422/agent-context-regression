import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PublicRecheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ('context_regression', 'reports/native-candidates', 'reports/native-revision-candidates', 'reports/native-tool-checkpoint-candidates'):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        (self.root / 'scripts').mkdir()
        for name in ('reports/native-smoke.json', 'reports/native-revision.json', 'reports/native-tool-checkpoint.json', 'scripts/recheck_native_candidates.py'):
            shutil.copyfile(ROOT / name, self.root / name)

    def run_recheck(self, scenario='fixed-policy'):
        # No inherited credentials or executable search path; only this Python.
        return subprocess.run([sys.executable, '-I', '-B', str(self.root / 'scripts/recheck_native_candidates.py'), '--scenario', scenario],
                              cwd=self.root, env={'PATH': '', 'HOME': str(self.root)},
                              capture_output=True, text=True, timeout=30)

    def test_public_files_recompute_eight_oracles_and_remain_unchanged(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        run = self.run_recheck()
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        result = json.loads(run.stdout)
        self.assertEqual(result['oracle_evaluations'], 8)
        self.assertEqual(len(result['candidates']), 4)
        for row in result['candidates']:
            self.assertTrue(row['matches_recorded_results'])
            self.assertEqual(row['differences'], {})
            self.assertEqual(sum(v['passed'] for v in row['cross_verification'].values()), 1)
            self.assertTrue(all(len(v['checks']) == 11 for v in row['cross_verification'].values()))
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_revision_published_candidates_match_and_swap_is_rejected(self):
        run = self.run_recheck('policy-revision')
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['oracle_evaluations'], 8)
        self.assertTrue(result['matches_recorded_results'])
        for row in result['candidates']:
            target = 'visible-policy-b' if row['candidate'].startswith('A-to-B') else 'visible-policy-a'
            self.assertEqual([t for t,v in row['cross_verification'].items() if v['passed']], [target])
        base = self.root / 'reports/native-revision-candidates'
        shutil.copyfile(base / 'A-to-B-control/plan.py', base / 'B-to-A-control/plan.py')
        run = self.run_recheck('policy-revision')
        self.assertEqual(run.returncode, 1)
        self.assertIn('candidate hash mismatch: B-to-A-control', run.stdout)

    def test_work_artifacts_recompute_intermediate_and_final_results(self):
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        run = self.run_recheck('tool-checkpoint')
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        result = json.loads(run.stdout)
        self.assertEqual(result['oracle_evaluations'], 3)
        verdicts = [r['cross_verification']['retry-method-policy'] for r in result['candidates']]
        self.assertEqual([v['passed'] for v in verdicts], [False, True, True])
        self.assertEqual([c['name'] for c in verdicts[0]['checks'] if not c['passed']],
                         ['rate_limit', 'case_insensitive_method'])
        self.assertTrue(all(r['matches_recorded_results'] for r in result['candidates']))
        self.assertEqual(before, {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_work_mutations_rejected_before_execution(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('recheck', self.root / 'scripts/recheck_native_candidates.py')
        recheck = importlib.util.module_from_spec(spec); spec.loader.exec_module(recheck)
        base = self.root / 'reports/native-tool-checkpoint-candidates'
        partial = base / 'work-checkpoint/retry.py'
        final = base / 'retry-work-native-compact/retry.py'
        paths = [partial, final, self.root / 'context_regression/worker.py',
                 self.root / 'context_regression/tasks/retry-method-policy/oracle.py']
        for path in paths:
            original = path.read_bytes()
            with self.subTest(path=path), patch('subprocess.Popen') as spawn, patch('runpy.run_path') as oracle:
                path.write_bytes(original + b'\n# changed\n')
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    recheck.recheck('tool-checkpoint')
                spawn.assert_not_called(); oracle.assert_not_called()
            path.write_bytes(original)
        for replacement in (None, partial.read_bytes()):
            original = final.read_bytes()
            with patch('subprocess.Popen') as spawn:
                final.unlink() if replacement is None else final.write_bytes(replacement)
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    recheck.recheck('tool-checkpoint')
                spawn.assert_not_called()
            final.write_bytes(original)

    def test_mutations_rejected_before_any_worker_or_oracle_executes(self):
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('recheck', self.root / 'scripts/recheck_native_candidates.py')
        recheck = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(recheck)
        paths = ['reports/native-candidates/B-control/plan.py', 'context_regression/worker.py',
                 'context_regression/verify.py', 'context_regression/release_checks.py',
                 'context_regression/tasks/visible-policy-a/oracle.py']
        for name in paths:
            path = self.root / name
            original = path.read_bytes()
            with self.subTest(name=name), patch('subprocess.Popen') as spawn, patch('runpy.run_path') as oracle:
                path.write_bytes(original + b'\n# changed\n')
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    recheck.recheck()
                spawn.assert_not_called()
                oracle.assert_not_called()
            run = self.run_recheck()
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertIn('mismatch', run.stdout)
            path.write_bytes(original)
        a = self.root / 'reports/native-candidates/A-control/plan.py'
        b = self.root / 'reports/native-candidates/B-control/plan.py'
        for mutation in ('missing', 'swapped'):
            with self.subTest(mutation=mutation), patch('subprocess.Popen') as spawn:
                original = b.read_bytes()
                b.unlink() if mutation == 'missing' else b.write_bytes(a.read_bytes())
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    recheck.recheck()
                spawn.assert_not_called()
            run = self.run_recheck()
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertIn('candidate', run.stdout)
            b.write_bytes(original)
        # CLI failure is nonzero and identifies the changed dependency.
        worker = self.root / 'context_regression/worker.py'
        worker.write_text(worker.read_text() + '\nraise AssertionError("must not execute")\n')
        run = self.run_recheck()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('verifier version mismatch: context_regression/worker.py', run.stdout)

    def test_recomputes_instead_of_repeating_recorded_verdicts(self):
        report = self.root / 'reports/native-smoke.json'
        data = json.loads(report.read_text())
        data['pairs'][0]['arms'][0]['cross_verification']['visible-policy-a']['checks'][0]['passed'] = False
        report.write_text(json.dumps(data))
        run = self.run_recheck()
        self.assertEqual(run.returncode, 1, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['oracle_evaluations'], 8)
        row = result['candidates'][0]
        self.assertFalse(row['matches_recorded_results'])
        self.assertTrue(row['cross_verification']['visible-policy-a']['checks'][0]['passed'])
        self.assertIn('visible-policy-a', row['differences'])


if __name__ == '__main__':
    unittest.main()
