#!/bin/bash
# Start the macOS thermal exporter as a background service

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIDFILE="$SCRIPT_DIR/thermal_exporter.pid"
LOGFILE="$SCRIPT_DIR/thermal_exporter.log"

# Check if already running
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Thermal exporter is already running (PID: $OLD_PID)"
        echo "To restart, run: make stop-thermal-exporter && make start-thermal-exporter"
        exit 0
    else
        echo "Removing stale PID file"
        rm "$PIDFILE"
    fi
fi

# Start the exporter
echo "Starting macOS thermal exporter..."
nohup python3 "$SCRIPT_DIR/macos_thermal_simple.py" > "$LOGFILE" 2>&1 &
PID=$!

# Save PID
echo $PID > "$PIDFILE"

# Wait a moment to check if it started successfully
sleep 2

if ps -p $PID > /dev/null; then
    echo "✅ Thermal exporter started successfully (PID: $PID)"
    echo "   Metrics available at: http://localhost:9101/metrics"
    echo "   Log file: $LOGFILE"
else
    echo "❌ Failed to start thermal exporter"
    rm "$PIDFILE"
    exit 1
fi