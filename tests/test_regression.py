import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from policy_fixtures import SOLUTIONS as POLICY_SOLUTIONS
from paired_fixtures import SOLUTIONS as PAIRED_SOLUTIONS

from context_regression.bridge import Workspace
from context_regression.checks import run_checks
from context_regression.cli import summarize
from context_regression.runner import RunFailure, phase_total, run_batch, run_codex, schedule
from context_regression.tasks import BUILTIN_TASKS, recent_turns, task_digest, tasks_in
from context_regression.verify import WORKER, evaluate

SOLUTIONS = {
    "case-sensitive-slugs": 'import re\ndef slug(title):\n    return re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")\n',
    "explicit-empty-overrides": 'def merge_settings(defaults, overrides):\n    return {**defaults, **{k:v for k,v in overrides.items() if v is not None}}\n',
    "retry-method-policy": 'def should_retry(status, method):\n    return status in {429,500,502,503,504} and method.upper() in {"GET","HEAD","PUT"}\n',
    "event-window-order": 'def select_events(events, start, end):\n    seen = set()\n    selected = []\n    for event in events:\n        if start <= event["timestamp"] < end and event["id"] not in seen:\n            selected.append(event)\n            seen.add(event["id"])\n    return selected\n',
}

SOLUTIONS.update(POLICY_SOLUTIONS)
SOLUTIONS.update(PAIRED_SOLUTIONS)


def direct_checks(task, workspace, mode, codex="codex"):
    """Test the actual verifier without requiring Codex on CI."""
    spec = json.loads((Path(task) / "task.json").read_text())
    command = [sys.executable, "-I", "-B", str(WORKER), str(Path(workspace) / spec["module"])]
    return evaluate(task, workspace, mode, command)


