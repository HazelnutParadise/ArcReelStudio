"""假的 ``grok agent stdio``：说 ACP（JSON-RPC 2.0 over stdio），按 ``behaviour.json`` 跑一轮。

``tool``：经 session/new 给的 HTTP MCP 端点真的呼叫一次 ``list_projects``；``permission``：先替一个内建工具与一个 ArcReel 工具
各要一次权限；``prompt_delay``：一轮要跑多久（测排队与中断）；``fail``：prompt 回 JSON-RPC 错误；``no_resume``：不支援
session/resume（逼 client 退回 session/load）。收到的请求、回覆与启动参数记进 ``seen.json``。Grok 引擎的单元与端到端用例共用。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FAKE_GROK_AGENT = f"""#!{sys.executable}
import json, os, sys, threading, time, urllib.request
here = os.path.dirname(os.path.abspath(__file__))
behaviour = json.load(open(os.path.join(here, "behaviour.json")))
lock = threading.Lock()
seen = {{"argv": sys.argv[1:], "home": os.environ.get("HOME"), "xai_key": os.environ.get("XAI_API_KEY"),
         "requests": [], "replies": [], "notifications": [], "tool_results": []}}
state = {{"mcp": None, "cancel": threading.Event(), "next_id": 900}}
pending = {{}}
def dump():
    with open(os.path.join(here, "seen.json"), "w") as f: json.dump(seen, f)
def send(o):
    o["jsonrpc"] = "2.0"
    with lock:
        sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()
def ask(method, params):
    state["next_id"] += 1; mid = state["next_id"]; ev = threading.Event(); pending[mid] = [ev, None]
    send({{"id": mid, "method": method, "params": params}}); ev.wait(10); return pending[mid][1]
def update(sid, upd):
    send({{"method": "session/update", "params": {{"sessionId": sid, "update": upd}}}})
def call_tool(name, args):
    url = state["mcp"]["url"]; headers = {{h["name"]: h["value"] for h in state["mcp"]["headers"]}}
    headers["Content-Type"] = "application/json"
    body = json.dumps({{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {{"name": name, "arguments": args}}}}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=10) as r:
        return json.loads(r.read())
def run_prompt(mid, sid):
    if behaviour.get("permission"):
        r1 = ask("session/request_permission", {{"sessionId": sid, "toolCall": {{"toolCallId": "b1", "title": "read_file /etc/passwd", "kind": "read"}},
                 "options": [{{"optionId": "ok", "name": "Allow", "kind": "allow_once"}}, {{"optionId": "no", "name": "Reject", "kind": "reject_once"}}]}})
        r2 = ask("session/request_permission", {{"sessionId": sid, "toolCall": {{"toolCallId": "m1", "title": "arcreel: list_projects", "kind": "other"}},
                 "options": [{{"optionId": "ok", "name": "Allow", "kind": "allow_once"}}, {{"optionId": "no", "name": "Reject", "kind": "reject_once"}}]}})
        seen["permission_answers"] = [r1, r2]; dump()
    update(sid, {{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": "Let me "}}}})
    update(sid, {{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": "check."}}}})
    if behaviour.get("tool"):
        seen["tool_results"].append(call_tool("list_projects", {{"x": 1}})); dump()
    deadline = time.time() + behaviour.get("prompt_delay", 0)
    while time.time() < deadline and not state["cancel"].is_set():
        time.sleep(0.02)
    if state["cancel"].is_set():
        state["cancel"].clear(); send({{"id": mid, "result": {{"stopReason": "cancelled"}}}}); return
    if behaviour.get("fail"):
        send({{"id": mid, "error": {{"code": -32000, "message": "You have hit your usage limit"}}}}); return
    update(sid, {{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": "done"}}}})
    send({{"id": mid, "result": {{"stopReason": "end_turn"}}}})
for line in sys.stdin:
    m = json.loads(line); method, mid, params = m.get("method"), m.get("id"), m.get("params") or {{}}
    if method is None:
        seen["replies"].append(m); dump()
        if mid in pending:
            pending[mid][1] = m.get("result"); pending[mid][0].set()
        continue
    if mid is None:
        seen["notifications"].append({{"method": method, "params": params}}); dump()
        if method == "session/cancel": state["cancel"].set()
        continue
    seen["requests"].append({{"method": method, "params": params}}); dump()
    if method == "initialize":
        send({{"id": mid, "result": {{"protocolVersion": 1, "agentCapabilities": {{"loadSession": True, "mcpCapabilities": {{"http": True}}}}}}}})
    elif method in ("session/new", "session/resume", "session/load"):
        if method == "session/resume" and behaviour.get("no_resume"):
            send({{"id": mid, "error": {{"code": -32601, "message": "method not found"}}}}); continue
        state["mcp"] = (params.get("mcpServers") or [None])[0]
        sid = params.get("sessionId", "G1")
        if method == "session/load":
            update(sid, {{"sessionUpdate": "agent_message_chunk", "content": {{"type": "text", "text": "OLD HISTORY"}}}})
        send({{"id": mid, "result": {{"sessionId": sid}} if method == "session/new" else {{}}}})
    elif method == "session/prompt":
        threading.Thread(target=run_prompt, args=(mid, params["sessionId"]), daemon=True).start()
    else:
        send({{"id": mid, "result": {{}}}})
"""


def install_fake_grok(folder: Path, **behaviour: Any) -> str:
    """在 ``folder`` 放一个假 grok CLI 并写好行为，返回它的路径。"""
    folder.mkdir(parents=True, exist_ok=True)
    cli = folder / "grok"
    cli.write_text(FAKE_GROK_AGENT, encoding="utf-8")
    cli.chmod(0o755)
    (folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")
    return str(cli)


def read_fake_grok_seen(folder: Path) -> dict[str, Any]:
    return json.loads((folder / "seen.json").read_text(encoding="utf-8"))
