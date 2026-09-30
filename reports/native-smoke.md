# Native compaction smoke: two short policy histories

2026-09-30. Frozen runner [`ec67f5d`](https://github.com/original4422/agent-context-regression/commit/ec67f5da4592b3225441d1638a9d92e9dbf5e6f5), Codex CLI 0.155.1, `gpt-6-astra` / low. [Full public result and audit](native-smoke.json).

One repaired batch completed exactly **2 real seed turns, 2 native compactions and 4 continuations**, with no retries. Both short A/B histories produced the requested policy after native compaction. Control also passed both policies. Every candidate passed the shared rules and failed only the opposite oracle's policy discriminator.

| Pair / arm | Native compact seconds | Continuation seconds | Tool calls / one-call approvals | Shared rules | Target policy | Opposite policy |
| --- | ---: | ---: | ---: | --- | --- | --- |
| A control | — | 34.157 | 3 / 3 | pass | pass | fail |
| A native-compact | 21.634 | 32.315 | 3 / 3 | pass | pass | fail |
| B native-compact | 18.683 | 37.130 | 3 / 3 | pass | pass | fail |
| B control | — | 25.110 | 4 / 4 | pass | pass | fail |

Seed A took 7.533 seconds; seed B took 7.976 seconds. Seeds and compactions used zero tools. Phase durations describe this run and include protocol waiting; they are not repeated latency estimates.

## Native lifecycle evidence

Each policy was supplied through a real seed user turn with an instruction to confirm and wait. Both seed turns completed without editing source. No assistant/tool history was injected. From each completed turn, the runner created two distinct persistent legacy forks before executing either arm. Fork response and `thread/read` histories matched the seed boundary after normalizing only turn/item identity and turn timestamps. All six threads returned the same selected model/effort, read-only sandbox and on-request/user approval settings.

The compact arms continued on their original fork IDs with a new turn ID. The observed request/event sequences were:

| Pair | RPC ack | New turn started | Matching contextCompaction item completed | Matching turn completed |
| --- | ---: | ---: | ---: | ---: |
| A | 175 | 177 | 180 | 182 |
| B | 345 | 347 | 350 | 352 |

These sequence numbers refer to the dedicated app-server trace; the public result includes request IDs, dispatch boundaries and compaction item fingerprints. Both terminals were `completed`. No seed or continuation emitted an automatic compaction. The deprecated notification and empty RPC ack were not used alone as success evidence.

Each thread had one observed ACR bridge identity, one MCP initialize and one tools/list: six total connections, each exposing exactly the same four fixture tools. The 13 continuation calls received exact, single-use approvals tied to current thread/turn, one pending call, actual tool name and arguments. No approval persisted and no server-wide approval was configured.

All arms began from identical bytes at the same neutral candidate path. Independent trusted verifiers outside that editable directory evaluated each candidate under a separate read-only sandbox process against both policies. Private candidate snapshots and six owned rollout snapshots retain their hashes and identities for audit.

## Usage and integrity

Costs and arm usage are **null/incomplete**. Raw per-stage token snapshots are retained, not summed or subtracted across forks. Both compact snapshots left inherited `total` unchanged while reporting nonzero `last.totalTokens` (6,381 / 6,303) with zero input/output components. This is insufficient to establish compression cost or savings. The result proves correct policy recovery for these two short histories; it does not establish long-context performance or summary fidelity.

The actual effective configuration disabled apps/plugins/hooks, shell, web and multi-agent plus 2 unrelated MCP servers and 12 plugins. Config/read responses were absent from both private traces. Protocol/MCP traces were 0600 inside a 0700 directory. App-server and all six observed bridges were reaped or confirmed exited, the temporary candidate was removed, and config/runner/task hashes were unchanged. Only the six dedicated experiment thread identities and rollout snapshots were retained privately.

The embedded `plan.execution: "plan-only"` describes the static plan generator. Top-level `status: "completed"`, phase events and the audit's 2/2/4 request counts describe this real execution. The raw measurement files retain their original fields.

## Separate setup records

The [first attempt](native-smoke-initial.md), frozen at `0f6ccc3`, stopped at thread/start before any seed, compact or continuation request: removing and recreating the live app-server cwd invalidated its directory inode. That failure is retained unchanged. The repair at `ec67f5d` resets only owned directory contents. A deterministic Python child regression and the [separate real no-model probe](native-reset-probe.json) confirmed stable cwd and persistent legacy thread/start/catalog before this batch was scheduled. The probe issued zero turn/fork/compact requests. Neither setup record is counted as an additional successful model sample.
