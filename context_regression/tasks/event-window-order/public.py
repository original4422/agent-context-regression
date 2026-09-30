CHECKS = {
    "deduplicate": lambda m: m.select_events([{"id":"a","timestamp":2},{"id":"a","timestamp":3}],0,10) == [{"id":"a","timestamp":2}],
    "outside": lambda m: m.select_events([{"id":"a","timestamp":12}],0,10) == [],
}
