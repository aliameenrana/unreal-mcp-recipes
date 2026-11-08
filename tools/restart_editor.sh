#!/bin/zsh
# Quit the editor, free port 8000, relaunch, wait until the MCP server answers.
# If the new editor logs "HttpListener unable to bind" (the port was still held by the old editor,
# a ShaderCompileWorker it spawned, or CrashReportClient), kill it and try again.
set -u
ENGINE="/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app"
PROJECT="${0:A:h}/../UnrealProject/SequencesTestProject.uproject"
LOG="$HOME/Library/Logs/Unreal Engine/SequencesTestProjectEditor/SequencesTestProject.log"
PORT=8000

ready() {
  curl -s -m 3 -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"restart","version":"1"}}}' \
    localhost:$PORT/mcp | grep -q result
}

stop_all() {
  osascript -e 'quit app "UnrealEditor"' 2>/dev/null
  for i in {1..30}; do pgrep -f "MacOS/UnrealEditor" >/dev/null || break; sleep 2; done
  pkill -9 -f "MacOS/UnrealEditor" 2>/dev/null
  pkill -9 -f "ShaderCompileWorker" 2>/dev/null
  pkill -9 -f "CrashReportClient" 2>/dev/null
  for i in {1..60}; do
    [[ -z "$(lsof -t -nP -iTCP:$PORT 2>/dev/null)" ]] && break
    for pid in $(lsof -t -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null); do kill -9 $pid; done
    sleep 1
  done
  sleep 3
}

for attempt in 1 2 3; do
  stop_all
  open -a "$ENGINE" --args "${PROJECT:A}"
  for i in {1..150}; do
    if ready; then echo READY; exit 0; fi
    if [[ $i -gt 5 ]] && grep -q "unable to bind to 127.0.0.1:$PORT" "$LOG" 2>/dev/null; then
      echo "port $PORT busy at launch (attempt $attempt); retrying" >&2
      break
    fi
    sleep 4
  done
done
echo "MCP server did not come up after 3 attempts" >&2; exit 1
