"""Opt-in observation of the existing four-tool bridge, in its actual process."""
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from context_regression.bridge import main


def run():
    # Extra final argument belongs only to this observer; regular bridge unchanged.
    path = Path(sys.argv.pop())
    with open(path, 'a', opener=lambda p, flags: os.open(p, flags, 0o600)) as log:
        def record(kind, value):
            log.write(json.dumps({'at_ns': time.monotonic_ns(), 'pid': os.getpid(), 'kind': kind, 'value': value}) + '\n')
            log.flush()
        record('start', {'pid': os.getpid(), 'ppid': os.getppid(), 'pgid': os.getpgrp(), 'nonce': uuid.uuid4().hex,
                         'started': subprocess.check_output(['ps', '-p', str(os.getpid()), '-o', 'lstart='], text=True).strip()})
        # Existing watchdog follows this dedicated app-server, not a long-lived caller.
        sys.argv[4] = str(os.getppid())
        def stop(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, stop)
        try:
            main(record)
        finally:
            record('exit', {'pid': os.getpid()})


if __name__ == '__main__':
    run()
