#!/usr/bin/env bash
# Start the Ad Server Simulator (macOS / Linux). Keep this terminal open while using the tool.
set -e
cd "$(dirname "$0")/backend"

if [ ! -x ".venv/bin/python" ]; then
  echo "The simulator is not set up yet. See HOW-TO-USE.md (section 12) for the one-time setup."
  exit 1
fi

echo "Starting the Ad Server Simulator..."
echo "Open http://localhost:8090 in your browser. Keep this terminal open; press Ctrl+C to stop."
( sleep 4; (command -v open >/dev/null && open http://localhost:8090) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8090) || true ) &
exec ./.venv/bin/python -m uvicorn app.main:app --port 8090
