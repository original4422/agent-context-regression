import hashlib
import json
import os
from pathlib import Path
import queue
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from .checks import run_checks
from .tasks import recent_turns, render_history, task_digest

STRATEGIES = ("full", "recent", "structured")
BRIDGE = Path(__file__).with_name("bridge.py")
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
SUMMARY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {key: {"type": "string"} for key in
                   ("objective", "constraints", "rejected_approaches", "observations", "next_steps")},
    "required": ["objective", "constraints", "rejected_approaches", "observations", "next_steps"],
}


class RunFailure(RuntimeError):
    def __init__(self, reason, phase):
        super().__init__(reason)
        self.phase = phase


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def schedule(tasks, repetitions, seed):
    """Seeded task order, cyclic strategy order, reversed on alternating repeats."""
    rng = random.Random(seed)
    groups = [(task, repeat) for repeat in range(repetitions) for task in tasks]
    rng.shuffle(groups)
    result = []
    for index, (task, repeat) in enumerate(groups):
        offset = index % len(STRATEGIES)
        order = list(STRATEGIES[offset:] + STRATEGIES[:offset])
        if repeat % 2:
            order.reverse()
        result.extend((task, repeat, strategy) for strategy in order)
    return result


def codex_args(config, workspace, output, *, task=None, schema=None):
    args = [config["codex"], "exec", "--json", "--ephemeral", "--ignore-user-config",
            "--ignore-rules", "--skip-git-repo-check", "--sandbox", "read-only",
            "--model", config["model"], "--color", "never", "-C", str(workspace),
            "--output-last-message", str(output)]
    values = {"approval_policy": "never", "model_reasoning_effort": config["effort"],
              "web_search": "disabled", "project_doc_max_bytes": 0,
              "features.shell_tool": False, "features.multi_agent": False}
    if task:
        values["mcp_servers.acr.command"] = sys.executable
        # These four local fixture tools are explicitly authorized by `run`.
        # Other MCP servers and native commands receive no approval override.
        values["mcp_servers.acr.default_tools_approval_mode"] = "approve"
        values["mcp_servers.acr.args"] = ["-I", "-B", str(BRIDGE), str(task["path"]),
                                           str(workspace), config["codex"], str(os.getpid())]
    for key, value in values.items():
        args.extend(["-c", f"{key}={json.dumps(value)}"])
    if schema:
        args.extend(["--output-schema", str(schema)])
    return args + ["-"]


def stop_process(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def run_codex(args, prompt, private, timeout, max_tools):
    private.mkdir(mode=0o700)
    (private / "prompt.txt").write_text(prompt)
    started = time.monotonic()
    usage, tool_calls, failure = None, 0, None
    messages = queue.Queue()
    env = dict(os.environ)
    # Keep the user's existing Codex login; never select a separately billed API key.
    env.pop("OPENAI_API_KEY", None)
    with (private / "events.jsonl").open("w") as events, (private / "stderr.log").open("w") as errors:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                text=True, env=env, start_new_session=True)
        def read_events():
            for line in proc.stdout:
                messages.put(line)
            messages.put(None)
        reader = threading.Thread(target=read_events, daemon=True)
        reader.start()
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    failure = "timeout"
                    break
                try:
                    line = messages.get(timeout=remaining)
                except queue.Empty:
                    failure = "timeout"
                    break
                if line is None:
                    break
                events.write(line)
                events.flush()
                event = json.loads(line)
                if event.get("type") == "turn.completed":
                    reported = event["usage"]
                    if any(type(reported.get(key)) is not int for key in USAGE_KEYS):
                        failure = "missing_usage"
                        break
                    usage = {key: (usage or {}).get(key, 0) + reported[key] for key in USAGE_KEYS}
                if event.get("type") == "turn.failed":
                    failure = "turn_failed"
                    break
                item = event.get("item", {})
                if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
                    if item.get("status") == "failed" or (item.get("result") or {}).get("isError"):
                        failure = "tool_failure"
                        break
                if event.get("type") == "item.started" and event.get("item", {}).get("type") == "mcp_tool_call":
                    tool_calls += 1
                    if tool_calls > max_tools:
                        failure = "tool_budget"
                        break
            if failure:
                stop_process(proc)
            else:
                proc.wait(timeout=max(0.1, timeout - (time.monotonic() - started)))
        except KeyboardInterrupt:
            failure = "interrupted"
            stop_process(proc)
        except (json.JSONDecodeError, BrokenPipeError, subprocess.TimeoutExpired) as error:
            failure = type(error).__name__
            stop_process(proc)
        except BaseException:
            stop_process(proc)
            raise
        finally:
            reader.join(timeout=2)
            proc.stdout.close()
            while not messages.empty():
                line = messages.get_nowait()
                if line:
                    events.write(line)
        if not failure and proc.returncode:
            failure = "nonzero_exit"
        if not failure and usage is None:
            failure = "missing_usage"
    phase = {"elapsed_seconds": round(time.monotonic() - started, 3), "usage": usage,
             "tool_calls": tool_calls, "exit_code": proc.returncode, "status": failure or "completed"}
    if failure:
        raise RunFailure(failure, phase)
    return phase


def phase_total(phases):
    values = list(phases.values())
    complete = bool(values) and all(phase["usage"] is not None for phase in values)
    return {"usage": {key: sum(phase["usage"][key] for phase in values) for key in USAGE_KEYS} if complete else None,
            "elapsed_seconds": round(sum(phase["elapsed_seconds"] for phase in values), 3)}


