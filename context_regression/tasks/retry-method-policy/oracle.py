CHECKS = {
    "rate_limit": lambda m: m.should_retry(429, "GET") is True,
    "server_error": lambda m: m.should_retry(503, "GET") is True,
    "rejected_post_retry": lambda m: m.should_retry(503, "POST") is False and m.should_retry(429, "POST") is False,
    "exact_allowed_methods": lambda m: m.should_retry(503, "PUT") is True and m.should_retry(503, "DELETE") is False and m.should_retry(503, "HEAD") is True,
    "case_insensitive_method": lambda m: m.should_retry(429, "get") is True,
    "exact_status_set": lambda m: m.should_retry(501, "GET") is False and m.should_retry(200, "GET") is False,
}
