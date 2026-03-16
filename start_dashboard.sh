#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_dashboard.sh — starts the Streamlit dashboard in the background
#
# The dashboard is lightweight (~200MB idle) and should run continuously
# so you can check data at any time without starting/stopping it.
#
# Usage:
#   ./start_dashboard.sh          # start in background
#   ./start_dashboard.sh stop     # stop
#   ./start_dashboard.sh status   # check if running
#   ./start_dashboard.sh logs     # tail live logs
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin"
PID_FILE="$SCRIPT_DIR/.dashboard.pid"
LOG_FILE="$SCRIPT_DIR/logs/dashboard.log"
PORT=8501

mkdir -p "$SCRIPT_DIR/logs"

cmd="${1:-start}"

case "$cmd" in
  stop)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        kill "$PID"
        rm -f "$PID_FILE"
        echo "Dashboard stopped (PID $PID)."
      else
        echo "Dashboard not running (stale PID file). Cleaning up."
        rm -f "$PID_FILE"
      fi
    else
      echo "Dashboard is not running."
    fi
    ;;

  status)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        echo "Dashboard is RUNNING (PID $PID) → http://localhost:$PORT"
      else
        echo "Dashboard is STOPPED (stale PID file)."
        rm -f "$PID_FILE"
      fi
    else
      echo "Dashboard is STOPPED."
    fi
    ;;

  logs)
    tail -f "$LOG_FILE"
    ;;

  start)
    if [ -f "$PID_FILE" ]; then
      PID=$(cat "$PID_FILE")
      if kill -0 "$PID" 2>/dev/null; then
        echo "Dashboard is already running (PID $PID) → http://localhost:$PORT"
        exit 0
      fi
    fi

    cd "$SCRIPT_DIR"
    nohup "$VENV/streamlit" run dashboard.py \
      --server.port "$PORT" \
      --server.headless true \
      --server.runOnSave false \
      --browser.gatherUsageStats false \
      >> "$LOG_FILE" 2>&1 &

    DASH_PID=$!
    echo "$DASH_PID" > "$PID_FILE"
    echo "Dashboard started (PID $DASH_PID) → http://localhost:$PORT"
    echo "Logs: $LOG_FILE"
    echo "To stop: ./start_dashboard.sh stop"
    ;;

  *)
    echo "Usage: $0 [start|stop|status|logs]"
    exit 1
    ;;
esac
