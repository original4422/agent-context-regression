from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from context_regression.cli import main
from context_regression.doctor import REQUIRED_EXEC_FLAGS, inspect_environment


class DoctorTests(unittest.TestCase):
    def fake(self, args, **kwargs):
        self.calls.append(args)
        self.assertEqual(kwargs['timeout'], 10)
        self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
        if args[1:] == ['--version']:
            return subprocess.CompletedProcess(args, 0, 'codex-cli fixture\n', '')
        if args[1:] == ['exec','--help']:
            return subprocess.CompletedProcess(args, 0, ' '.join(REQUIRED_EXEC_FLAGS - self.missing_flags), '')
        if args[1:] == ['login','status']:
            return subprocess.CompletedProcess(args, self.login_code, '', '')
        if args[1] == 'sandbox':
            target = Path(args[-1])
            self.temp_target = target
            self.assertEqual(target.read_text(), 'unchanged')
            if self.allow_write:
                target.write_text('changed')
            return subprocess.CompletedProcess(args, 0, json.dumps({'read': True, 'write_blocked': not self.allow_write}), '')
        raise AssertionError(f'unexpected command: {args}')

    def setUp(self):
        self.calls = []
        self.missing_flags = set()
        self.login_code = 0
        self.allow_write = False

    def test_ready_checks_real_interface_without_model_or_login_mutation(self):
        with patch('context_regression.doctor.subprocess.run', side_effect=self.fake), patch.dict('os.environ', {'OPENAI_API_KEY':'not-used'}):
            report = inspect_environment('codex-test')
        self.assertTrue(report['ready'])
        self.assertEqual(len(self.calls), 4)
        self.assertFalse(self.temp_target.parent.exists())
        self.assertTrue(all(args[1:] == ['exec','--help'] for args in self.calls if args[1] == 'exec'))
        self.assertTrue(all(args[1:] == ['login','status'] for args in self.calls if args[1] == 'login'))

    def test_missing_flags_login_and_failed_write_protection_are_not_ready(self):
        for issue in ('flags','login','sandbox'):
            with self.subTest(issue=issue):
                self.missing_flags = {'--ignore-rules'} if issue == 'flags' else set()
                self.login_code = 1 if issue == 'login' else 0
                self.allow_write = issue == 'sandbox'
                with patch('context_regression.doctor.subprocess.run', side_effect=self.fake):
                    report = inspect_environment()
                self.assertFalse(report['ready'])
                self.assertEqual([c['name'] for c in report['checks'] if not c['ready']], ['exec_flags' if issue == 'flags' else issue])

    def test_missing_cli_and_timeout_are_reported_without_repair_actions(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired('codex',10)):
            with self.subTest(error=type(error).__name__), patch('context_regression.doctor.subprocess.run', side_effect=error) as run:
                report = inspect_environment('/missing/codex')
            self.assertFalse(report['ready'])
            self.assertEqual(run.call_count, 1)

    def test_cli_exit_distinguishes_ready_and_not_ready(self):
        for ready in (True, False):
            with patch('context_regression.cli.inspect_environment', return_value={'ready':ready,'checks':[]}), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    main(['doctor'])
            self.assertEqual(result.exception.code, 0 if ready else 1)
