"""Trusted checks evaluate JSON values returned by separate candidate processes."""
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time

WORKER = Path(__file__).with_name("worker.py")


class CandidateFailure(Exception):
    pass


class Candidate:
    def __init__(self, command, workspace, deadline):
        self.command, self.workspace, self.deadline = command, workspace, deadline

    def __getattr__(self, name):
        def call(*args, **kwargs):
            request = {"function": name, "args": args, "kwargs": kwargs}
            payload = json.dumps(request, allow_nan=False)
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise CandidateFailure("CandidateTimeout")
            proc = subprocess.Popen(self.command, cwd=self.workspace, stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    start_new_session=True)
            try:
                out, err = proc.communicate(payload, timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()
                raise CandidateFailure("CandidateTimeout") from None
            lines = out.splitlines()
            # Emitted before importing candidate code. A worker that cannot
            # start is a harness failure, not a failed implementation.
            if not lines or lines[0] != 'ACR_WORKER_READY':
                raise RuntimeError(f"Candidate worker failed to start ({proc.returncode}): {err[-1000:]}")
            if proc.returncode or len(lines) == 1:
                raise CandidateFailure("CandidateExited")
            if len(lines) != 2:
                raise CandidateFailure("CandidateProtocolError")
            try:
                response = json.loads(lines[1])
                if set(response) == {"error"} and isinstance(response["error"], str):
                    raise CandidateFailure(response["error"])
                if set(response) != {"value", "args", "kwargs"}:
                    raise ValueError("Invalid response fields")
                # Pure-function tasks: do not hide input mutations behind JSON.
                original = json.loads(payload)
                if response["args"] != original["args"] or response["kwargs"] != original["kwargs"]:
                    raise CandidateFailure("InputMutation")
                return response["value"]
            except (ValueError, TypeError):
                raise CandidateFailure("CandidateProtocolError") from None
        return call


def evaluate(task_path, workspace, mode, command, timeout=15):
    checks = runpy.run_path(str(Path(task_path) / f"{mode}.py"))["CHECKS"]
    if not isinstance(checks, dict) or not checks:
        raise ValueError("CHECKS must be a non-empty dict")
    candidate = Candidate(command, workspace, time.monotonic() + timeout)
    results = []
    for name, check in checks.items():
        try:
            results.append({"name": name, "passed": check(candidate) is True})
        except CandidateFailure as error:
            results.append({"name": name, "passed": False, "error": str(error)})
    return {"status": "completed", "passed": all(c["passed"] for c in results), "checks": results}
