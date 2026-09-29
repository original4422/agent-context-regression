import json
from pathlib import Path
import sys

from .verify import WORKER, evaluate


VERIFICATION_TIMEOUT = 15


def run_checks(task_path, workspace, mode, codex="codex", timeout=VERIFICATION_TIMEOUT):
    spec = json.loads((Path(task_path) / "task.json").read_text())
    # CHECKS and final verdicts stay in the trusted process. Only candidate code
    # enters the read-only sandbox, returning JSON values rather than verdicts.
    command = [codex, "sandbox", "-c", 'sandbox_mode="read-only"', "-c",
               'approval_policy="never"', "--", sys.executable, "-I", "-B",
               str(WORKER), str(Path(workspace) / spec["module"])]
    return evaluate(task_path, workspace, mode, command, timeout)
