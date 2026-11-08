#!/usr/bin/env python3
"""Minimal client for Epic's Unreal MCP server over streamable HTTP.

  mcp.py call <toolset> <tool> '<json args>'
  mcp.py batch <file.json>   # [[toolset, tool, args], ...]; stops on first failure
  mcp.py pins <graph> <type_id>...
  mcp.py find <graph> <filter>
  mcp.py raw <method> '<json params>'
Short toolset names (UMG, BP, Object, Asset, Scene, App, Logs, Slate) expand to full IDs.
"""
import json, sys, urllib.request

URL = "http://localhost:8000/mcp"
SHORT = {
    "UMG": "UMGToolSet.UMGToolSet",
    "Object": "editor_toolset.toolsets.object.ObjectTools",
    "BP": "editor_toolset.toolsets.blueprint.BlueprintTools",
    "Asset": "editor_toolset.toolsets.asset.AssetTools",
    "Scene": "editor_toolset.toolsets.scene.SceneTools",
    "App": "EditorToolset.EditorAppToolset",
    "Logs": "EditorToolset.LogsToolset",
    "Slate": "SlateInspectorToolset.SlateInspectorToolset",
    "Actor": "editor_toolset.toolsets.actor.ActorTools",
    "DataTable": "editor_toolset.toolsets.data_table.DataTableTools",
    "Prim": "editor_toolset.toolsets.primitive.PrimitiveTools",
    "DataAsset": "editor_toolset.toolsets.data_asset.DataAssetTools",
}
_session = None
_id = 0


def _post(payload):
    global _session
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if _session:
        headers["Mcp-Session-Id"] = _session
    req = urllib.request.Request(URL, json.dumps(payload).encode(), headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        _session = r.headers.get("Mcp-Session-Id") or _session
        body = r.read().decode()
    if not body.strip():
        return None
    if "data:" in body:
        body = [l[5:] for l in body.splitlines() if l.startswith("data:")][-1]
    return json.loads(body)


def rpc(method, params=None):
    global _id
    _id += 1
    return _post({"jsonrpc": "2.0", "id": _id, "method": method, "params": params or {}})


def init():
    rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                       "clientInfo": {"name": "recipe-runner", "version": "1"}})
    _post({"jsonrpc": "2.0", "method": "notifications/initialized"})


def call(toolset, tool, args):
    r = rpc("tools/call", {"name": "call_tool", "arguments": {
        "toolset_name": SHORT.get(toolset, toolset), "tool_name": tool, "arguments": args}})
    if "error" in r:
        return False, r["error"]
    res = r["result"]
    text = "".join(c.get("text", "") for c in res.get("content", []))
    try:
        text = json.loads(text)
    except Exception:
        pass
    return not res.get("isError"), text


def main():
    init()
    cmd = sys.argv[1]
    if cmd == "raw":
        print(json.dumps(rpc(sys.argv[2], json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}), indent=1))
    elif cmd == "call":
        ok, out = call(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]) if len(sys.argv) > 4 else {})
        print(out if isinstance(out, str) else json.dumps(out, indent=1))
        sys.exit(0 if ok else 1)
    elif cmd == "pins":
        for t in sys.argv[3:]:
            ok, o = call("BP", "get_node_type_pins", {"graph": sys.argv[2], "type_id": t})
            if not ok:
                print(t, "FAIL", o); continue
            f = lambda k: [f"{x['name']}:{x['type_id']}" for x in o["returnValue"][k]]
            print(t, "| in:", f("input_pins"), "| out:", f("output_pins"))
    elif cmd == "find":
        ok, o = call("BP", "find_node_types", {"graph": sys.argv[2], "type_id_filter": sys.argv[3], "context_pins": []})
        print(o["returnValue"] if ok else o)
    elif cmd == "batch":
        for i, (ts, tool, args) in enumerate(json.load(open(sys.argv[2]))):
            ok, out = call(ts, tool, args)
            s = out if isinstance(out, str) else json.dumps(out)
            print(f"[{i}] {tool}: {'OK' if ok else 'FAIL'} {s[:400]}")
            if not ok:
                sys.exit(1)


if __name__ == "__main__":
    main()
