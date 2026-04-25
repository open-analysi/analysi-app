#!/bin/bash
# Stop the macOS thermal exporter

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$SCRIPT_DIR/thermal_exporter.pid"

if [ ! -f "$PIDFILE" ]; then
    echo "Thermal exporter is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PIDFILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping thermal exporter (PID: $PID)..."
    kill "$PID"
    sleep 1

    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        kill -9 "$PID"
    fi

    rm "$PIDFILE"
    echo "✅ Thermal exporter stopped"
else
    echo "Thermal exporter not running (stale PID file)"
    rm "$PIDFILE"
fi