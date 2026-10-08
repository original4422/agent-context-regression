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
        self.sensitive_ids = set()
        self.notifications = []
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
                # Keep this ID set for the process lifetime: a timed-out
                # config/read response is still sensitive when it arrives late.
                if "method" in event or event.get("id") not in self.sensitive_ids:
                    self.trace.append({"direction": "receive", "sequence": self.sequence, "message": event})
                self.messages.append((self.sequence, event))

    def send(self, method, params):
        self.serial += 1
        if method == "config/read":
            self.sensitive_ids.add(self.serial)
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

    def request(self, method, params, timeout=15):
        """Serial, no-model preflight RPCs only; notifications remain observable."""
        if method not in {"initialize", "config/read", "thread/start", "mcpServer/tool/call"}:
            raise ValueError("unsupported_preflight_method")
        return self._rpc(method, params, timeout)

    def lifecycle(self, method, params, timeout=15):
        """The two additional lifecycle calls needed by the live smoke."""
        if method not in {"thread/read", "thread/fork"}:
            raise ValueError("unsupported_lifecycle_method")
        return self._rpc(method, params, timeout)

    def _rpc(self, method, params, timeout):
        deadline = time.monotonic() + timeout
        try:
            request_id = self.send(method, params)
            while True:
                received = self.receive(deadline)
                if not received:
                    continue
                _, event = received
                if "method" in event:
                    if "id" in event:
                        raise RuntimeError("unexpected_server_request:" + event["method"])
                    self.notifications.append(event)
                elif event.get("id") == request_id:
                    if "error" in event:
                        # config/read errors may contain sensitive inherited values.
                        raise RuntimeError("rpc_error:" + method)
                    return event["result"]
        except BaseException:
            if method != "config/read":
                self.close()
            raise

    def initialize(self, timeout=15):
        result = self.request("initialize", {"clientInfo": {"name": "acr_native_preflight", "version": "1"},
                                             "capabilities": {"experimentalApi": True}}, timeout)
        self.process.stdin.write(b'{"method":"initialized","params":{}}\n')
        self.process.stdin.flush()
        return result

    def wait_notification(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while True:
            for event in self.notifications:
                if predicate(event):
                    return event
            received = self.receive(deadline)
            if received:
                _, event = received
                if "method" in event:
                    if "id" in event:
                        raise RuntimeError("unexpected_server_request:" + event["method"])
                    self.notifications.append(event)

    def phase(self, kind, thread_id, params, timeout, *, previous_turn_id=None, cancel=None, grace=3, approve=None):
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
                        if approve is None or kind not in ("continuation", "work"):
                            phase.failure = "unexpected_server_request"
                            break
                        result = approve(event, phase)
                        response = {"id": event["id"], "result": result}
                        self.trace.append({"direction": "send", "message": response})
                        self.process.stdin.write((json.dumps(response) + "\n").encode())
                        self.process.stdin.flush()
                    else:
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
