#!/bin/bash

# Lightweight multi-instance manager for USACOArena API servers backed by a shared Hydro deployment.
set -e

SERVICE_INSTANCES=10
SERVER_BASE_PORT=5000
CHECK_INTERVAL=10
HYDRO_BASE_URL="${HYDRO_BASE_URL:-http://127.0.0.1:8888}"
HYDRO_API_TOKEN="${HYDRO_API_TOKEN:-}"
LOG_DIR="logs/services"
PID_DIR="pids"

mkdir -p "$LOG_DIR" "$PID_DIR"

SERVICE_STATUS_FILE="$PID_DIR/service_status.json"

show_usage() {
    echo "Usage: $0 COMMAND [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start                       Start all server instances"
    echo "  stop                        Stop all server instances"
    echo "  restart                     Restart all server instances"
    echo "  status                      Show status of all services"
    echo "  monitor                     Start monitoring daemon"
    echo "  list-ports                  List available service ports"
    echo ""
    echo "Options:"
    echo "  --instances N               Number of service instances (default: 10)"
    echo "  --server-base-port PORT     Base port for competition servers (default: 5000)"
    echo "  --check-interval SECONDS    Health check interval (default: 10)"
    echo "  --hydro-base-url URL        Shared Hydro base URL"
    echo "  --hydro-api-token TOKEN     Shared Hydro addon token"
}

parse_args() {
    COMMAND=""
    while [[ $# -gt 0 ]]; do
        case $1 in
            start|stop|restart|status|monitor|list-ports)
                COMMAND="$1"
                shift
                ;;
            --instances)
                SERVICE_INSTANCES="$2"
                shift 2
                ;;
            --server-base-port)
                SERVER_BASE_PORT="$2"
                shift 2
                ;;
            --check-interval)
                CHECK_INTERVAL="$2"
                shift 2
                ;;
            --hydro-base-url)
                HYDRO_BASE_URL="$2"
                shift 2
                ;;
            --hydro-api-token)
                HYDRO_API_TOKEN="$2"
                shift 2
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    if [[ -z "$COMMAND" ]]; then
        echo "Error: No command specified"
        show_usage
        exit 1
    fi
}

check_service_health() {
    local service_type=$1
    local value=$2

    case $service_type in
        "hydro")
            curl -s --max-time 3 "${value%/}/usacoarena/api/health" >/dev/null 2>&1
            ;;
        "server")
            curl -s --max-time 3 "http://localhost:$value/health" >/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

start_server_instance() {
    local instance_id=$1
    local server_port=$((SERVER_BASE_PORT + instance_id))
    local pid_file="$PID_DIR/server_${instance_id}.pid"
    local log_file="$LOG_DIR/server_${instance_id}.log"

    echo "Starting server instance $instance_id on port $server_port..."

    nohup competition_server \
        --config config/server_config.json \
        --port "$server_port" \
        --hydro-base-url "$HYDRO_BASE_URL" \
        --hydro-api-token "$HYDRO_API_TOKEN" \
        >> "$log_file" 2>&1 &

    echo $! > "$pid_file"
}

stop_server_instance() {
    local instance_id=$1
    local pid_file="$PID_DIR/server_${instance_id}.pid"

    echo "Stopping server instance $instance_id..."
    if [[ -f "$pid_file" ]]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid"
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid"
            fi
        fi
        rm -f "$pid_file"
    fi
}

start_services() {
    echo "Starting $SERVICE_INSTANCES server instances against Hydro: $HYDRO_BASE_URL"

    cat > "$SERVICE_STATUS_FILE" <<EOF
{
    "instances": $SERVICE_INSTANCES,
    "server_base_port": $SERVER_BASE_PORT,
    "hydro_base_url": "$HYDRO_BASE_URL",
    "started_at": "$(date -Iseconds)"
}
EOF

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        start_server_instance "$i"
        sleep 2
    done

    echo ""
    echo "All services started."
    list_service_ports
}

stop_services() {
    echo "Stopping all server instances..."
    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        stop_server_instance "$i"
    done
    rm -f "$SERVICE_STATUS_FILE"
    echo "All services stopped."
}

show_status() {
    echo "Service Status:"
    echo "==============="

    if [[ ! -f "$SERVICE_STATUS_FILE" ]]; then
        echo "No services running."
        return
    fi

    if check_service_health "hydro" "$HYDRO_BASE_URL"; then
        echo "Shared Hydro: ✓ ($HYDRO_BASE_URL)"
    else
        echo "Shared Hydro: ✗ ($HYDRO_BASE_URL)"
    fi

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        local server_port=$((SERVER_BASE_PORT + i))
        printf "Instance %d: " "$i"
        if check_service_health "server" "$server_port"; then
            printf "Server(:%d)=✓" "$server_port"
        else
            printf "Server(:%d)=✗" "$server_port"
        fi
        echo
    done
}

list_service_ports() {
    if [[ ! -f "$SERVICE_STATUS_FILE" ]]; then
        echo "No services running."
        return
    fi

    echo "Available Service Endpoints:"
    echo "============================"
    echo "Shared Hydro: $HYDRO_BASE_URL"
    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        local server_port=$((SERVER_BASE_PORT + i))
        echo "Instance $i: http://localhost:$server_port"
    done
}

start_monitoring() {
    echo "Starting service monitoring (interval: ${CHECK_INTERVAL}s)..."
    echo "Press Ctrl+C to stop monitoring"

    while true; do
        for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
            local server_port=$((SERVER_BASE_PORT + i))
            if ! check_service_health "server" "$server_port"; then
                echo "$(date): server instance $i is down, restarting..."
                stop_server_instance "$i"
                sleep 2
                start_server_instance "$i"
                sleep 3
            fi
        done
        sleep "$CHECK_INTERVAL"
    done
}

main() {
    parse_args "$@"

    case "$COMMAND" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            stop_services
            sleep 2
            start_services
            ;;
        status)
            show_status
            ;;
        monitor)
            start_monitoring
            ;;
        list-ports)
            list_service_ports
            ;;
        *)
            echo "Unknown command: $COMMAND"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
