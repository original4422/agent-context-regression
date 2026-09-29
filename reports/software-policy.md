# Software-policy checkpoints

This extension adds two hand-authored tasks with reconstructed engineering conversations. Both are pure Python functions over JSON values. The conversations contain concrete design proposals, rejected alternatives, checkpoint observations, and pending changes; they do not come from native Codex compaction.

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
