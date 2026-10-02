# Context regression results

Controlled reconstructed contexts; not native Codex compaction. Hand-authored coding tasks.

Batch: **completed**; 12/12 attempted.

| Strategy | Passed / attempted | Regression rows | Total tokens¹ | Median end-to-end seconds² |
| --- | ---: | ---: | ---: | ---: |
| full | 4/4 | 0 | 397160 | 31.91 |
| recent | 3/4 | 0 | 386616 | 32.48 |
| structured | 4/4 | 0 | 460791 | 51.88 |

¹ Input + output tokens; summary generation is included. Cached input is a subset of input, not an extra charge. These are CLI-reported tokens, not dollars or subscription quota units.

² Includes summary generation, continuation, and independent verification. All attempted rows remain in the report; aborted batches are not complete comparisons.

## Per-task outcomes

| Task | Repeat | Strategy | Passed | Failed checks |
| --- | ---: | --- | --- | --- |
| rollout-dependency-admission | 2 | structured | True |  |
| rollout-dependency-admission | 2 | recent | True |  |
| rollout-dependency-admission | 2 | full | True |  |
| rollout-dependency-admission | 1 | recent | True |  |
| rollout-dependency-admission | 1 | structured | True |  |
| rollout-dependency-admission | 1 | full | True |  |
| scoped-policy-precedence | 1 | structured | True |  |
| scoped-policy-precedence | 1 | full | True |  |
| scoped-policy-precedence | 1 | recent | True |  |
| scoped-policy-precedence | 2 | structured | True |  |
| scoped-policy-precedence | 2 | recent | False | wildcard_scope |
| scoped-policy-precedence | 2 | full | True |  |
