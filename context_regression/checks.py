import json
import os
from pathlib import Path
import signal
import subprocess
import sys

VERIFY = Path(__file__).with_name("verify.py")


def run_checks(task_path, workspace, mode, codex="codex", timeout=15):
    # The model cannot select a command or check path. All candidate code runs read-only.
    command = [codex, "sandbox", "-c", 'sandbox_mode="read-only"', "-c",
               'approval_policy="never"', "--",
               sys.executable, "-I", "-B", str(VERIFY), str(task_path), str(workspace), mode]
    proc = subprocess.Popen(command, cwd=workspace, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return {"status": "candidate_timeout", "passed": False, "checks": []}
    markers = [line.removeprefix("ACR_RESULT=") for line in out.splitlines() if line.startswith("ACR_RESULT=")]
    if proc.returncode != 0 or len(markers) != 1:
        raise RuntimeError(f"Verifier failed ({proc.returncode}): {err[-1000:]}")
    checks = json.loads(markers[0])
    if not checks or any(type(c.get("passed")) is not bool for c in checks):
        raise RuntimeError("Verifier returned invalid checks")
    return {"status": "completed", "passed": all(c["passed"] for c in checks), "checks": checks}
