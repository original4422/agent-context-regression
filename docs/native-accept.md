# Accept saved native results

`native-run` reports whether a fixed sampling group completed. A candidate that follows the superseded policy remains a valid research outcome, so completion can exit 0 even when behavior fails. `native-accept` provides a separate, opt-in acceptance exit code for automation.

```sh
python3 -B -m context_regression native-accept reports/native-smoke.json --scenario fixed-policy
python3 -B -m context_regression native-accept reports/native-revision.json --scenario policy-revision
acr native-accept /path/to/new/run/public.json --scenario policy-revision
```

Python 3.11+ is sufficient. The required scenario selects one of two fixed contracts; the command reads a single JSON file and prints a verdict. The same function supports public.json and private results.json through their common fields. It does not read candidate files, credentials, configuration, raw traces or rollout files, and does not execute a model, oracle, worker process or network call. Input files are unchanged; output contains fixed anonymous case/arm/check names and controlled reason codes, not private identities or arbitrary error text.

| Exit | Verdict | Meaning |
| ---: | --- | --- |
| 0 | accepted | The fixed group is complete and all four candidates satisfy the target policy and shared rules |
| 1 | behavior_failed | A complete recorded group includes old/opposite policy, shared-rule or target-policy failures |
| 2 | invalid_result | Unreadable JSON, duplicate JSON keys, unsupported protocol/direction, wrong field types, duplicate or unknown structure, or an incomplete generated check list |
| 3 | run_incomplete | A valid partial run, missing phase/candidate/oracle, insufficient compact evidence, exceeded tool budget or unconfirmed integrity/cleanup |

An incomplete group takes precedence over any observed behavioral failures. Malformed consumed fields still return 2, including when the rest of the run is incomplete. A failed setup with no pairs, or an empty private seed/null public seed projection, returns 3. Top-level completed alone cannot accept a partial result.

## Fixed checks

- **Plan and group:** known protocol, correct pair/direction and arm order, exactly four unique case/arm results. Fixed-policy has two seed phases; policy-revision adds two separate revision phases. Both have two compact and four continuation phases.
- **Recorded completion:** each required phase has the expected kind, completed status and terminal, and no requested cancellation. Prelude/compact tool counts are zero, continuations use at most 16. Compact evidence includes a compaction-completed marker and successful terminal; a compaction marker in another phase marks the result incomplete. Required runner integrity and cleanup flags must be true.
- **Detailed outcomes:** both visible-policy oracles must record all ten shared checks and dependency_policy, each exactly once with boolean results. Every shared check passes, the known final policy passes, and the opposite policy fails. Both policies passing is an unsupported contradiction for this fixture.

The gate ignores redundant `classification`, `shared_rules_pass`, per-oracle summary `passed`, and `both_policies_pass` fields. It derives acceptance from the detailed checks. It does not audit every metadata field, reconstruct event ordering or match private request/thread identities. Its scope is explicitly **saved native result acceptance; no oracle rerun or wire verification**. Usage remains outside this behavioral gate, so null/incomplete cost coverage does not reject an otherwise complete result.

The public-candidate recheck serves a different purpose: it reruns the published code and compares it to the recorded verdicts. Such historical consistency can hold even for a failed candidate. The acceptance gate reads arbitrary new saved runs in the two supported shapes and requires successful target behavior. Neither command changes native-run's completion semantics.

## 中文

`native-run` 的 0 表示固定采样完成，合法行为失败也会保留。自动化需要行为门时，显式运行 `native-accept FILE --scenario fixed-policy|policy-revision`。它共用 public/private 的稳定字段，只读记录，不公开真实身份。

验收要求完整固定组、四个唯一候选、阶段完成和必要清理记录，以及双 oracle 的完整逐项结果。共享规则全过、最终政策过、相反政策不过才接受；原汇总 bool 和分类不参与放行。返回码 0=接受，1=有效行为失败，2=格式/结构不支持，3=未完成。真实启动失败的空结果也属于未完成。

此命令不重跑候选/oracle，不核验真实 wire、身份、源码或压缩过程，不改旧采样命令和历史文件。若要重算已经公开的源码行为，继续使用 `scripts/recheck_native_candidates.py`。
