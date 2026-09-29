"""One JSON call to a candidate module. No acceptance code enters this process."""
import contextlib
import importlib.util
import json
from pathlib import Path
import sys


def main():
    print("ACR_WORKER_READY", flush=True)
    request = json.loads(sys.stdin.read())
    module_path = Path(sys.argv[1])
    loader = importlib.util.spec_from_file_location("candidate", module_path)
    candidate = importlib.util.module_from_spec(loader)
    # Candidate print() output is diagnostic, never a verifier result.
    with contextlib.redirect_stdout(sys.stderr):
        try:
            loader.loader.exec_module(candidate)
            value = getattr(candidate, request["function"])(*request["args"], **request["kwargs"])
            result = json.dumps({"value": value, "args": request["args"], "kwargs": request["kwargs"]}, allow_nan=False)
        except BaseException as error:
            # Candidate SystemExit/KeyboardInterrupt cannot terminate the verifier.
            result = json.dumps({"error": type(error).__name__})
    print(result, flush=True)


if __name__ == "__main__":
    main()
