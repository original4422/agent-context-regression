# Counterfactual release-planning pair

The previous software-policy extension nearly saturated even with only the latest turn retained. This experiment changes an explicit business decision while holding the rest of the task fixed. It tests whether a continuation follows the supplied decision rather than whether a conventional implementation happens to satisfy one oracle.

## Measured result

The fixed **12-continuation / 4-summary** batch completed at [`5cbc325`](https://github.com/original4422/agent-context-regression/tree/5cbc325), with Codex CLI 0.155.1, `gpt-6-sol`, low reasoning. No attempt was replaced. [Environment](paired-policy-environment.json), [results JSON](paired-policy-results.json), [every own-policy outcome](paired-policy-outcomes.md), and [cross-scores and reconciliation](paired-policy-cross-scores.json) are public.

| Strategy | Requested-policy task success | A and B both pass, by repetition | Input + output tokens | Median end-to-end seconds |
| --- | ---: | ---: | ---: | ---: |
| Full | 4/4 | 2/2 | 396,924 | 30.38 |
| Recent | 0/4 | 0/2 | 524,573 | 42.67 |
| Structured | 4/4 | 2/2 | 456,567 | 46.53 |

Full and structured candidates followed both opposing contracts. All four recent candidates passed the B version of the dependency-policy discriminator and failed its A counterpart. However, all four also revisited previously skipped jobs, violating a rule shared by both contracts. Two used alphabetical rather than input-order ties. Thus every recent candidate failed **both complete oracles**; their failures cannot be attributed solely to choosing the opposite dependency policy.

| Strategy | Passes requested oracle | Passes only opposite oracle | Passes neither oracle |
| --- | ---: | ---: | ---: |
| Full | 4 | 0 | 0 |
| Recent | 0 | 0 | 4 |
| Structured | 4 | 0 | 0 |

The two alphabetical-tie implementations fail both `stable_priority_budget` and the ordered result in `manual_gate`; source inspection shows their boolean manual-approval gate itself is correct. Named checks report observable outputs rather than uniquely identifying a root cause.

All four actual recent prompt files have the same SHA-256 as the pre-measurement input audit. Each of the 12 saved candidates was re-evaluated against both oracles under the read-only sandbox; every own-policy result matched the original. Every phase had exactly one `turn.completed`, and all 16 usage records reconciled. The sampling window contained no other local model workload.

### Phase costs

| Strategy | Phase | Count | Input | Cached input (subset) | Output | Median phase seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full | Continuation | 4 | 395,127 | 379,648 | 1,797 | 29.93 |
| Recent | Continuation | 4 | 520,650 | 485,376 | 3,923 | 42.22 |
| Structured | Summary | 4 | 62,962 | 8,064 | 1,296 | 17.68 |
| Structured | Continuation | 4 | 390,361 | 363,648 | 1,948 | 28.01 |

Mean retained context sizes were 2,240 characters (full), 189 (recent) and 1,605.5 (structured). Summary generation is charged once per structured attempt in the reported totals; cached input is already included in input. These are CLI token counts, not subscription allowance units. End-to-end time includes verification and setup. Median phase times are not additive to the median of per-attempt totals.

This pair establishes identical recent observations and records which implementation each continuation produced. It does not isolate the entire success-rate gap to the one opposing decision: truncation also removes shared admission rules. A follow-up can retain every shared rule in both checkpoints while leaving only the differing decision in history. That follow-up is not part of this frozen batch, and these results remain unchanged.

To reproduce the cross-scoring with private traces retained by your own run:

```sh
python3 scripts/score_policy_pair.py /path/to/private/batch/results.json
```

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
- Offline tests compare the whole initial observation—prompt, tool schema, file listing, file contents and public outcomes—not merely context length. The four actual recent prompts were also compared after execution.

The recent condition is intentionally unidentifiable: its supplied input has no signal distinguishing A from B. Independently sampled outputs can still choose different policies by chance. Two repetitions and their pair pass rate cannot establish a population estimate of memory ability.

## Frozen protocol

One pair × two policy versions × three context strategies × two repetitions = **12 continuations plus 4 summaries**. Use `gpt-6-sol`, low reasoning, seed `20260930`, one recent turn, summary limit 4,096 characters/90 seconds, and continuation budget 16 tool calls/180 seconds. All runs are serial. No failed attempt will be replaced or used to tune the frozen tasks.

```sh
python3 -m context_regression run --model gpt-6-sol --effort low \
  --task wave-policy-a --task wave-policy-b --repetitions 2 --seed 20260930 \
  --recent-turns 1 --summary-chars 4096 --summary-timeout 90 \
  --timeout 180 --max-tools 16
```

Report both per-strategy task success and **pair success**: for a given strategy/repetition, did its A continuation pass A and its B continuation pass B? Every saved candidate additionally runs against both oracles. This separates passing its requested policy, implementing the opposite policy, and failing both. Token/time accounting includes automatic summary generation. Earlier tasks and measured results are unchanged.
