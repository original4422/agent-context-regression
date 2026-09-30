"""Small owned-process stdio adapter, exercised with scripted peers offline."""
import json
import os
import queue
import signal
import subprocess
import threading
import time

from .native import Phase


class AppServer:
    def __init__(self, command, cwd, trace):
        self.serial = self.sequence = 0
        self.receive_lock = threading.Lock()
        self.stopped = False
        self.closed = False
        self.messages = queue.Queue()
        self.trace = trace
        env = dict(os.environ)
        env.pop("OPENAI_API_KEY", None)
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        text=True, start_new_session=True)
        def read():
            for line in self.process.stdout:
                with self.receive_lock:
                    self.sequence += 1
                    self.messages.put((self.sequence, line))
            self.messages.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, method, params):
        self.serial += 1
        message = {"id": self.serial, "method": method, "params": params}
        self.trace.append({"direction": "send", "message": message})
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()
        return self.serial

    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("phase_timeout")
        try:
            line = self.messages.get(timeout=min(remaining, 0.05))
        except queue.Empty:
            return None
        if line is None:
            raise RuntimeError("app_server_closed")
        sequence, line = line
        event = json.loads(line)
        # This adapter never sends config/read. A future preflight must keep its
        # response (including late responses) out of this raw protocol trace.
        self.trace.append({"direction": "receive", "sequence": sequence, "message": event})
        return sequence, event

    def phase(self, kind, thread_id, params, timeout, *, previous_turn_id=None, cancel=None, grace=3):
        if self.stopped or (cancel and cancel.is_set()):
            self.close()
            raise RuntimeError("client_stopped")
        # Deadline includes dispatch, RPC response and all completion events.
        deadline = time.monotonic() + timeout
        method = "thread/compact/start" if kind == "compact" else "turn/start"
        if params.get("threadId") != thread_id:
            raise ValueError("thread_mismatch")
        phase = Phase(kind, thread_id, self.serial + 1, self.sequence, previous_turn_id)
        try:
            with self.receive_lock:
                if cancel and cancel.is_set():
                    raise RuntimeError("cancelled")
                phase.start_sequence = self.sequence
                self.send(method, params)
            while not phase.completed and not phase.failure:
                if cancel and cancel.is_set():
                    phase.failure = "cancelled"
                    break
                received = self.receive(deadline)
                if received:
                    sequence, event = received
                    if "id" in event and "method" in event:
                        phase.failure = "unexpected_server_request"
                        break
                    phase.consume(event, sequence)
        except (TimeoutError, RuntimeError, ValueError, OSError) as error:
            phase.failure = str(error)
        except KeyboardInterrupt:
            phase.failure = "cancelled"
        except BaseException:
            self.close()
            raise
        if phase.failure:
            self.stopped = True
            cancellation = self.cancel(phase, grace)
            return {**phase.report(), "cancellation": cancellation, "exit_code": self.close()}
        return {**phase.report(), "cancellation": "not_requested"}

    def cancel(self, phase, grace):
        deadline, interrupted = time.monotonic() + grace, False
        reason = phase.failure
        while time.monotonic() < deadline:
            try:
                if phase.turn_id and not interrupted and phase.terminal is None:
                    self.send("turn/interrupt", {"threadId": phase.thread_id, "turnId": phase.turn_id})
                    interrupted = True
                if phase.terminal in ("completed", "failed", "interrupted"):
                    return "terminal_confirmed"
                received = self.receive(deadline)
                if received:
                    sequence, event = received
                    # A late turn/start response can reveal the turn to cancel.
                    phase.consume(event, sequence)
                    phase.failure = reason
            except (TimeoutError, RuntimeError, ValueError, OSError):
                break
        return "cancellation_unconfirmed"

    def close(self):
        if self.closed:
            return self.process.returncode
        self.closed = True
        self.stopped = True
        # Only this session's process group, including its spawned MCP bridge.
        # Always clean the group even if the app-server leader already exited.
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=3)
        self.reader.join(timeout=1)
        self.process.stdin.close()
        self.process.stdout.close()
        return self.process.returncode
