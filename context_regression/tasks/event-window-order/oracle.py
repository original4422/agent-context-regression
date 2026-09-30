CHECKS = {
    "deduplicate": lambda m: m.select_events([{"id":"a","timestamp":2},{"id":"a","timestamp":3}],0,10) == [{"id":"a","timestamp":2}],
    "rejected_closed_boundary": lambda m: m.select_events([{"id":"a","timestamp":0},{"id":"b","timestamp":10}],0,10) == [{"id":"a","timestamp":0}],
    "ingestion_order": lambda m: m.select_events([{"id":"a","timestamp":8},{"id":"b","timestamp":2}],0,10) == [{"id":"a","timestamp":8},{"id":"b","timestamp":2}],
    "filter_before_dedup": lambda m: m.select_events([{"id":"a","timestamp":-1},{"id":"a","timestamp":2}],0,10) == [{"id":"a","timestamp":2}],
    "inputs_unchanged": lambda m: unchanged(m),
}

def unchanged(m):
    events = [{"id":"a","timestamp":2},{"id":"a","timestamp":3}]
    m.select_events(events,0,10)
    return events == [{"id":"a","timestamp":2},{"id":"a","timestamp":3}]
