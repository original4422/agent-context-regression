CHECKS = {
    "rate_limit": lambda m: m.should_retry(429, "GET") is True,
    "not_found": lambda m: m.should_retry(404, "GET") is False,
}
