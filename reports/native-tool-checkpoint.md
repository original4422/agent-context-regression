# Native continuation from a real intermediate edit

2026-09-30. Measured source [`782a107`](https://github.com/original4422/agent-context-regression/commit/782a107823525e0026e5e8f49f68b411de47afed), Codex CLI 0.155.1, `gpt-6-astra` / low. [Unmodified public measurement](native-tool-checkpoint.json), [protocol](../docs/native-tool-checkpoint.md).

One fixed batch completed **one work turn, one native compaction and two continuations**, without retries. The agent first implemented the retry method gate and observed a failing rate-limit check. Both control and native then added 429 without losing that method gate. Each final candidate passed all six external oracle checks; the two final files are byte-identical.

| Phase | Seconds | Tools / single-call approvals | Result |
| --- | ---: | ---: | --- |
| Work | 23.947 | 3 / 3 | Required intermediate four pass / two fail |
| Control continuation | 16.155 | 3 / 3 | Six checks pass |
| Native compaction | 25.335 | 0 / 0 | Matching completed item and successful terminal |
| Native continuation | 23.512 | 3 / 3 | Six checks pass |

These are recorded phase durations from one group, not a performance comparison. Usage and cost remain **null/incomplete**; original usage snapshots are retained without adding cumulative counters or subtracting across forks.

## Actual work and shared starting state

The work turn actually called `read_file`, `write_file`, and `check` in that order. Its final source restricted methods to case-insensitive GET, HEAD and PUT, while retaining the original server-status set. The public tool result was `rate_limit=false`, `not_found=true`. The unchanged external oracle independently returned:

| Check | Work checkpoint | Control | Native |
| --- | --- | --- | --- |
| server_error | pass | pass | pass |
| rejected_post_retry | pass | pass | pass |
| exact_allowed_methods | pass | pass | pass |
| exact_status_set | pass | pass | pass |
| rate_limit | fail | pass | pass |
| case_insensitive_method | fail | pass | pass |

The two intermediate failures both exercise 429, which the first turn was instructed to leave unfinished. The work gate was satisfied on its single attempt; no reference source was substituted.

Both forks were created from the same completed work turn, after its real tools finished and before either continuation. The full read/write/check arguments and results matched the completed items returned by `thread/read`; both fork/readback fingerprints matched that boundary. No assistant or tool history was fabricated.

The runner saved the actual partial source and restored it before each arm at the same candidate path/inode. Independent wire review also confirmed that **both continuations' real first `read_file` responses contained the original partial bytes**, including the missing 429. This directly checks that control's completed edit did not become native's input. The common final request mentioned only the remaining work and observed checks, without repeating the method allowlist or status set.

The native compact had RPC acknowledgement at sequence 273, its new turn at 275, the matching completed contextCompaction item at 278, and a successful terminal at 280. The continuation stayed on that fork. Work and both continuations showed no automatic compaction.

## Integrity, review and reproducibility

Three dedicated experiment threads had distinct observed bridge identities. All nine tool requests received exact single-use approval for the current thread/turn, the single pending ACR call and its actual arguments; no approval persisted. App-server and bridges exited, the temporary candidate was removed, and all seven cleanup/config/source/task/fixture checks passed. All 20 recorded source hashes matched the measured commit. Original traces, real identities and three rollout snapshots remain private; config/read responses are excluded from protocol logs.

An independent reviewer checked the real wire, fork boundary, tool results, byte restoration, compact terminal, approvals, source/config hashes and public projection. The review reused the idle `patch_witness_environment_review` agent from another project; it was a read-only Context review, separate from the author's implementation and run.

The [three released source artifacts](native-tool-checkpoint-candidates/README.md) are the actual partial checkpoint and both final candidates, copied without edits after individual privacy review. Each is a two-line fictional pure function, containing no imports, credentials, paths or account data.

```sh
python3 -I -B scripts/recheck_native_candidates.py --scenario tool-checkpoint
```

Python 3.11+ recomputes three complete oracle verdicts in separate ordinary Python worker processes. All candidate/task/verifier hashes are checked before execution, and every result is compared to this original report. This includes the expected intermediate failures; successful recheck means historical agreement. `native-accept` continues to support only fixed-policy and policy-revision.

This establishes one successful native continuation of real partial coding work. The code itself retained completed behavior, and the public check could be rerun; it does not isolate conversation memory as the only information source. The uncompressed control also passed. No general compression, speed or token-saving claim follows from this sample.

The public JSON is an exact copy of the run's `public.json` (SHA-256 `fd20e1f4b89702f60e6110f97b72d54270b563669a7c2f4a9f48c2c1fc1e12ec`). Its embedded plan retains `execution: "plan-only"`; top-level `status: "completed"` and the audited events record actual execution. Private measurement files and all older reports are unchanged.

中文：唯一固定组完成真实读写检查后，从同一 work 终态与同一原字节中间产物建立两臂。两臂真实读取均为未加入 429 的 partial 源码，最终六项检查全过且文件相同；没有把 control 修改带给 native。三份虚构源码原字节公开，可离线重算中间及最终判定。审查由复用的跨项目空闲 reviewer 独立完成；日志、身份和 rollout 保持私有。结果仅说明这一次真实工具工作流，usage 仍为 null/incomplete。