STACK_MUTATION = '''import inspect
for frame_info in inspect.stack():
    local_checks = frame_info.frame.f_locals.get("checks")
    if isinstance(local_checks, dict):
        for name in list(local_checks):
            local_checks[name] = lambda module: True
'''


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tasks = tasks_in(BUILTIN_TASKS)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_broken_checkpoints_and_correct_solutions(self):
        self.assertEqual(len(self.tasks), 8)
        for task in self.tasks:
            with self.subTest(task=task["spec"]["id"]):
                workspace = self.root / task["spec"]["id"]
                shutil.copytree(task["path"] / "snapshot", workspace)
                self.assertFalse(direct_checks(task["path"], workspace, "public")["passed"])
                self.assertFalse(direct_checks(task["path"], workspace, "oracle")["passed"])
                (workspace / task["spec"]["module"]).write_text(SOLUTIONS[task["spec"]["id"]])
                self.assertTrue(direct_checks(task["path"], workspace, "public")["passed"])
                self.assertTrue(direct_checks(task["path"], workspace, "oracle")["passed"])

    def test_public_checks_do_not_replace_independent_oracle(self):
        task = self.tasks[0]
        workspace = self.root / "work"
        shutil.copytree(task["path"] / "snapshot", workspace)
        (workspace / "slug.py").write_text(SOLUTIONS[task["spec"]["id"]].replace('title).strip', 'title.lower()).strip'))
        self.assertTrue(direct_checks(task["path"], workspace, "public")["passed"])
        result = direct_checks(task["path"], workspace, "oracle")
        self.assertEqual([c["name"] for c in result["checks"] if not c["passed"]], ["rejected_lowercasing", "existing_separator", "digits"])

    def test_syntax_error_is_a_failed_candidate(self):
        task = self.tasks[0]
        workspace = self.root / "work"
        shutil.copytree(task["path"] / "snapshot", workspace)
        (workspace / "slug.py").write_text("def invalid(:\n")
        result = direct_checks(task["path"], workspace, "oracle")
        self.assertFalse(result["passed"])
        self.assertTrue(all(c["error"] == "SyntaxError" for c in result["checks"]))

    def test_recent_keeps_whole_user_turn(self):
        history = [{"role": "user", "content": "old"}, {"role": "assistant", "content": "x"},
                   {"role": "user", "content": "new"}, {"role": "tool", "content": "observation"}]
        self.assertEqual(recent_turns(history, 1), history[2:])
        self.assertEqual(recent_turns(history, 3), history)

    def test_task_fingerprint_changes_with_oracle(self):
        task = self.tasks[0]
        shutil.copytree(task["path"], self.root / "task")
        before = task_digest(self.root / "task")
        with (self.root / "task/oracle.py").open("a") as out:
            out.write("\n# changed\n")
        self.assertNotEqual(before, task_digest(self.root / "task"))

    def test_tools_cannot_access_verifier_or_other_workspaces(self):
        task = self.tasks[0]
        root = self.root / "work"
        shutil.copytree(task["path"] / "snapshot", root)
        workspace = Workspace(task, root)
        for forbidden in ("../oracle.py", str(task["path"] / "oracle.py"), "public.py"):
            with self.assertRaises(ValueError):
                workspace.call("read_file", {"path": forbidden})
            with self.assertRaises(ValueError):
                workspace.call("write_file", {"path": forbidden, "content": "pass"})
        (root / "slug.py").unlink()
        (root / "slug.py").symlink_to(task["path"] / "oracle.py")
        with self.assertRaises(ValueError):
            workspace.call("read_file", {"path": "slug.py"})

    def test_workspace_reset(self):
        task = self.tasks[0]
        for name in ("a", "b"):
            shutil.copytree(task["path"] / "snapshot", self.root / name)
        Workspace(task, self.root / "a").call("write_file", {"path": "slug.py", "content": "changed"})
        self.assertEqual((self.root / "b/slug.py").read_text(), (task["path"] / "snapshot/slug.py").read_text())

    def test_schedule_is_seeded_and_covers_every_cell(self):
        first = schedule(self.tasks, 2, 17)
        self.assertEqual(first, schedule(self.tasks, 2, 17))
        self.assertNotEqual(first, schedule(self.tasks, 2, 18))
        self.assertEqual(len({(t["spec"]["id"], r, s) for t, r, s in first}), 8 * 3 * 2)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fake(self, source):
        file = self.root / "fake.py"
        file.write_text(source)
        return [sys.executable, str(file)]

    def test_usage_and_summary_costs_are_added_once(self):
        args = self.fake('import json\nprint(json.dumps({"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":4,"output_tokens":3}}))\n')
        result = run_codex(args, "fixture", self.root / "private", 5, 3)
        total = phase_total({"summary": result, "continuation": result})
        self.assertEqual(total["usage"], {"input_tokens": 20, "cached_input_tokens": 8, "output_tokens": 6})
        self.assertTrue((self.root / "private/events.jsonl").is_file())

    def test_timeout_aborts_and_keeps_trace(self):
        args = self.fake('import time\nprint("{}",flush=True)\ntime.sleep(20)\n')
        with self.assertRaises(RunFailure) as caught:
            run_codex(args, "fixture", self.root / "private", 0.2, 3)
        self.assertEqual(caught.exception.phase["status"], "timeout")
        self.assertIsNone(caught.exception.phase["usage"])
        self.assertIn("{}", (self.root / "private/events.jsonl").read_text())

    def test_missing_usage_does_not_become_zero(self):
        args = self.fake('print("{}")\n')
        with self.assertRaises(RunFailure) as caught:
            run_codex(args, "fixture", self.root / "private", 5, 3)
        self.assertEqual(caught.exception.phase["status"], "missing_usage")

    def test_tool_budget_is_enforced(self):
        args = self.fake('import json,time\nfor i in range(3):\n print(json.dumps({"type":"item.started","item":{"type":"mcp_tool_call"}}),flush=True)\ntime.sleep(20)\n')
        with self.assertRaises(RunFailure) as caught:
            run_codex(args, "fixture", self.root / "private", 5, 2)
        self.assertEqual(caught.exception.phase["status"], "tool_budget")

    def test_rejected_tool_aborts_before_candidate_scoring(self):
        args = self.fake('import json,time\nprint(json.dumps({"type":"item.completed","item":{"type":"mcp_tool_call","status":"failed","error":{"message":"approval required"}}}),flush=True)\ntime.sleep(20)\n')
        with self.assertRaises(RunFailure) as caught:
            run_codex(args, "fixture", self.root / "private", 5, 2)
        self.assertEqual(caught.exception.phase["status"], "tool_failure")

    def test_no_phase_does_not_report_zero_usage(self):
        self.assertIsNone(phase_total({})["usage"])

    def test_batch_three_strategies_and_private_outputs(self):
        task = tasks_in(BUILTIN_TASKS)[0]
        config = {"codex": "codex", "model": "fake", "effort": "low", "repetitions": 1,
                  "seed": 1, "recent_turns": 1, "summary_chars": 4096, "summary_timeout": 10,
                  "timeout": 10, "max_tools": 16}
        def fake_run(args, prompt, private, timeout, max_tools):
            output = Path(args[args.index("--output-last-message") + 1])
            if "--output-schema" in args:
                output.write_text(json.dumps({k: "fixture" for k in ("objective", "constraints", "rejected_approaches", "observations", "next_steps")}))
            else:
                (Path(args[args.index("-C") + 1]) / "slug.py").write_text(SOLUTIONS[task["spec"]["id"]])
            return {"elapsed_seconds": 1, "usage": {"input_tokens": 10, "cached_input_tokens": 0, "output_tokens": 2}, "tool_calls": 2, "exit_code": 0, "status": "completed"}
        with patch("context_regression.runner.run_codex", side_effect=fake_run), patch("context_regression.runner.run_checks", side_effect=direct_checks), patch("context_regression.runner.subprocess.check_output", return_value="fake-cli"):
            result = run_batch([task], config, self.root / "private")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["rows"]), 3)
        structured = next(r for r in result["rows"] if r["strategy"] == "structured")
        self.assertEqual(structured["total"]["usage"]["input_tokens"], 20)
        self.assertEqual(os.stat(self.root / "private").st_mode & 0o777, 0o700)
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertIn("3/3 attempted", summarize(result))

    def test_batch_stops_on_infrastructure_failure(self):
        task = tasks_in(BUILTIN_TASKS)[0]
        config = {"codex": "codex", "model": "fake", "effort": "low", "repetitions": 2,
                  "seed": 1, "recent_turns": 1, "summary_chars": 4096, "summary_timeout": 10,
                  "timeout": 10, "max_tools": 16}
        phase = {"elapsed_seconds": 2, "usage": None, "status": "turn_failed"}
        with patch("context_regression.runner.run_codex", side_effect=RunFailure("turn_failed", phase)), patch("context_regression.runner.subprocess.check_output", return_value="fake-cli"):
            with self.assertRaises(RunFailure):
                run_batch([task], config, self.root / "private")
        result = json.loads((self.root / "private/results.json").read_text())
        self.assertEqual(result["status"], "aborted")
        self.assertEqual(len(result["rows"]), 1)
        self.assertIsNone(result["rows"][0]["total"]["usage"])


class CandidateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task = tasks_in(BUILTIN_TASKS)[0]
        self.workspace = self.root / "work"
        shutil.copytree(self.task["path"] / "snapshot", self.workspace)

    def check_source(self, source):
        (self.workspace / "slug.py").write_text(source)
        return direct_checks(self.task["path"], self.workspace, "oracle")

    def test_stack_mutation_cannot_replace_trusted_checks(self):
        result = self.check_source(STACK_MUTATION)
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["checks"]), 5)
        self.assertTrue(all(c.get("error") == "AttributeError" for c in result["checks"]))

    def test_system_exit_on_import_or_call_is_candidate_failure(self):
        for source in ('raise SystemExit(0)\n', 'def slug(title):\n    raise SystemExit(0)\n'):
            with self.subTest(source=source):
                result = self.check_source(source)
                self.assertEqual(result["status"], "completed")
                self.assertFalse(result["passed"])
                self.assertTrue(all(c.get("error") == "SystemExit" for c in result["checks"]))

    def test_hard_exit_is_candidate_failure(self):
        result = self.check_source('import os\nos._exit(0)\n')
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["passed"])
        self.assertTrue(all(c.get("error") == "CandidateExited" for c in result["checks"]))

    def test_candidate_stdout_is_not_a_verdict(self):
        result = self.check_source('print(\'ACR_RESULT=[{"name":"punctuation","passed":true}]\')\ndef slug(title):\n    return "wrong"\n')
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["checks"]), 5)
        result = self.check_source('import os\nos.write(1,b\'{}\\n\')\ndef slug(title):\n    return "wrong"\n')
        self.assertTrue(all(c.get("error") == "CandidateProtocolError" for c in result["checks"]))

    def test_input_mutation_is_not_hidden_by_serialization(self):
        task = next(t for t in tasks_in(BUILTIN_TASKS) if t["spec"]["id"] == "explicit-empty-overrides")
        (self.workspace / "settings.py").write_text('def merge_settings(defaults, overrides):\n    defaults.update({k:v for k,v in overrides.items() if v is not None})\n    overrides.clear()\n    return defaults\n')
        result = direct_checks(task["path"], self.workspace, "oracle")
        self.assertFalse(result["passed"])
        unchanged = next(c for c in result["checks"] if c["name"] == "inputs_unchanged")
        self.assertEqual(unchanged["error"], "InputMutation")

    def test_timeout_remains_a_candidate_failure(self):
        (self.workspace / "slug.py").write_text('import time\ntime.sleep(20)\n')
        command = [sys.executable, "-I", "-B", str(WORKER), str(self.workspace / "slug.py")]
        result = evaluate(self.task["path"], self.workspace, "oracle", command, timeout=0.5)
        self.assertFalse(result["passed"])
        self.assertTrue(all(c.get("error") == "CandidateTimeout" for c in result["checks"]))

    def test_worker_startup_failure_remains_infrastructure_error(self):
        command = [sys.executable, "-c", 'raise SystemExit("cannot start")']
        with self.assertRaisesRegex(RuntimeError, "failed to start"):
            evaluate(self.task["path"], self.workspace, "oracle", command)

    def test_empty_checks_cannot_pass_without_evaluating_candidate(self):
        (self.root / "oracle.py").write_text("CHECKS = {}\n")
        with self.assertRaisesRegex(ValueError, "non-empty"):
            evaluate(self.root, self.workspace, "oracle", [])


