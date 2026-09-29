# Agent Context Regression

Does a coding agent still produce the correct change after its context is shortened?

This CLI resumes small coding tasks from fixed source checkpoints under three context strategies. Independent executable checks evaluate the resulting code. It measures corrected requirements that were lost, task success, total tokens, and elapsed time—including automatic summary generation.

The built-in suite contains **four hand-authored Python microtasks with reconstructed conversations**. It tests controlled context reconstruction, not Codex's native compaction or production conversation memory.

## Run

Requires Python 3.11+, a logged-in Codex CLI supporting `exec --ignore-user-config`, and its working OS sandbox. The measured platform is macOS; Linux execution has not been measured. Python code uses only the standard library.

```sh
git clone https://github.com/original4422/agent-context-regression.git
cd agent-context-regression
python3 -m context_regression list
python3 -m unittest discover -s tests -v

# Existing Codex login; no separate model API key is used.
# Choose a model available to your account; it is held fixed for all phases.
python3 -m context_regression run --model gpt-6-sol
```

Defaults run 4 tasks × 3 strategies × 2 repetitions: **24 continuations plus 8 summary generations**, serially. Each continuation has a 180-second timeout and 16-tool-call budget; each summary has 90 seconds and a 4,096-character limit. Infrastructure failures abort the batch; failed code checks remain valid outcomes and do not stop it.

The CLI prints a private result directory under `~/.local/state/agent-context-regression/`. Raw prompts, events, summaries and candidate files stay there, behind a mode-0700 directory. To render the metrics:

```sh
python3 -m context_regression summarize /path/from/run/results.json

# Optional installation provides the equivalent `acr` command.
python3 -m pip install .
acr list
```

## Comparison

| Strategy | Retained context | Extra model phase |
| --- | --- | --- |
| `full` | All supplied messages | None |
| `recent` | Most recent user turn and its assistant/tool messages | None |
| `structured` | Automatically generated objective, constraints, rejected approaches, observations and next steps | Same model and effort as continuation |

The current request is identical across strategies. Each attempt starts from a fresh copy of the same source snapshot. A seeded schedule shuffles task/repetition groups and rotates/reverses strategy order within groups. The schedule, task fingerprints, runner fingerprint, model, effort and budgets are saved with the results.

The agent has four MCP tools: list files, read a listed file, replace a listed file, and run public smoke checks. Native shell and web search are disabled. This is a constrained coding loop: the agent edits and executes actual Python code, with the same capabilities in every arm.

Public checks are deliberately incomplete. Acceptance scripts stay outside the candidate workspace and run afterward under Codex's read-only OS sandbox. Neither file tools nor executed candidate code can rewrite those scripts. A sandbox regression test verifies an attempted overwrite is denied. The harness also fingerprints task files before and after each attempt.

## Tasks and outcomes

| Task | Pending work | Earlier requirement checked independently |
| --- | --- | --- |
| Case-sensitive slugs | Normalize punctuation | Preserve existing URL casing |
| Explicit empty overrides | Implement `None` inheritance | Keep empty strings, `0` and `False` |
| Retry method policy | Add rate-limit retries and finish policy | Respect the exact method allowlist |
| Event window order | Add deduplication and finish window selection | Exclude the right endpoint; keep ingestion order |

Acceptance checks return named booleans. A task passes only when every check passes. `regressions` lists failures of designated corrected requirements; it reports observable behavior, not an inference about the model's internal memory. No LLM judge is used.

Token totals include summary and continuation phases. Cached input is reported separately as a **subset** of input tokens. Token counts are not dollar costs or subscription quota units. End-to-end wall time includes independent verification. Missing usage stays missing; an aborted batch is not presented as a complete comparison.

## Add a task

Pass `--tasks /path/to/tasks` to `list` or `run`. Each child directory contains:

```text
my-task/
  task.json        # id, title, module, editable, request, regression_checks, provenance
  history.json     # [{"role": "user|assistant|tool", "content": "..."}, ...]
  snapshot/        # initial candidate files; never contains acceptance tests
  public.py        # CHECKS: dict[str, callable(candidate_module) -> bool]
  oracle.py        # same interface; independent acceptance checks
```

Copy a [built-in task](context_regression/tasks/explicit-empty-overrides) for the exact schema. Use trusted Python check scripts; task definitions are executable code. The current adapter loads one Python module and exposes only the files listed in `editable`. Changing strategy logic is a small edit to `runner.py`; adding general agent/provider adapters is outside this first version.

Useful controls:

```sh
acr run --model gpt-6-sol --task retry-method-policy --repetitions 1
acr run --model gpt-6-sol --recent-turns 2 --seed 42 --effort medium
```

The microtasks intentionally contain requirements that are easy to lose. Results describe these tasks and this constrained tool surface; four tasks and two repetitions are a regression pilot, not a general ranking of compression methods.

## Related work and attribution

[CompactBench](https://github.com/compactbench/compactbench) evaluates compaction through probes and multi-cycle drift. [Hermes compression eval](https://github.com/NousResearch/hermes-compression-eval) evaluates continuation probes using LLM grading. [LongMemEval-V2](https://github.com/xiaowu0162/LongMemEval-V2) evaluates memory over agent trajectories. This project focuses on executable code outcomes at fixed intermediate checkpoints.

The runner, task fixtures and checks in this repository are original work. Codex CLI and the Model Context Protocol are external interfaces; their implementations are not vendored. MIT © 2026 Daniel Peng (original4422).
