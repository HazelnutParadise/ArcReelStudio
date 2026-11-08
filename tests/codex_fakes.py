"""假的 ``codex app-server``：说与真 app-server 同一套 JSON-RPC，按 ``behaviour.json`` 跑一轮（可带一次工具呼叫），
把收到的请求与回覆记进 ``seen.json``。Codex 引擎的单元与端到端用例共用。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FAKE_CODEX_APP_SERVER = f"""#!{sys.executable}
import json, os, sys, threading, time
here = os.path.dirname(os.path.abspath(__file__))
behaviour = json.load(open(os.path.join(here, "behaviour.json")))
lock = threading.Lock()
seen = {{"argv": sys.argv[1:], "requests": [], "replies": []}}
def dump():
    with open(os.path.join(here, "seen.json"), "w") as f: json.dump(seen, f)
def send(o):
    with lock:
        sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
turns = [0]
def run_turn(turn_id):
    time.sleep(behaviour.get("turn_delay", 0))
    if behaviour.get("tool"):
        send({{"method": "item/started", "params": {{"threadId": "T1", "item": {{"type": "dynamicToolCall", "id": "C1", "tool": "list_projects", "arguments": {{"x": 1}}}}}}}})
        send({{"id": 900, "method": "item/tool/call", "params": {{"threadId": "T1", "turnId": turn_id, "callId": "C1", "tool": "list_projects", "arguments": {{"x": 1}}}}}})
        reply = waiting.get()
        send({{"method": "item/completed", "params": {{"threadId": "T1", "item": {{"type": "dynamicToolCall", "id": "C1", "tool": "list_projects", "contentItems": reply["result"]["contentItems"], "success": reply["result"]["success"]}}}}}})
    if behaviour.get("approval"):
        send({{"id": 901, "method": "item/commandExecution/requestApproval", "params": {{"threadId": "T1"}}}})
        waiting.get()
    send({{"method": "item/completed", "params": {{"threadId": "T1", "item": {{"type": "agentMessage", "id": "M" + turn_id, "text": "done " + turn_id}}}}}})
    send({{"method": "thread/tokenUsage/updated", "params": {{"threadId": "T1", "tokenUsage": {{"total": {{"inputTokens": 100, "cachedInputTokens": 40, "outputTokens": 7, "cacheWriteInputTokens": 0}}}}}}}})
    status = behaviour.get("status", "completed")
    turn = {{"id": turn_id, "status": status}}
    if status == "failed":
        turn["error"] = {{"message": "You've hit your usage limit", "codexErrorInfo": "usageLimitExceeded"}}
    send({{"method": "turn/completed", "params": {{"threadId": "T1", "turn": turn}}}})
import queue
waiting = queue.Queue()
for line in sys.stdin:
    m = json.loads(line); method, mid = m.get("method"), m.get("id")
    if method is None:
        seen["replies"].append(m); dump(); waiting.put(m); continue
    seen["requests"].append({{"method": method, "params": m.get("params")}}); dump()
    if method == "initialize": send({{"id": mid, "result": {{}}}})
    elif method in ("thread/start", "thread/resume"): send({{"id": mid, "result": {{"thread": {{"id": m["params"].get("threadId", "T1")}}, "model": "gpt-5.5"}}}})
    elif method == "turn/start":
        turns[0] += 1; turn_id = "U%d" % turns[0]
        send({{"id": mid, "result": {{"turn": {{"id": turn_id}}}}}})
        threading.Thread(target=run_turn, args=(turn_id,), daemon=True).start()
    elif mid is not None: send({{"id": mid, "result": {{}}}})
"""


def install_fake_codex(folder: Path, **behaviour: Any) -> str:
    """在 ``folder`` 放一个假 codex CLI 并写好行为，返回它的路径。"""
    folder.mkdir(parents=True, exist_ok=True)
    cli = folder / "codex"
    cli.write_text(FAKE_CODEX_APP_SERVER, encoding="utf-8")
    cli.chmod(0o755)
    (folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
    return str(cli)


def read_fake_codex_seen(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "seen.json").read_text(encoding="utf-8"))
