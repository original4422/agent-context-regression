import hashlib
import json
from pathlib import Path

BUILTIN_TASKS = Path(__file__).with_name("tasks")


def load_task(path):
    path = Path(path).resolve()
    spec = json.loads((path / "task.json").read_text())
    history = json.loads((path / "history.json").read_text())
    for name in spec["editable"]:
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError(f"Invalid editable path: {name}")
        if not (path / "snapshot" / name).is_file():
            raise ValueError(f"Missing snapshot file: {name}")
    if spec["module"] not in spec["editable"]:
        raise ValueError("module must be in editable")
    for check in ("public.py", "oracle.py"):
        if not (path / check).is_file():
            raise ValueError(f"Missing {check}")
    if not history or any(m["role"] not in {"user", "assistant", "tool"} for m in history):
        raise ValueError("History must contain user/assistant/tool messages")
    return {"path": path, "spec": spec, "history": history, "digest": task_digest(path)}


def task_digest(path):
    digest = hashlib.sha256()
    for file in sorted(Path(path).rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts:
            digest.update(str(file.relative_to(path)).encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()


def tasks_in(root):
    return [load_task(p.parent) for p in sorted(Path(root).glob("*/task.json"))]


def render_history(history):
    return "\n\n".join(f"[{item['role']}]\n{item['content']}" for item in history)


def recent_turns(history, count):
    """A turn starts at a user message; keep its assistant/tool observations too."""
    starts = [i for i, message in enumerate(history) if message["role"] == "user"]
    if count < 1:
        raise ValueError("recent turns must be positive")
    return history[starts[-count] :] if len(starts) >= count else history
