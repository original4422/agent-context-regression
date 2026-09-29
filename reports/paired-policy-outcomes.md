# Context regression results

Controlled reconstructed contexts; not native Codex compaction. Hand-authored coding tasks.

Batch: **completed**; 12/12 attempted.

| Strategy | Passed / attempted | Regression rows | Total tokens¹ | Median end-to-end seconds² |
| --- | ---: | ---: | ---: | ---: |
| full | 4/4 | 0 | 396924 | 30.38 |
| recent | 0/4 | 2 | 524573 | 42.67 |
| structured | 4/4 | 0 | 456567 | 46.53 |

¹ Input + output tokens; summary generation is included. Cached input is a subset of input, not an extra charge. These are CLI-reported tokens, not dollars or subscription quota units.

² Includes summary generation, continuation, and independent verification. All attempted rows remain in the report; aborted batches are not complete comparisons.

## Per-task outcomes

| Task | Repeat | Strategy | Passed | Failed checks |
| --- | ---: | --- | --- | --- |
| wave-policy-a | 2 | structured | True |  |
| wave-policy-a | 2 | recent | False | dependency_policy, no_revisit |
| wave-policy-a | 2 | full | True |  |
| wave-policy-a | 1 | recent | False | dependency_policy, no_revisit, manual_gate, stable_priority_budget |
| wave-policy-a | 1 | structured | True |  |
| wave-policy-a | 1 | full | True |  |
| wave-policy-b | 1 | structured | True |  |
| wave-policy-b | 1 | full | True |  |
| wave-policy-b | 1 | recent | False | no_revisit |
| wave-policy-b | 2 | structured | True |  |
| wave-policy-b | 2 | recent | False | no_revisit, manual_gate, stable_priority_budget |
| wave-policy-b | 2 | full | True |  |
