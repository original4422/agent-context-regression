"""Check local CLI/login/sandbox prerequisites without invoking a model."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REQUIRED_EXEC_FLAGS = {
    "--json", "--ephemeral", "--ignore-user-config", "--ignore-rules",
    "--skip-git-repo-check", "--sandbox", "--model", "--color", "--cd",
    "--output-last-message", "--output-schema", "--config",
}
PROBE = '''import json, sys
from pathlib import Path
p = Path(sys.argv[1])
assert p.read_text() == "unchanged"
try:
    p.write_text("changed")
except PermissionError:
    print(json.dumps({"read": True, "write_blocked": True}))
else:
    print(json.dumps({"read": True, "write_blocked": False}))
'''


def inspect_environment(codex="codex"):
    checks = [{"name": "python", "ready": sys.version_info >= (3, 11),
               "detail": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; requires 3.11+"}]
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)

    def command(args, cwd=None):
        return subprocess.run([codex, *args], capture_output=True, text=True,
                              env=env, cwd=cwd, timeout=10)

    def inspect(name, args, assess):
        try:
            result = command(args)
            ready, detail = assess(result)
        except (OSError, subprocess.TimeoutExpired) as error:
            ready, detail = False, type(error).__name__
        checks.append({"name": name, "ready": ready, "detail": detail})
        return ready

    if not inspect("codex", ["--version"], lambda r: (r.returncode == 0, r.stdout.strip() if r.returncode == 0 else f"exit {r.returncode}")):
        for name in ("exec_flags", "login", "sandbox"):
            checks.append({"name": name, "ready": False, "detail": "not checked: Codex executable unavailable"})
        return {"ready": False, "checks": checks}

    def flags(result):
        if result.returncode:
            return False, f"exec --help exited {result.returncode}"
        missing = REQUIRED_EXEC_FLAGS - set(re.findall(r"--[a-z][a-z-]*", result.stdout))
        return (result.returncode == 0 and not missing,
                f"missing: {', '.join(sorted(missing))}" if missing else "all required exec flags present")

    inspect("exec_flags", ["exec", "--help"], flags)
    inspect("login", ["login", "status"], lambda r: (r.returncode == 0,
            "existing login reported" if r.returncode == 0 else f"not logged in (exit {r.returncode}); use codex login separately"))
    with tempfile.TemporaryDirectory(prefix="acr-doctor-") as temporary:
        target = Path(temporary) / "read-only-probe.txt"
        target.write_text("unchanged")
        try:
            result = command(["sandbox", "-c", 'sandbox_mode="read-only"', "-c", 'approval_policy="never"',
                              "--", sys.executable, "-I", "-B", "-c", PROBE, str(target)], cwd=temporary)
            value = json.loads(result.stdout) if result.returncode == 0 else None
            ready = value == {"read": True, "write_blocked": True} and target.read_text() == "unchanged"
            detail = "read succeeds; write blocked" if ready else f"read-only probe failed (exit {result.returncode})"
        except (OSError, subprocess.TimeoutExpired, ValueError) as error:
            ready, detail = False, type(error).__name__
        checks.append({"name": "sandbox", "ready": ready, "detail": detail})
    return {"ready": all(check["ready"] for check in checks), "checks": checks}


def format_doctor(report):
    lines = ["Local prerequisites: " + ("ready" if report["ready"] else "not ready")]
    lines.extend(f"{'OK' if check['ready'] else 'FAIL'} {check['name']}: {check['detail']}" for check in report["checks"])
    lines.append("No model request was sent. Model access and an end-to-end MCP run are checked only by an actual run.")
    return "\n".join(lines)
