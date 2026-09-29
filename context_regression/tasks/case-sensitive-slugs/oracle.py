CHECKS = {
    "punctuation": lambda m: m.slug("release / notes") == "release-notes",
    "rejected_lowercasing": lambda m: m.slug("API / v2 Guide") == "API-v2-Guide",
    "existing_separator": lambda m: m.slug("API--Guide") == "API-Guide",
    "empty": lambda m: m.slug(" / ") == "",
    "digits": lambda m: m.slug("Q4 2026") == "Q4-2026",
}