def continuation_prompt(task, context):
    return f"""Continue a coding task from the supplied checkpoint and retained context.
Use only the acr MCP tools to inspect/edit listed files and run public smoke checks.
Do not access other files, use other tools, or change tests. Public checks are incomplete;
the requirements in the retained context define correctness. Make the code changes now.

RETAINED CONTEXT (a controlled reconstruction, not native session history):
{context}

CURRENT REQUEST:
{task['spec']['request']}
Finish with a brief description of the change and checks you ran.
"""


def run_batch(tasks, config, private):
    private = Path(private).resolve()
    private.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(private, 0o700)
    planned = schedule(tasks, config["repetitions"], config["seed"])
    report = {"schema_version": 1, "status": "running", "config": {k: v for k, v in config.items() if k != "codex"},
              "codex_version": subprocess.check_output([config["codex"], "--version"], text=True).strip(),
              "scope": "Controlled reconstructed contexts; not native Codex compaction. Hand-authored coding tasks.",
              "tasks": [{"id": t["spec"]["id"], "sha256": t["digest"], "provenance": t["spec"]["provenance"]} for t in tasks],
              "planned_runs": len(planned), "rows": []}
    source_files = sorted(Path(__file__).parent.glob("*.py"))
    report["runner_sha256"] = hashlib.sha256(b"".join(p.name.encode() + p.read_bytes() for p in source_files)).hexdigest()
    report["order"] = [{"task": t["spec"]["id"], "repeat": r + 1, "strategy": s} for t, r, s in planned]
    write_json(private / "results.json", report)
    try:
        for index, (task, repeat, strategy) in enumerate(planned):
            if task_digest(task["path"]) != task["digest"]:
                raise RuntimeError("Task definition changed during batch")
            row = {"index": index + 1, "task": task["spec"]["id"], "repeat": repeat + 1,
                   "strategy": strategy, "status": "running", "phases": {}}
            report["rows"].append(row)
            attempt = private / f"{index + 1:02d}-{task['spec']['id']}-{strategy}"
            attempt.mkdir(mode=0o700)
            started = time.monotonic()
            current_phase = "setup"
            print(f"[{index + 1}/{len(planned)}] {row['task']} {strategy} repeat={repeat + 1}", flush=True)
            try:
                with tempfile.TemporaryDirectory(prefix="acr-") as temporary:
                    workspace = Path(temporary) / "work"
                    shutil.copytree(task["path"] / "snapshot", workspace)
                    if strategy == "structured":
                        current_phase = "summary"
                        schema = attempt / "summary-schema.json"
                        write_json(schema, SUMMARY_SCHEMA)
                        output = attempt / "summary.json"
                        summary_prompt = f"""Compress the following coding-task history for another agent.
Preserve current requirements, corrections, rejected approaches, verified observations and pending work.
Return the required JSON object. Total JSON length must be at most {config['summary_chars']} characters.
Use only the provided history. Do not inspect files or call tools.
HISTORY:
{render_history(task['history'])}
"""
                        # An empty separate workspace prevents the summarizer from seeing the checkpoint.
                        summary_workspace = Path(temporary) / "summary"
                        summary_workspace.mkdir()
                        row["phases"]["summary"] = run_codex(
                            codex_args(config, summary_workspace, output, schema=schema), summary_prompt,
                            attempt / "summary", config["summary_timeout"], 0)
                        summary = json.loads(output.read_text())
                        if set(summary) != set(SUMMARY_SCHEMA["required"]) or any(not isinstance(v, str) for v in summary.values()):
                            raise RuntimeError("Invalid structured summary")
                        context = json.dumps(summary, ensure_ascii=False)
                        if len(context) > config["summary_chars"]:
                            raise RuntimeError("Structured summary exceeded its character budget")
                    elif strategy == "recent":
                        context = render_history(recent_turns(task["history"], config["recent_turns"]))
                    else:
                        context = render_history(task["history"])
                    row["retained_context_chars"] = len(context)
                    row["retained_context_sha256"] = hashlib.sha256(context.encode()).hexdigest()
                    current_phase = "continuation"
                    row["phases"]["continuation"] = run_codex(
                        codex_args(config, workspace, attempt / "answer.txt", task=task),
                        continuation_prompt(task, context), attempt / "continuation",
                        config["timeout"], config["max_tools"])
                    current_phase = "verification"
                    row["verification"] = run_checks(task["path"], workspace, "oracle", config["codex"])
                    # Keep source and raw traces private. Public output only contains checks and metrics.
                    shutil.copytree(workspace, attempt / "candidate")
                    failed = {c["name"] for c in row["verification"]["checks"] if not c["passed"]}
                    row["regressions"] = sorted(failed & set(task["spec"]["regression_checks"]))
                    if task_digest(task["path"]) != task["digest"]:
                        raise RuntimeError("Task definition changed during candidate execution")
                    row["status"] = "completed"
            except BaseException as error:
                if isinstance(error, RunFailure):
                    row["phases"][current_phase] = error.phase
                row["status"] = "aborted"
                row["failure_phase"] = current_phase
                row["failure_type"] = type(error).__name__
                (attempt / "failure.txt").write_text(str(error))
                raise
            finally:
                row["total"] = phase_total(row["phases"])
                row["wall_seconds"] = round(time.monotonic() - started, 3)
                write_json(private / "results.json", report)
        report["status"] = "completed"
    except BaseException:
        report["status"] = "aborted"
        raise
    finally:
        write_json(private / "results.json", report)
    return report
