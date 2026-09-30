def should_retry(status, method):
    return method.upper() in {"GET", "HEAD", "PUT"} and status in {500, 502, 503, 504}
