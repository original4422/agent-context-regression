# Counterfactual release-planning pair

The previous software-policy extension nearly saturated even with only the latest turn retained. This experiment changes an explicit business decision while holding the rest of the task fixed. It tests whether a continuation follows the supplied decision rather than whether a conventional implementation happens to satisfy one oracle.

## Two legitimate contracts

- **A: concurrent launch wave.** The launcher starts all selected jobs immediately. Only jobs in the initial `completed` set satisfy dependencies; selecting a prerequisite does not make its dependent safe to launch yet.
- **B: sequential execution plan.** The executor runs selected jobs in returned order, waits for each to succeed, and stops on failure. A prerequisite selected earlier in the plan can therefore satisfy a later job's dependency.

Both functions receive the same schema and return ordered ids. Both scan once in stable descending priority, respect approval and capacity, skip oversized jobs, and never revisit earlier skipped jobs. The single differing history message is an explicit user decision with its product rationale. The checkpoint is intentionally unfinished under both policies.

For the identical input `base` followed by `app` depending on `base`, with no completed jobs and capacity two, A requires `["base"]`; B requires `["base", "app"]`. No single deterministic implementation can satisfy both oracles on this input. The oracle also checks a three-job dependency chain, alongside shared constraints.

## Controls and input audit

[Input fingerprints](paired-policy-inputs.json) record every shared component. Run `python3 scripts/audit_policy_pair.py` to regenerate the audit.

- The full recent continuation prompt, source checkpoint, input schema, file names, public check source, task title/request/provenance and MCP tool metadata are byte-identical between A and B.
- Exactly one earlier user message differs. All subsequent messages, including the final turn and current request, are identical.
- Task ids exist in private runner bookkeeping and public result labels, not the prompt or MCP responses. Candidate working directories have random `acr-` names. The file tool returns only `plan.py`, its contents, and named public outcomes, never an A/B policy label.
- Public checks use independent jobs or previously completed prerequisites and are policy-neutral. Both reference implementations pass them. Reference A passes oracle A and fails B only on `dependency_policy`; reference B does the reverse.
- Offline tests compare the whole initial observation—prompt, tool schema, file listing, file contents and public outcomes—not merely context length. Actual recent prompts will also be compared after execution.

The recent condition is intentionally unidentifiable: its supplied input has no signal distinguishing A from B. Independently sampled outputs can still choose different policies by chance. Two repetitions and their pair pass rate cannot establish a population estimate of memory ability.

## Frozen protocol

One pair × two policy versions × three context strategies × two repetitions = **12 continuations plus 4 summaries**. Use `gpt-6-sol`, low reasoning, seed `20260930`, one recent turn, summary limit 4,096 characters/90 seconds, and continuation budget 16 tool calls/180 seconds. All runs are serial. No failed attempt will be replaced or used to tune the frozen tasks.

```sh
python3 -m context_regression run --model gpt-6-sol --effort low \
  --task wave-policy-a --task wave-policy-b --repetitions 2 --seed 20260930 \
  --recent-turns 1 --summary-chars 4096 --summary-timeout 90 \
  --timeout 180 --max-tools 16
```

Report both per-strategy task success and **pair success**: for a given strategy/repetition, did its A continuation pass A and its B continuation pass B? Every saved candidate will additionally run against both oracles. This separates passing its requested policy, implementing the opposite policy, and failing both. Token/time accounting includes automatic summary generation. Earlier tasks and measured results are unchanged.
