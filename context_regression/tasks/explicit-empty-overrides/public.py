CHECKS = {
    "inherit_none": lambda m: m.merge_settings({"theme": "dark"}, {"theme": None}) == {"theme": "dark"},
    "normal_override": lambda m: m.merge_settings({"theme": "dark"}, {"theme": "light"}) == {"theme": "light"},
}
