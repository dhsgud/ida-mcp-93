"""Exercise the real stdio MCP server with a disposable binary and database."""

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


def main():
    root = Path(tempfile.mkdtemp(prefix="ida93-mcp-"))
    sample = root / "sample.elf"
    shutil.copyfile(
        Path(__file__).resolve().parent.parent / "ida-nexus-93/tests/crackme03.elf",
        sample,
    )
    env = dict(
        os.environ,
        IDA_NEXUS_STATE_DIR=str(root / "nexus"),
        IDA_MCP_STATE_DIR=str(root / "mcp"),
    )
    responses = queue.Queue()
    log = (root / "server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from ida_mcp.cli import main; raise SystemExit(main())",
            "stdio",
            "--agent=ida93-smoke",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        encoding="utf-8",
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )

    def read_responses():
        for line in process.stdout:
            responses.put(json.loads(line))
        responses.put(None)

    threading.Thread(target=read_responses, daemon=True).start()
    request_id = 0

    def request(method, params):
        nonlocal request_id
        request_id += 1
        process.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            + "\n"
        )
        process.stdin.flush()
        while True:
            response = responses.get(timeout=90)
            assert response is not None, f"MCP exited: {root / 'server.log'}"
            if response.get("id") == request_id:
                assert "error" not in response, response
                return response["result"]

    def tool(name, **arguments):
        result = request("tools/call", {"name": name, "arguments": arguments})
        assert not result.get("isError"), result
        return result.get("structuredContent") or json.loads(
            result["content"][0]["text"]
        )

    try:
        request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ida93-smoke", "version": "1"},
            },
        )
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        process.stdin.flush()
        assert len(request("tools/list", {})["tools"]) >= 6
        tool("open_database", path=str(sample))
        result = tool(
            "execute_python",
            code="""
import idaapi, threading
functions = list(db.functions)
assert functions
func = functions[0]
assert db.functions.set_name(func, 'IDA93_SMOKE_SAVED')
pseudocode = str(db.functions.get_pseudocode(func))
assert pseudocode.strip()
{'version': idaapi.get_kernel_version(), 'functions': len(functions),
 'main_thread': threading.current_thread() is threading.main_thread(),
 'pseudocode_chars': len(pseudocode)}
""",
        )
        assert result["result"]["version"] == "9.3", result
        assert result["result"]["main_thread"], result
        print(json.dumps(result["result"]), flush=True)
        tool("save_database")
        tool("close_database")
        tool("open_database", path=str(sample))
        saved = tool(
            "execute_python", code="db.functions.get_name(next(iter(db.functions)))"
        )
        assert saved["result"] == "IDA93_SMOKE_SAVED", saved
        tool("close_database")
        assert tool("list_databases")["instances"] == []
        print(
            "PASS: stdio MCP, IDA 9.3, analysis, decompile, rename, save/reopen, close"
        )
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        print(f"Test artifacts: {root}")
    assert process.returncode == 0, process.returncode


if __name__ == "__main__":
    main()
