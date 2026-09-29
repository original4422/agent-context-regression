"""Executed outside the candidate process, under a read-only OS sandbox."""
import importlib.util
import json
from pathlib import Path
import runpy
import sys


def main():
    task, workspace, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    spec = json.loads((task / "task.json").read_text())
    checks = runpy.run_path(str(task / f"{mode}.py"))["CHECKS"]
    loader = importlib.util.spec_from_file_location("candidate", workspace / spec["module"])
    candidate = importlib.util.module_from_spec(loader)
    results = []
    try:
        loader.loader.exec_module(candidate)
    except Exception as error:
        results = [{"name": name, "passed": False, "error": type(error).__name__} for name in checks]
    else:
        for name, check in checks.items():
            try:
                passed = check(candidate) is True
                results.append({"name": name, "passed": passed})
            except Exception as error:
                results.append({"name": name, "passed": False, "error": type(error).__name__})
    print("ACR_RESULT=" + json.dumps(results))


if __name__ == "__main__":
    main()
