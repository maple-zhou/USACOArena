#!/bin/bash

# 轻量级批处理竞赛脚本 - 只运行实验，连接到现有服务
set -e

# 默认参数
CONCURRENCY=10
COMPETITORS_CONFIG="config/1pro.json"
PROBLEM_IDS_LIST=""
SERVICE_DISCOVERY_RETRIES=3
MANUAL_PORTS=""

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "This script runs competitions by connecting to existing OJ and Server instances."
    echo "Use service_manager.sh to start/stop the underlying services."
    echo ""
    echo "Options:"
    echo "  --concurrency N             Number of concurrent runs (default: 10)"
    echo "  --competitors-config FILE   Competitors config file (default: config/1pro.json)"
    echo "  --problem-ids-list FILES    Comma-separated list of problem ID files"
    echo "  --problem-pattern PATTERN   Pattern to find problem files (e.g., 'config/problem_*.json')"
    echo "  --service-retries N         Service discovery retries (default: 3)"
    echo "  --manual-ports PORTS        Manually specify server ports (comma-separated, e.g., '5000,5001,5002')"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Step 1: Start services"
    echo "  ./service_manager.sh start --instances 3"
    echo ""
    echo "  # Step 2: Run experiments with auto-discovery"
    echo "  $0 --problem-pattern 'config/problem_*.json' --concurrency 10"
    echo ""
    echo "  # Step 2 (Alternative): Run experiments with manual ports"
    echo "  $0 --problem-pattern 'config/problem_*.json' --manual-ports '5000,5001,5002' --concurrency 10"
    echo ""
    echo "  # Step 3: Stop services when done"
    echo "  ./service_manager.sh stop"
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        --competitors-config)
            COMPETITORS_CONFIG="$2"
            shift 2
            ;;
        --problem-ids-list)
            PROBLEM_IDS_LIST="$2"
            shift 2
            ;;
        --problem-pattern)
            PROBLEM_PATTERN="$2"
            shift 2
            ;;
        --service-retries)
            SERVICE_DISCOVERY_RETRIES="$2"
            shift 2
            ;;
        --manual-ports)
            MANUAL_PORTS="$2"
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

# 构建问题文件列表
if [[ -n "$PROBLEM_PATTERN" ]]; then
    echo "Finding problem files with pattern: $PROBLEM_PATTERN"
    PROBLEM_FILES=($(ls $PROBLEM_PATTERN 2>/dev/null | sort))
elif [[ -n "$PROBLEM_IDS_LIST" ]]; then
    echo "Using provided problem files list"
    IFS=',' read -ra PROBLEM_FILES <<< "$PROBLEM_IDS_LIST"
else
    echo "Auto-discovering problem files in config/ directory..."
    PROBLEM_FILES=($(ls config/problem_*.json 2>/dev/null | sort))
fi

