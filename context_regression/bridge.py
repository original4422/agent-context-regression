"""Small stdio MCP surface: task files and public checks only; no shell tool."""
import json
import os
from pathlib import Path
import sys
import threading

# This file is launched by absolute path with Python's isolated mode.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from context_regression.checks import run_checks
from context_regression.tasks import load_task


class Workspace:
    def __init__(self, task, root, codex="codex"):
        self.task, self.root, self.codex = task, Path(root).resolve(), codex
        self.files = task["spec"]["editable"]

    def file(self, name):
        if name not in self.files:
            raise ValueError("Only listed task files are accessible")
        path = self.root / name
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("Task files must stay inside the workspace")
        return path

    def call(self, name, arguments):
        if name == "list_files":
            return {"files": self.files}
        if name == "read_file":
            return {"content": self.file(arguments["path"]).read_text()}
        if name == "write_file":
            content = arguments["content"]
            if not isinstance(content, str) or len(content.encode()) > 100_000:
                raise ValueError("File content must be text, at most 100 KB")
            self.file(arguments["path"]).write_text(content)
            return {"written": arguments["path"]}
        if name == "check":
            return run_checks(self.task["path"], self.root, "public", self.codex)
        raise ValueError(f"Unknown tool: {name}")


def schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


TOOLS = [
    {"name": "list_files", "description": "List the editable files in this coding task.", "inputSchema": schema({})},
    {"name": "read_file", "description": "Read a task file.", "inputSchema": schema({"path": {"type": "string"}})},
    {"name": "write_file", "description": "Replace a task file with complete source code.", "inputSchema": schema({"path": {"type": "string"}, "content": {"type": "string"}})},
    {"name": "check", "description": "Run the public smoke checks. They do not cover every earlier requirement.", "inputSchema": schema({})},
]


def main(observe=None):
    workspace = Workspace(load_task(sys.argv[1]), sys.argv[2], sys.argv[3])
    # If a timed-out runner exits, do not leave a detached MCP server alive.
    parent = int(sys.argv[4])
    def watch_parent():
        while True:
            threading.Event().wait(1)
            try:
                os.kill(parent, 0)
            except ProcessLookupError:
                os._exit(1)
    threading.Thread(target=watch_parent, daemon=True).start()
    for line in sys.stdin:
        request = json.loads(line)
        if observe:
            observe("request", request)
        if "id" not in request:
            continue
        method = request["method"]
        try:
            if method == "initialize":
                result = {"protocolVersion": request["params"]["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "acr-files", "version": "0.1.0"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request["params"]
                value = workspace.call(params["name"], params.get("arguments", {}))
                result = {"content": [{"type": "text", "text": json.dumps(value)}], "isError": False}
            elif method == "ping":
                result = {}
            else:
                raise ValueError(f"Unsupported MCP method: {method}")
        except (ValueError, KeyError, OSError, RuntimeError) as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
        response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        if observe:
            observe("response", response)
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