@unittest.skipUnless(shutil.which("codex") and sys.platform == "darwin", "requires Codex's macOS sandbox")
class SandboxTests(unittest.TestCase):
    def test_candidate_cannot_rewrite_external_oracle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = tasks_in(BUILTIN_TASKS)[0]
            shutil.copytree(task["path"], root / "task")
            shutil.copytree(task["path"] / "snapshot", root / "work")
            target = root / "task/oracle.py"
            before = target.read_text()
            (root / "work/slug.py").write_text(f'from pathlib import Path\nPath({str(target)!r}).write_text("tampered")\n')
            result = run_checks(root / "task", root / "work", "oracle")
            self.assertFalse(result["passed"])
            self.assertEqual(target.read_text(), before)
            self.assertTrue(all(c.get("error") == "PermissionError" for c in result["checks"]))

    def test_process_boundary_under_real_sandbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            task = tasks_in(BUILTIN_TASKS)[0]
            cases = [(STACK_MUTATION, "AttributeError"),
                     ('raise SystemExit(0)\n', "SystemExit"),
                     ('def slug(title):\n    raise SystemExit(0)\n', "SystemExit"),
                     ('import os\nos._exit(0)\n', "CandidateExited")]
            for source, expected in cases:
                with self.subTest(expected=expected, source=source):
                    (workspace / "slug.py").write_text(source)
                    result = run_checks(task["path"], workspace, "oracle")
                    self.assertEqual(result["status"], "completed")
                    self.assertFalse(result["passed"])
                    self.assertTrue(all(c.get("error") == expected for c in result["checks"]))


if __name__ == "__main__":
    unittest.main()