# 检查是否找到了问题文件
if [[ ${#PROBLEM_FILES[@]} -eq 0 ]]; then
    echo "Error: No problem files found!"
    echo "Please use --problem-ids-list or --problem-pattern to specify problem files."
    exit 1
fi

TOTAL_RUNS=${#PROBLEM_FILES[@]}

# 服务发现或手动指定端口
setup_services() {
    if [[ -n "$MANUAL_PORTS" ]]; then
        echo "Using manually specified ports: $MANUAL_PORTS"
        IFS=',' read -ra AVAILABLE_SERVICES <<< "$MANUAL_PORTS"

        # 验证端口格式和可用性
        for port in "${AVAILABLE_SERVICES[@]}"; do
            # 移除前后空格
            port=$(echo "$port" | xargs)

            # 验证端口是否为数字
            if ! [[ "$port" =~ ^[0-9]+$ ]]; then
                echo "Error: Invalid port number '$port'"
                exit 1
            fi

            # 可选：验证端口是否在监听（如果需要的话）
            # if ! nc -z localhost "$port" 2>/dev/null; then
            #     echo "Warning: Port $port may not be available"
            # fi
        done

        echo "Manually configured ${#AVAILABLE_SERVICES[@]} services: ${AVAILABLE_SERVICES[*]}"
    else
        echo "Auto-discovering services..."
        discover_services
    fi

    # 根据可用端口数量调整并发数
    adjust_concurrency
}

# 服务发现 - 获取可用的服务端口
discover_services() {
    echo "Discovering available services..."

    if [[ ! -f "pids/service_status.json" ]]; then
        echo "Error: No services found! Please start services first:"
        echo "  ./service_manager.sh start"
        exit 1
    fi

    # 获取可用的服务端点
    AVAILABLE_SERVICES=()
    local retry_count=0

    while [[ ${#AVAILABLE_SERVICES[@]} -eq 0 && $retry_count -lt $SERVICE_DISCOVERY_RETRIES ]]; do
        echo "Service discovery attempt $((retry_count + 1))/$SERVICE_DISCOVERY_RETRIES"

        # 通过service_manager获取可用端点
        local service_output=$(./service_manager.sh list-ports 2>/dev/null | grep "Instance" || true)

        if [[ -n "$service_output" ]]; then
            while IFS= read -r line; do
                if [[ $line =~ Instance\ ([0-9]+):\ http://localhost:([0-9]+) ]]; then
                    local instance_id="${BASH_REMATCH[1]}"
                    local server_port="${BASH_REMATCH[2]}"
                    AVAILABLE_SERVICES+=("$server_port")
                fi
            done <<< "$service_output"
        fi

        if [[ ${#AVAILABLE_SERVICES[@]} -eq 0 ]]; then
            echo "No healthy services found, retrying in 5 seconds..."
            sleep 5
            retry_count=$((retry_count + 1))
        fi
    done

    if [[ ${#AVAILABLE_SERVICES[@]} -eq 0 ]]; then
        echo "Error: No healthy services available after $SERVICE_DISCOVERY_RETRIES attempts"
        echo "Please check service status: ./service_manager.sh status"
        exit 1
    fi

    echo "Found ${#AVAILABLE_SERVICES[@]} available services: ${AVAILABLE_SERVICES[*]}"
}

# 根据可用端口数量调整并发数
adjust_concurrency() {
    local available_ports=${#AVAILABLE_SERVICES[@]}
    local original_concurrency=$CONCURRENCY

    if [ $available_ports -eq 0 ]; then
        echo "Error: No available services found"
        exit 1
    fi

    # 如果并发数超过可用端口数，自动调整为端口数
    if [ $CONCURRENCY -gt $available_ports ]; then
        CONCURRENCY=$available_ports
        echo "Warning: Concurrency ($original_concurrency) exceeds available ports ($available_ports)"
        echo "Automatically adjusted concurrency to $CONCURRENCY"
    else
        echo "Concurrency ($CONCURRENCY) is within available ports limit ($available_ports)"
    fi

    # 如果并发数明显小于端口数，给出提示
    if [ $CONCURRENCY -lt $available_ports ] && [ $((available_ports - CONCURRENCY)) -ge 2 ]; then
        echo "Info: You have $available_ports ports available but only using $CONCURRENCY concurrent jobs"
        echo "Consider increasing --concurrency to maximize port utilization"
    fi
}

echo "Starting lean batch competition execution..."
echo "Initial configuration:"
echo "  Requested concurrency: $CONCURRENCY"
echo "  Total runs: $TOTAL_RUNS"
echo "  Competitors config: $COMPETITORS_CONFIG"
echo ""
echo "Problem files to run:"
for i in "${!PROBLEM_FILES[@]}"; do
    echo "  Competition $i: ${PROBLEM_FILES[$i]}"
done
echo ""

# 发现或配置可用服务
setup_services

echo ""
echo "Final configuration:"
echo "  Actual concurrency: $CONCURRENCY"

# 创建日志目录
LOG_DIR="logs/batch_lean_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "Logs will be saved to: $LOG_DIR"
echo ""

# 运行单个竞赛的函数
run_competition_lean() {
    local run_id=$1
    local problem_file=$2

    # 重新构建可用服务列表（因为数组无法通过export传递给子进程）
    local services_list=(${AVAILABLE_SERVICES_STR})
    local service_count=${#services_list[@]}

    if [ $service_count -eq 0 ]; then
        echo "Error: No available services found in subprocess"
        return 1
    fi

    local server_port=${services_list[$((run_id % service_count))]}
    local log_file="$LOG_DIR/competition_${run_id}.log"

    echo "Starting competition $run_id (Server:$server_port, Problem:$problem_file)..."
    echo "Starting competition $run_id (Server:$server_port, Problem:$problem_file)..." >> "$log_file"

    # 只运行竞赛客户端，连接到现有服务
    competition_run \
        --competition-config config/competition_config.json \
        --competitors-config "$COMPETITORS_CONFIG" \
        --port "$server_port" \
        --problem-ids "$problem_file" \
        >> "$log_file" 2>&1

    local exit_code=$?
    if [ $exit_code -eq 0 ]; then
        echo "Competition $run_id ($problem_file) completed successfully"
        echo "Competition $run_id ($problem_file) completed successfully" >> "$log_file"
    else
        echo "Competition $run_id ($problem_file) failed with exit code $exit_code"
        echo "Competition $run_id ($problem_file) failed with exit code $exit_code" >> "$log_file"
    fi

    return $exit_code
}

# 并发控制 - 将数组转为字符串以便export
AVAILABLE_SERVICES_STR="${AVAILABLE_SERVICES[*]}"
export -f run_competition_lean
export LOG_DIR COMPETITORS_CONFIG AVAILABLE_SERVICES_STR

# 创建任务列表，格式：run_id problem_file
TASK_LIST=""
for i in $(seq 0 $((TOTAL_RUNS-1))); do
    TASK_LIST="$TASK_LIST$i ${PROBLEM_FILES[$i]}\n"
done

# 使用GNU parallel或xargs进行并发执行
if command -v parallel >/dev/null 2>&1; then
    echo "Using GNU parallel for concurrent execution..."
    echo -e "$TASK_LIST" | parallel -j "$CONCURRENCY" --colsep ' ' run_competition_lean {1} {2}
else
    echo "Using xargs for concurrent execution..."
    echo -e "$TASK_LIST" | xargs -n 2 -P "$CONCURRENCY" bash -c 'run_competition_lean "$1" "$2"' _
fi

echo ""
echo "All competitions completed!"
echo "Check logs in: $LOG_DIR"

# 生成汇总报告
echo ""
echo "=== Competition Summary ==="
for i in $(seq 0 $((TOTAL_RUNS-1))); do
    log_file="$LOG_DIR/competition_${i}.log"
    problem_file="${PROBLEM_FILES[$i]}"
    if grep -q "completed successfully" "$log_file" 2>/dev/null; then
        echo "Competition $i ($problem_file): SUCCESS"
    else
        echo "Competition $i ($problem_file): FAILED"
    fi
done

echo ""
echo "Service utilization:"
echo "==================="
for service_port in "${AVAILABLE_SERVICES[@]}"; do
    local count=$(grep -l "Server:$service_port" "$LOG_DIR"/*.log 2>/dev/null | wc -l)
    echo "Server port $service_port: $count competitions"
done