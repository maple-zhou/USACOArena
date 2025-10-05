#!/bin/bash

# 服务管理脚本 - 管理OJ和Server实例的启动、监控和重启
set -e

# 配置参数
SERVICE_INSTANCES=10  # 默认启动2个服务实例
OJ_BASE_PORT=9000
SERVER_BASE_PORT=5000
CHECK_INTERVAL=10    # 健康检查间隔（秒）
LOG_DIR="logs/services"
PID_DIR="pids"

# 创建必要目录
mkdir -p "$LOG_DIR" "$PID_DIR"

# 服务状态文件
SERVICE_STATUS_FILE="$PID_DIR/service_status.json"

show_usage() {
    echo "Usage: $0 COMMAND [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  start                       Start all service instances"
    echo "  stop                        Stop all service instances"
    echo "  restart                     Restart all service instances"
    echo "  status                      Show status of all services"
    echo "  monitor                     Start monitoring daemon"
    echo "  list-ports                  List available service ports"
    echo ""
    echo "Options:"
    echo "  --instances N               Number of service instances (default: 2)"
    echo "  --oj-base-port PORT         Base port for OJ services (default: 9000)"
    echo "  --server-base-port PORT     Base port for competition servers (default: 5000)"
    echo "  --check-interval SECONDS    Health check interval (default: 10)"
    echo ""
    echo "Examples:"
    echo "  $0 start --instances 3                    # Start 3 service instances"
    echo "  $0 monitor --check-interval 5             # Monitor with 5s interval"
    echo "  $0 list-ports                             # List available ports"
}

# 解析命令行参数
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
            --oj-base-port)
                OJ_BASE_PORT="$2"
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

# 检查端口是否可用
is_port_available() {
    local port=$1
    ! ss -tuln | grep -q ":$port "
}

# 检查服务是否健康
check_service_health() {
    local service_type=$1
    local port=$2

    case $service_type in
        "oj")
            curl -s --max-time 3 http://localhost:$port >/dev/null 2>&1
            ;;
        "server")
            curl -s --max-time 3 http://localhost:$port/health >/dev/null 2>&1
            ;;
        *)
            return 1
            ;;
    esac
}

# 启动单个OJ实例
start_oj_instance() {
    local instance_id=$1
    local oj_port=$((OJ_BASE_PORT + instance_id))
    local pid_file="$PID_DIR/oj_${instance_id}.pid"
    local log_file="$LOG_DIR/oj_${instance_id}.log"

    echo "Starting OJ instance $instance_id on port $oj_port..."

    # 启动docker容器
    docker run --platform linux/amd64 -d \
        -v /home/ubuntu/scratch/lfzhou/CompeteMAS/dataset/datasets/usaco_2025/tests:/data/tests \
        --name "oj-rust-$instance_id" \
        -p "${oj_port}:8080" \
        oj-rust-v4 > "$pid_file" 2>/dev/null

    if [[ $? -eq 0 ]]; then
        echo "OJ instance $instance_id started successfully (port: $oj_port)"
        echo "$(date): OJ instance $instance_id started on port $oj_port" >> "$log_file"
    else
        echo "Failed to start OJ instance $instance_id"
        return 1
    fi
}

# 启动单个Server实例
start_server_instance() {
    local instance_id=$1
    local server_port=$((SERVER_BASE_PORT + instance_id))
    local oj_port=$((OJ_BASE_PORT + instance_id))
    local pid_file="$PID_DIR/server_${instance_id}.pid"
    local log_file="$LOG_DIR/server_${instance_id}.log"

    echo "Starting Server instance $instance_id on port $server_port..."

    # 启动竞赛服务器
    nohup competition_server \
        --config config/server_config.json \
        --port "$server_port" \
        --oj-endpoint "http://localhost:${oj_port}/2015-03-31/functions/function/invocations" \
        >> "$log_file" 2>&1 &

    echo $! > "$pid_file"

    if [[ $? -eq 0 ]]; then
        echo "Server instance $instance_id started successfully (port: $server_port)"
        echo "$(date): Server instance $instance_id started on port $server_port" >> "$log_file"
    else
        echo "Failed to start Server instance $instance_id"
        return 1
    fi
}

