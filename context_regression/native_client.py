"""Small owned-process stdio adapter, exercised with scripted peers offline."""
import json
import os
from collections import deque
import selectors
import signal
import subprocess
import time

from .native import Phase


class AppServer:
    def __init__(self, command, cwd, trace):
        self.serial = self.sequence = 0
        self.stopped = False
        self.closed = False
        self.messages = deque()
        self.buffer = b""
        self.eof = False
        self.trace = trace
        env = dict(os.environ)
        env.pop("OPENAI_API_KEY", None)
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        bufsize=0, start_new_session=True)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)

    def drain(self, deadline, wait=0):
        """Consume readable bytes in this thread, bounded by the stage deadline."""
        while not self.eof:
            if time.monotonic() >= deadline:
                raise TimeoutError("phase_timeout")
            if not self.selector.select(wait):
                return
            wait = 0
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                self.eof = True
                if self.buffer:
                    raise ValueError("incomplete_event_at_eof")
                return
            self.buffer += data
            while b"\n" in self.buffer:
                if time.monotonic() >= deadline:
                    raise TimeoutError("phase_timeout")
                line, self.buffer = self.buffer.split(b"\n", 1)
                event = json.loads(line)
                self.sequence += 1
                self.trace.append({"direction": "receive", "sequence": self.sequence, "message": event})
                self.messages.append((self.sequence, event))

    def send(self, method, params):
        self.serial += 1
        message = {"id": self.serial, "method": method, "params": params}
        self.trace.append({"direction": "send", "message": message})
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()
        return self.serial

    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("phase_timeout")
        if not self.messages:
            self.drain(deadline, min(remaining, 0.05))
        if self.messages:
            return self.messages.popleft()
        if self.eof:
            raise RuntimeError("app_server_closed")
        return None

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
            self.drain(deadline)
            if self.buffer:
                raise RuntimeError("partial_event_before_dispatch")
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
            self.process.poll()
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except PermissionError:
                # macOS can reject signalling an exited, unreaped group leader.
                self.process.wait(timeout=3)
                os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            self.process.wait(timeout=3)
            self.selector.close()
            self.process.stdin.close()
            self.process.stdout.close()
        return self.process.returncode
