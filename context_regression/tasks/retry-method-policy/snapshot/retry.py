def should_retry(status, method):
    return status in {500, 502, 503, 504}