# 停止单个OJ实例
stop_oj_instance() {
    local instance_id=$1
    local container_name="oj-rust-$instance_id"

    echo "Stopping OJ instance $instance_id..."
    docker stop "$container_name" >/dev/null 2>&1 || true
    docker rm "$container_name" >/dev/null 2>&1 || true
    rm -f "$PID_DIR/oj_${instance_id}.pid"
}

# 停止单个Server实例
stop_server_instance() {
    local instance_id=$1
    local pid_file="$PID_DIR/server_${instance_id}.pid"

    echo "Stopping Server instance $instance_id..."
    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
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

# 启动所有服务
start_services() {
    echo "Starting $SERVICE_INSTANCES service instances..."

    # 更新服务状态文件
    cat > "$SERVICE_STATUS_FILE" <<EOF
{
    "instances": $SERVICE_INSTANCES,
    "oj_base_port": $OJ_BASE_PORT,
    "server_base_port": $SERVER_BASE_PORT,
    "started_at": "$(date -Iseconds)",
    "services": []
}
EOF

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        start_oj_instance "$i"
        sleep 3  # 等待OJ启动
        start_server_instance "$i"
        sleep 2  # 等待Server启动

        # 更新状态文件
        local oj_port=$((OJ_BASE_PORT + i))
        local server_port=$((SERVER_BASE_PORT + i))
        echo "Recording service instance $i in status file..."
    done

    echo ""
    echo "All services started! Available endpoints:"
    list_service_ports
}

# 停止所有服务
stop_services() {
    echo "Stopping all service instances..."

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        stop_server_instance "$i"
        stop_oj_instance "$i"
    done

    rm -f "$SERVICE_STATUS_FILE"
    echo "All services stopped."
}

# 显示服务状态
show_status() {
    echo "Service Status:"
    echo "==============="

    if [[ ! -f "$SERVICE_STATUS_FILE" ]]; then
        echo "No services running."
        return
    fi

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        local oj_port=$((OJ_BASE_PORT + i))
        local server_port=$((SERVER_BASE_PORT + i))

        printf "Instance %d: " "$i"

        # 检查OJ状态
        if check_service_health "oj" "$oj_port"; then
            printf "OJ(:%d)=✓ " "$oj_port"
        else
            printf "OJ(:%d)=✗ " "$oj_port"
        fi

        # 检查Server状态
        if check_service_health "server" "$server_port"; then
            printf "Server(:%d)=✓" "$server_port"
        else
            printf "Server(:%d)=✗" "$server_port"
        fi

        echo
    done
}

# 列出可用端口
list_service_ports() {
    if [[ ! -f "$SERVICE_STATUS_FILE" ]]; then
        echo "No services running."
        return
    fi

    echo "Available Service Endpoints:"
    echo "============================"

    for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
        local oj_port=$((OJ_BASE_PORT + i))
        local server_port=$((SERVER_BASE_PORT + i))

        if check_service_health "server" "$server_port"; then
            echo "Instance $i: http://localhost:$server_port (OJ: http://localhost:$oj_port)"
        fi
    done
}

# 监控守护进程
start_monitoring() {
    echo "Starting service monitoring (interval: ${CHECK_INTERVAL}s)..."
    echo "Press Ctrl+C to stop monitoring"

    while true; do
        for i in $(seq 0 $((SERVICE_INSTANCES-1))); do
            local oj_port=$((OJ_BASE_PORT + i))
            local server_port=$((SERVER_BASE_PORT + i))

            # 检查并重启失败的服务
            if ! check_service_health "oj" "$oj_port"; then
                echo "$(date): OJ instance $i is down, restarting..."
                stop_oj_instance "$i"
                start_oj_instance "$i"
                sleep 5
            fi

            if ! check_service_health "server" "$server_port"; then
                echo "$(date): Server instance $i is down, restarting..."
                stop_server_instance "$i"
                sleep 2
                start_server_instance "$i"
                sleep 3
            fi
        done

        sleep "$CHECK_INTERVAL"
    done
}

# 主函数
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