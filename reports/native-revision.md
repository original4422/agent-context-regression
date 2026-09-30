# Native user-policy revision: two short histories

2026-09-30. Measured runner [`5c06db1`](https://github.com/original4422/agent-context-regression/commit/5c06db134d78c2149bbf43025c7311dd216c47dd), Codex CLI 0.155.1, `gpt-6-astra` / low. [Public result and audit](native-revision.json).

One fixed batch completed **2 initial turns + 2 revision turns + 2 native compactions + 4 continuations** without retries. Both control/native branches followed the latest user decision in A→B and B→A; all four candidates passed the ten shared rules and only the final policy oracle. No candidate implemented the superseded policy.

| Direction / arm | Final policy | Compact seconds | Continuation seconds | Tools / approvals | Latest policy | Superseded policy |
| --- | --- | ---: | ---: | ---: | --- | --- |
| A-to-B / control | B | — | 36.023 | 3 / 3 | pass | fail |
| A-to-B / native-compact | B | 26.98 | 28.98 | 3 / 3 | pass | fail |
| B-to-A / native-compact | A | 24.323 | 33.556 | 3 / 3 | pass | fail |
| B-to-A / control | A | — | 29.639 | 3 / 3 | pass | fail |

Initial/revision turns took 7.701/7.179 seconds for A→B and 11.777/8.659 seconds for B→A. Both compactions and all four prelude turns used zero tools. Durations describe this one batch; usage and costs remain **null/incomplete**.

## Revision boundary and native evidence

Each seed thread first received the old policy and produced a real completed reply. Only then did the same thread receive a separate user correction explicitly superseding that policy. Both forks were created from the correction’s completed turn, with the full two-turn history matching on fork response and readback. Both forks existed before either continuation ran. There was no fabricated assistant/tool history and no source edit during either prelude.

The final coding request was identical in all four arms and referred to the latest agreed decision without repeating the policy. All arms reset the same neutral candidate path to identical checkpoint bytes. Each native continuation stayed on its own compacted fork.

| Direction | Compact RPC ack | New turn started | Matching contextCompaction completed | Matching successful turn terminal |
| --- | ---: | ---: | ---: | ---: |
| A→B | 228 | 230 | 233 | 235 |
| B→A | 457 | 459 | 462 | 464 |

Event sequence numbers refer to the dedicated app-server trace. The public result preserves request/dispatch boundaries, anonymous turns and item fingerprints. Neither seed, correction nor continuation auto-compacted. Six dedicated threads had six distinct observed bridge identities, one MCP initialize/catalog request each, and the same four-tool schema. Twelve continuation calls received exact single-use approvals for their current thread/turn and pending tool arguments; none persisted.

## Independent behavioral result

Both unchanged visible-policy oracles ran outside the editable candidate in separate read-only sandbox worker processes. Their ten shared checks are identical. For the same `base → app` input, the A oracle expects `[base]`, while B expects `[base, app]`. Every A→B candidate passed B and failed only A’s dependency-policy check; every B→A candidate did the reverse. The opposite-policy result therefore distinguishes the superseded decision from an unrelated implementation failure.

The existing published A/B references also calibrate this discriminator: an old-policy reference passes all shared checks and only the superseded oracle. The implementation’s offline negative test confirms such a result stays `superseded_policy` and the predeclared group continues; protocol failures stop the group. Actual candidates all classified as `latest_policy`, so this run supplies no failure example.

This establishes correct behavior for two short explicit user revisions. Both uncompressed controls also passed. The runtime may retain the latest user message directly; correct code does not reveal how an opaque compaction summary represents the revision. There is no claim about long histories, repeated policy churn, general losslessness, latency advantage or token savings. Raw usage snapshots are retained without summing cumulative values or subtracting across forks.

## Integrity and public recheck

All requested effective configuration overrides matched, with 2 unrelated MCP servers and 12 plugins disabled. User config, runner, tasks and revision fixture hashes remained unchanged during measurement. Config/read responses never entered the private protocol logs; private traces are 0600 in a 0700 directory. App-server and all observed bridges exited, the temporary candidate was removed, and the model window was released after cleanup. Original logs, thread identities and six rollout snapshots remain private.

Only the four reviewed fictional `plan.py` candidate files were copied out, with byte and directory hashes verified against the measured results. Each contains two pure task functions and no imports, credentials, paths, account identifiers or runtime transcripts. [Published candidates and bilingual instructions](native-revision-candidates/README.md).

```sh
python3 -B scripts/recheck_native_candidates.py --scenario policy-revision
```

The existing offline recheck gained a second fixed scenario; it checks source/task/candidate fingerprints, then actually recalculates all eight complete oracle verdicts using ordinary Python subprocesses. It needs Python 3.11+ and no Codex, credentials, network or extra packages. This rechecks function behavior, not the original sandbox, native lifecycle or timings. The old fixed-policy report, candidates and default recheck remain unchanged.

The raw measured `public.json` retains the embedded static plan’s `execution: "plan-only"`; top-level `status: "completed"` and audited request/event counts describe the real execution. The public report adds a separate audit and candidate-release metadata without rewriting private measurement files.

中文：一次固定组完成两个真实跨 turn 修订方向，四份候选均执行最新政策、未恢复旧政策，共享规则全过。两个原生压缩分支都有匹配完成项与成功终态；对照也通过。四份虚构源码按原字节公开，可用上述纯 Python 命令离线重算；日志与真实身份仍私有，usage 保持 null/incomplete。结论仅限这两个短修订历史。
