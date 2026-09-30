"""Lifecycle contracts for the bounded Codex native-compaction smoke.

Usage snapshots are evidence, not a billing sum.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from .tasks import BUILTIN_TASKS, tasks_in

LIMITS = {"seed": 60, "compact": 90, "continuation": 180}
TOKEN_KEYS = ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens")
SCENARIOS = ("fixed-policy", "policy-revision")
REVISION_FIXTURE = Path(__file__).with_name('fixtures') / 'native-policy-revision.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def native_plan(model=None, effort="low", scenario="fixed-policy"):
    if scenario not in SCENARIOS:
        raise ValueError('unknown native scenario')
    tasks = {t["spec"]["id"]: t for t in tasks_in(BUILTIN_TASKS)}
    pairs = []
    for suffix, arms in (("a", ["control", "native-compact"]), ("b", ["native-compact", "control"])):
        task = tasks[f"visible-policy-{suffix}"]
        # Only user requirements become the new real user turn. No fabricated
        # assistant/tool messages or reconstructed history are sent to Codex.
        seed = "\n\n".join([task["history"][0]["content"], task["history"][2]["content"],
                            "Remember this decision for the later coding task. Do not call tools or modify files yet. Confirm briefly and wait."])
        pairs.append({"task": task["spec"]["id"], "task_sha256": task["digest"], "arms": arms,
                      "seed_text": seed, "seed_sha256": hashlib.sha256(seed.encode()).hexdigest(),
                      "request": task["spec"]["request"], "request_sha256": hashlib.sha256(task["spec"]["request"].encode()).hexdigest()})
    plan = {"protocol": "codex-native-compaction-smoke-v1", "execution": "plan-only",
            "model": model, "effort": effort, "seeds": 2, "compactions": 2, "continuations": 4,
            "timeouts_seconds": LIMITS, "continuation_tool_budget": 16, "seed_tool_budget": 0,
            "cancellation_grace_seconds": 3, "model_phase_timeout_budget_seconds": 1020,
            "usage_contract": "unverified; phase usage null, arm total incomplete", "pairs": pairs}
    if scenario == 'policy-revision':
        fixture_bytes = REVISION_FIXTURE.read_bytes()
        fixture = json.loads(fixture_bytes)
        initial = {pair['task']: pair for pair in pairs}
        revisions = []
        for case in fixture['pairs']:
            pair = deepcopy(initial[case['initial_task']])
            pair.update(case, task_sha256=tasks[case['task']]['digest'],
                        initial_task_sha256=tasks[case['initial_task']]['digest'],
                        revision_sha256=hashlib.sha256(case['revision_text'].encode()).hexdigest(),
                        request=fixture['request'], request_sha256=hashlib.sha256(fixture['request'].encode()).hexdigest())
            revisions.append(pair)
        plan.update(protocol='codex-native-policy-revision-v1', scenario=scenario,
                    fixture_sha256=hashlib.sha256(fixture_bytes).hexdigest(), pairs=revisions,
                    seeds=4, initial_turns=2, revision_turns=2, model_phase_timeout_budget_seconds=1140)
    return plan


def isolated_config(inherited, bridge_args, model, effort):
    """Return thread overrides and CLI arguments; never mutate user config.

    The caller must obtain the effective inherited config without logging it,
    apply overrides at BOTH process and thread startup, and verify tool catalog.
    """
    if inherited.get("hooks"):
        raise ValueError("inherited_hooks_require_review")
    values = {f"features.{name}": False for name in
              ("apps", "plugins", "hooks", "skill_search", "skill_mcp_dependency_install", "shell_tool", "multi_agent")}
    values.update({"features.skip_host_skill_discovery": True, "web_search": "disabled", "notify": [],
                   "project_doc_max_bytes": 0, "sandbox_mode": "read-only", "approval_policy": "on-request",
                   "approvals_reviewer": "user", "model_reasoning_effort": effort})
    if model:
        values["model"] = model
    for name in inherited.get("mcp_servers", {}):
        values[f"mcp_servers.{name}.enabled"] = False
    for name in inherited.get("plugins", {}):
        values[f"plugins.{name}.enabled"] = False
    values.update({"mcp_servers.acr.enabled": True, "mcp_servers.acr.command": bridge_args[0],
                   "mcp_servers.acr.args": bridge_args[1:]})
    # Codex's dotted-key parser treats quote characters as part of the name.
    # Quote TOML values, not MCP/plugin path segments (also in thread config).
    cli = []
    for key, value in values.items():
        cli.extend(["-c", f"{key}={json.dumps(value)}"])
    return values, ["app-server", "--listen", "stdio://", *cli]


def boundary_fingerprint(thread):
    turns = deepcopy(thread["turns"])
    if not turns or any(t["status"] != "completed" for t in turns):
        raise ValueError("boundary_not_completed")
    for turn in turns:
        for key in ("id", "startedAt", "completedAt", "durationMs"):
            turn.pop(key, None)
        for item in turn["items"]:
            item.pop("id", None)
            if item["type"] == "contextCompaction":
                raise ValueError("comparison_contaminated")
    return digest(turns)


def check_fork(seed, fork, last_turn_id):
    if seed["turns"][-1]["id"] != last_turn_id or fork["forkedFromId"] != seed["id"] or fork["id"] == seed["id"]:
        raise ValueError("fork_boundary_mismatch")
    if boundary_fingerprint(seed) != boundary_fingerprint(fork):
        raise ValueError("fork_boundary_mismatch")
    return boundary_fingerprint(seed)


class Phase:
    """Consume only events received after dispatch, on one idle thread.

    Native success needs the new turn's compaction item AND completed terminal.
    The RPC ack, legacy notification and unrelated events cannot satisfy it.
    """
    def __init__(self, kind, thread_id, request_id, start_sequence, previous_turn_id=None):
        self.kind, self.thread_id, self.request_id = kind, thread_id, request_id
        self.start_sequence, self.previous_turn_id = start_sequence, previous_turn_id
        self.turn_id = None
        self.acked = False
        self.evidence = []
        self.terminal = None
        self.failure = None
        self.compactions = set()
        self.tools = set()
        self.pending_tools = {}
        self.usage_events = []
        self.usage_issue = "missing"

    def bind(self, turn_id):
        if not turn_id or turn_id == self.previous_turn_id or (self.turn_id and self.turn_id != turn_id):
            self.failure = "turn_boundary_mismatch"
        else:
            self.turn_id = turn_id

    def consume(self, event, sequence):
        if sequence <= self.start_sequence:
            return
        if event.get("id") == self.request_id and "method" not in event:
            if "error" in event:
                self.failure = "rpc_error"
            else:
                self.acked = True
                self.evidence.append({"sequence": sequence, "event": "rpc_ack"})
                if self.kind != "compact":
                    self.bind(event["result"]["turn"]["id"])
            return
        p, method = event.get("params", {}), event.get("method")
        if p.get("threadId") != self.thread_id:
            return
        item = p.get("item", {})
        if method == "thread/compacted" or item.get("type") == "contextCompaction":
            if self.kind != "compact":
                self.failure = "comparison_contaminated"
        if method == "turn/started":
            self.bind(p["turn"]["id"])
            self.evidence.append({"sequence": sequence, "event": "turn_started", "turn_id": p["turn"]["id"]})
        turn_id = p.get("turnId") or p.get("turn", {}).get("id")
        if not self.turn_id or turn_id != self.turn_id:
            return
        if method == "turn/completed":
            self.terminal = p["turn"]["status"]
            self.evidence.append({"sequence": sequence, "event": "turn_completed", "turn_id": self.turn_id, "status": self.terminal})
            if self.terminal != "completed":
                self.failure = "turn_" + self.terminal
        elif method == "item/completed" and item.get("type") == "contextCompaction":
            self.compactions.add(item["id"])
            self.evidence.append({"sequence": sequence, "event": "compaction_completed", "turn_id": self.turn_id, "item_id": item["id"]})
        elif method == "item/started" and item.get("type") in ("mcpToolCall", "commandExecution", "webSearch", "collabAgentToolCall"):
            self.tools.add(item["id"])
            if item["type"] == "mcpToolCall":
                self.pending_tools[item["id"]] = deepcopy(item)
            if len(self.tools) > (16 if self.kind == "continuation" else 0):
                self.failure = "tool_budget"
        elif method == "item/completed" and item.get("type") == "mcpToolCall":
            self.pending_tools.pop(item["id"], None)
            if item.get("status") == "failed" or item.get("error"):
                self.failure = "tool_failed"
        elif method == "thread/tokenUsage/updated":
            self.usage_events.append({"sequence": sequence, "notification": deepcopy(p)})
            total = p["tokenUsage"].get("total", {})
            if any(type(total.get(k)) is not int or total[k] < 0 for k in TOKEN_KEYS):
                self.usage_issue = "missing_fields"
            elif len(self.usage_events) > 1 and any(
                    type(previous := self.usage_events[-2]["notification"]["tokenUsage"].get("total", {}).get(k)) is int
                    and total[k] < previous for k in TOKEN_KEYS):
                self.usage_issue = "counter_regression"
            elif self.usage_issue == "missing":
                self.usage_issue = "contract_unverified"

    @property
    def completed(self):
        return not self.failure and self.acked and self.terminal == "completed" and (self.kind != "compact" or bool(self.compactions))

    def report(self):
        return {"status": self.failure or ("completed" if self.completed else "incomplete"),
                "request_id": self.request_id, "start_sequence": self.start_sequence, "evidence": self.evidence,
                "turn_id": self.turn_id, "terminal": self.terminal,
                "compaction_item_ids": sorted(self.compactions), "tool_calls": len(self.tools),
                "usage": None, "usage_coverage": "unavailable", "usage_issue": self.usage_issue,
                "usage_events": self.usage_events, "arm_total": None, "arm_total_coverage": "incomplete"}
