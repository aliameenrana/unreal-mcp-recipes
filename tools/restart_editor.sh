#!/bin/zsh
# Quit the editor, wait until port 8000 is free, relaunch, wait until the MCP server answers.
# A relaunch while the old process (or a CrashReportClient it spawned) still holds the port logs
# "HttpListener unable to bind to 127.0.0.1:8000" and the server never comes up.
set -u
ENGINE="/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app"
PROJECT="${0:A:h}/../UnrealProject/SequencesTestProject.uproject"
PORT=8000

osascript -e 'quit app "UnrealEditor"' 2>/dev/null
for i in {1..60}; do
  pgrep -f "MacOS/UnrealEditor" >/dev/null || break
  sleep 2
done
pkill -9 -f "MacOS/UnrealEditor" 2>/dev/null
for pid in $(lsof -t -nP -iTCP:$PORT -sTCP:LISTEN 2>/dev/null); do kill -9 $pid; done
for i in {1..30}; do
  lsof -nP -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1 || break
  sleep 1
done

open -a "$ENGINE" --args "${PROJECT:A}"
for i in {1..150}; do
  if curl -s -m 3 -X POST -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
      -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"restart","version":"1"}}}' \
      localhost:$PORT/mcp | grep -q result; then
    echo READY; exit 0
  fi
  sleep 4
done
echo "MCP server did not answer within 10 minutes" >&2; exit 1
