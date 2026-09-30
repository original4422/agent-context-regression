CHECKS = {
    "punctuation": lambda m: m.slug("release / notes") == "release-notes",
    "whitespace": lambda m: m.slug("  release   notes  ") == "release-notes",
}
