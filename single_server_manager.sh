#!/bin/bash

# Lightweight server manager inspired by service_manager.sh
set -euo pipefail

SERVER_CMD="uv run python -m usacoarena.main --host 0.0.0.0 --port 5000 --debug"
CHECK_INTERVAL=1
LOG_DIR="logs"
PID_DIR="pids"
LOG_FILE="${LOG_DIR}/single_server.log"
PID_FILE="${PID_DIR}/single_server.pid"
HEALTH_URL="http://localhost:5000/health"

ensure_dirs() {
    mkdir -p "$LOG_DIR" "$PID_DIR"
}

show_usage() {
    cat <<EOF
Usage: $0 {start|stop|restart|status|monitor|logs}

Commands:
  start     Start the server if it is not running
  stop      Stop the server if it is running
  restart   Stop (if needed) and then start the server
  status    Show whether the server is running and healthy
  monitor   Keep the server running, restarting on failure
  logs      Tail the server log file
EOF
}

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

health_check() {
    curl -s --max-time 3 "$HEALTH_URL" >/dev/null 2>&1
}

start_server() {
    ensure_dirs
    if is_running; then
        echo "Server already running (pid $(cat "$PID_FILE"))."
        return
    fi

    echo "Starting server..."
    nohup bash -lc "$SERVER_CMD" >>"$LOG_FILE" 2>&1 &
    local pid=$!
    echo "$pid" >"$PID_FILE"
    echo "Server started with pid $pid (logging to $LOG_FILE)."
}

stop_server() {
    if ! is_running; then
        echo "Server is not running."
        return
    fi

    local pid
    pid=$(cat "$PID_FILE")
    echo "Stopping server (pid $pid)..."
    kill "$pid" >/dev/null 2>&1 || true
    rm -f "$PID_FILE"
    echo "Server stopped."
}

status_server() {
    if ! is_running; then
        echo "Server status: stopped."
        return
    fi

    if health_check; then
        echo "Server status: running and healthy (pid $(cat "$PID_FILE"))."
    else
        echo "Server status: running but health check failed (pid $(cat "$PID_FILE"))."
    fi
}

monitor_server() {
    ensure_dirs
    echo "Monitoring server (health every ${CHECK_INTERVAL}s). Press Ctrl+C to exit."
    while true; do
        if ! is_running; then
            echo "$(date '+%F %T') server not running, starting..."
            start_server
        elif ! health_check; then
            echo "$(date '+%F %T') health check failed, restarting..."
            stop_server
            sleep 1
            start_server
        fi
        sleep "$CHECK_INTERVAL"
    done
}

tail_logs() {
    ensure_dirs
    touch "$LOG_FILE"
    tail -f "$LOG_FILE"
}

case "${1-}" in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    restart)
        stop_server
        start_server
        ;;
    status)
        status_server
        ;;
    monitor)
        monitor_server
        ;;
    logs)
        tail_logs
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
