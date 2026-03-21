#!/usr/bin/env bash
# Stop AION (macOS / Linux)
cd "$(dirname "$0")"
PID=$(lsof -ti :7000 2>/dev/null || true)
if [ -n "$PID" ]; then
  kill -9 "$PID" 2>/dev/null
  echo "AION stopped (PID $PID)"
else
  echo "AION not running on port 7000"
fi
pkill -f "aion_cli.py" 2>/dev/null || true
