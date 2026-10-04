# Native smoke: first setup failure

2026-09-30, runner [`0f6ccc3`](https://github.com/original4422/agent-context-regression/commit/0f6ccc3ee0096e417022deebff798326ca448b81), Codex CLI 0.155.1, configured `gpt-6-astra` / low. [Frozen result and audit](native-smoke-initial.json).

The first attempted group stopped at `thread/start`, before any model-producing request. The RPC returned `-32600: failed to load configuration: No such file or directory (os error 2)`. No thread identity was returned and no MCP process was observed. Actual model requests: **0 seed, 0 compaction, 0 continuation**. There are no native-compaction or task-correctness outcomes from this attempt; usage remains null/incomplete.

The runner had started app-server with the neutral candidate directory as its cwd, then removed and recreated that directory before the seed. A deterministic no-model Python child reproduced the lifecycle defect: the pathname existed again, but the child's `os.getcwd()` raised `ENOENT` because its cwd inode had been deleted.

The repair preserves the candidate directory inode and resets only its harness-owned contents. A real Python child held at that cwd can subsequently resolve it, the inode is unchanged, and the source bytes equal the checkpoint. The complete fake eight-phase graph still passes. This repair did not itself rerun app-server or call a model.

The failed attempt reaped its app-server, removed the candidate directory, and left user config, runner and task hashes unchanged. Private logs, source/binary/schema fingerprints and the empty branch graph remain preserved. The measurement window was released after cleanup; any repaired real group requires a separate scheduling decision.
