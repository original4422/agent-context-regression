def select_events(events, start, end):
    return [event for event in events if start <= event["timestamp"] <= end]
