CHECKS = {
    "inherit_none": lambda m: m.merge_settings({"theme": "dark"}, {"theme": None}) == {"theme": "dark"},
    "rejected_truthiness": lambda m: m.merge_settings({"label": "old", "tries": 3, "enabled": True}, {"label": "", "tries": 0, "enabled": False}) == {"label": "", "tries": 0, "enabled": False},
    "new_none_omitted": lambda m: m.merge_settings({}, {"optional": None}) == {},
    "new_key": lambda m: m.merge_settings({}, {"region": "west"}) == {"region": "west"},
    "inputs_unchanged": lambda m: unchanged(m),
}

def unchanged(m):
    defaults, overrides = {"theme": "dark"}, {"theme": None}
    m.merge_settings(defaults, overrides)
    return defaults == {"theme": "dark"} and overrides == {"theme": None}
