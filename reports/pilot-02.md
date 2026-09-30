# Context regression results

Controlled reconstructed contexts; not native Codex compaction. Hand-authored microtasks.

Batch: **completed**; 24/24 attempted.

| Strategy | Passed / attempted | Regression rows | Total tokens¹ | Median end-to-end seconds² |
| --- | ---: | ---: | ---: | ---: |
| full | 8/8 | 0 | 780797 | 26.41 |
| recent | 2/8 | 5 | 768542 | 30.10 |
| structured | 8/8 | 0 | 899098 | 43.87 |

¹ Input + output tokens; summary generation is included. Cached input is a subset of input, not an extra charge. These are CLI-reported tokens, not dollars or subscription quota units.

² Includes summary generation, continuation, and independent verification. All attempted rows remain in the report; aborted batches are not complete comparisons.

## Per-task outcomes

| Task | Repeat | Strategy | Passed | Failed checks |
| --- | ---: | --- | --- | --- |
| case-sensitive-slugs | 1 | full | True |  |
| case-sensitive-slugs | 1 | recent | False | rejected_lowercasing, existing_separator, digits |
| case-sensitive-slugs | 1 | structured | True |  |
| case-sensitive-slugs | 2 | full | True |  |
| case-sensitive-slugs | 2 | structured | True |  |
| case-sensitive-slugs | 2 | recent | False | existing_separator |
| explicit-empty-overrides | 2 | recent | True |  |
| explicit-empty-overrides | 2 | full | True |  |
| explicit-empty-overrides | 2 | structured | True |  |
| explicit-empty-overrides | 1 | full | True |  |
| explicit-empty-overrides | 1 | recent | True |  |
| explicit-empty-overrides | 1 | structured | True |  |
| event-window-order | 1 | recent | False | rejected_closed_boundary |
| event-window-order | 1 | structured | True |  |
| event-window-order | 1 | full | True |  |
| event-window-order | 2 | recent | False | rejected_closed_boundary |
| event-window-order | 2 | full | True |  |
| event-window-order | 2 | structured | True |  |
| retry-method-policy | 1 | full | True |  |
| retry-method-policy | 1 | recent | False | rejected_post_retry, exact_allowed_methods |
| retry-method-policy | 1 | structured | True |  |
| retry-method-policy | 2 | full | True |  |
| retry-method-policy | 2 | structured | True |  |
| retry-method-policy | 2 | recent | False | exact_allowed_methods |
