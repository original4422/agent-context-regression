# Software-policy checkpoints

This extension adds two hand-authored tasks with reconstructed engineering conversations. Both are pure Python functions over JSON values. The conversations contain concrete design proposals, rejected alternatives, checkpoint observations, and pending changes; they do not come from native Codex compaction.

## Measured outcome

The frozen batch completed all **12 continuations and 4 summaries** at [`af4840c`](https://github.com/original4422/agent-context-regression/tree/af4840c). No attempts were replaced. Codex CLI 0.155.1 used `gpt-6-sol` with low reasoning. [Environment](software-policy-environment.json), [machine-readable results](software-policy-results.json), [every outcome](software-policy-outcomes.md), and [independent recheck](software-policy-recheck.json) are available.

| Strategy | Passed | Designated correction failures | Input + output tokens | Median end-to-end seconds |
| --- | ---: | ---: | ---: | ---: |
| Full | 4/4 | 0 | 397,160 | 31.91 |
| Recent | 3/4 | 0 | 386,616 | 32.48 |
| Structured | 4/4 | 0 | 460,791 | 51.88 |

All six deployment continuations passed. For authorization, one recent-turn candidate required exact tenant equality and therefore rejected a wildcard-tenant grant. Its resource/action and role wildcards worked; the failing independent check was `wildcard_scope`. This requirement appeared in the initial contract rather than a later correction, so it is an overall failure but not a designated correction regression. The other eleven candidates passed every check.

Most constraints survived even the recent-turn condition. Inspection of the returned functions is consistent with agents reconstructing conventional scheduling and access-control rules from the checkpoint schema; this is an interpretation, not direct evidence about internal memory. Increased rule complexity alone did not yield a strong discriminator for corrected-requirement retention. The structured arm passed, while adding summary time and tokens.

### Phase accounting

| Strategy | Phase | Count | Input | Cached input (subset) | Output | Median phase seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Full | Continuation | 4 | 395,083 | 345,472 | 2,077 | 31.30 |
| Recent | Continuation | 4 | 384,133 | 364,160 | 2,483 | 32.05 |
| Structured | Summary | 4 | 62,744 | 28,160 | 1,538 | 20.30 |
| Structured | Continuation | 4 | 394,469 | 329,472 | 2,040 | 33.20 |

Each of the 16 private phase traces contained exactly one `turn.completed` event, and each recorded input/cached-input/output tuple matched that event. Cached input is not added to input again. Summary costs are included once per structured attempt. Total tokens are CLI counts, not subscription allowance units. End-to-end time includes setup and process-isolated verification; phase medians should not be added to reconstruct the median of per-attempt totals.

Mean retained context sizes were 1,979 characters (full), 233 (recent) and 1,851.5 (structured). No history was extended with filler. The measurement ran serially after the browser experiment and the local MLX service finished. All twelve saved candidates were subsequently rechecked under the real read-only sandbox with identical named outcomes; task and runner fingerprints still matched the frozen batch.

### Next experiment suggested by this result

A stronger retention test would pair tasks with identical source checkpoints, schemas and final requests but opposing explicit policy choices in their earlier histories. Such pairs would make a default coding convention insufficient to pass both versions. This batch does not contain those pairs, and its existing tasks and samples will remain unchanged.

## Requirements and retained context

| Task | Earlier requirements and corrections | Final incremental request | Independent outcomes |
| --- | --- | --- | --- |
| `rollout-dependency-admission` | Dependencies must be completed before the batch, not merely selected in it. Approval opens only the manual gate. Priority ties preserve input order. Skip jobs that do not fit and continue; do not optimize a knapsack. | Finish the shared capacity budget and run smoke checks. | Dependency readiness, unknown dependencies, approval scope, stable priority, skip-and-continue, exact fits, zero-cost jobs, and combined gates. |
| `scoped-policy-precedence` | Applicable denies override allows regardless of specificity/order. Tenant scope applies to denies too. Empty role lists match nobody. Validity is start-inclusive/end-exclusive, with `0` distinct from `None`. | Finish expiration support and run smoke checks. | Deny precedence, tenant isolation, empty roles, role intersection, wildcards, time endpoints, inactive denies, exact names, and default denial. |

Each checkpoint includes the function signature, input field/type schema and the unfinished implementation. The latest turn names the module and the incremental work; older turns supply the established contract. Consequently `recent` intentionally loses prior constraints, as it would when retaining only the latest turn of an ongoing implementation. This comparison measures cross-turn requirement retention; it does not ask whether the final turn is a complete standalone specification.

`full` receives all those corrections and observations. `recent` receives the final user turn and its assistant acknowledgement. `structured` receives an automatically produced summary of the full history, with the same 4,096-character limit as the pilot. The current request, starting files, tools and verification are identical between strategies.

## Frozen protocol

- Two tasks × three strategies × two repetitions: **12 continuations and 4 summaries**.
- Codex `gpt-6-sol`, low effort; seeded order `20260930`.
- Continuation: 180 seconds / 16 tool calls. Summary: 90 seconds / 4,096 characters.
- Existing trusted verifier computes outcomes from fresh sandboxed candidate workers. No LLM judge.
- Every candidate is retained privately and every attempted outcome is reported. A full-history failure remains a failure; it does not trigger resampling.
- Summary and continuation token/time costs are reported separately and together. Input caching is a subset of input usage.
- The original four-task pilot and its measurement files are unchanged. Its timings use an older verifier and should not be pooled with this extension.

```sh
python3 -m context_regression run --model gpt-6-sol --effort low \
  --task rollout-dependency-admission --task scoped-policy-precedence \
  --repetitions 2 --seed 20260930 --recent-turns 1 \
  --summary-chars 4096 --summary-timeout 90 --timeout 180 --max-tools 16
```

## Offline task validation

The reference implementations pass all public and independent checks, including the real Codex read-only sandbox. The checkpoints fail both check sets. Twelve intentionally wrong implementations exercise twelve concrete violations. Every designated historical correction has a counterexample that **passes public smoke checks but fails the independent oracle**, so passing smoke is insufficient to satisfy the established contract. The reference implementations and mutation catalogue live in `tests/policy_fixtures.py`; they never enter candidate workspaces.
