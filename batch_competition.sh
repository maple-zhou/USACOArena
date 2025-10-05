#!/bin/bash

# 设置错误时退出
set -e

# 默认参数
CONCURRENCY=10
BASE_OJ_PORT=9000
BASE_SERVER_PORT=5000
COMPETITORS_CONFIG="config/1pro.json"
PROBLEM_IDS_LIST=""  # 将通过参数或自动发现设置
TOTAL_RUNS=0  # 将根据问题文件数量自动设置

# 显示使用说明
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  --concurrency N             Number of concurrent runs (default: 10)"
    echo "  --base-oj-port PORT         Base OJ port, will increment (default: 9000)"
    echo "  --base-server-port PORT     Base server port, will increment (default: 5000)"
    echo "  --competitors-config FILE   Competitors config file (default: config/1pro.json)"
    echo "  --problem-ids-list FILES    Comma-separated list of problem ID files"
    echo "  --problem-pattern PATTERN   Pattern to find problem files (e.g., 'config/problem_*.json')"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Use specific problem files"
    echo "  $0 --problem-ids-list 'config/problem_1467.json,config/problem_1468.json,config/problem_1469.json'"
    echo ""
    echo "  # Auto-discover all problem files"
    echo "  $0 --problem-pattern 'config/problem_*.json'"
    echo ""
    echo "  # Custom concurrency and ports"
    echo "  $0 --concurrency 5 --base-oj-port 9100 --problem-pattern 'config/problem_*.json'"
    echo ""
    echo "Each competition will run with a different problem file and unique ports."
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        --base-oj-port)
            BASE_OJ_PORT="$2"
            shift 2
            ;;
        --base-server-port)
            BASE_SERVER_PORT="$2"
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
    echo "Or make sure problem files exist in config/ directory with pattern problem_*.json"
    exit 1
fi

TOTAL_RUNS=${#PROBLEM_FILES[@]}

echo "Starting batch competition execution..."
echo "Configuration:"
echo "  Concurrency: $CONCURRENCY"
echo "  Total runs: $TOTAL_RUNS"
echo "  Base OJ port: $BASE_OJ_PORT"
echo "  Base server port: $BASE_SERVER_PORT"
echo "  Competitors config: $COMPETITORS_CONFIG"
echo ""
echo "Problem files to run:"
for i in "${!PROBLEM_FILES[@]}"; do
    echo "  Competition $i: ${PROBLEM_FILES[$i]}"
done
echo ""

# 创建日志目录
LOG_DIR="logs/batch_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "Logs will be saved to: $LOG_DIR"
echo ""

# 运行单个竞赛的函数
run_competition() {
    local run_id=$1
    local problem_file=$2
    local oj_port=$((BASE_OJ_PORT + run_id))
    local server_port=$((BASE_SERVER_PORT + run_id))
    local log_file="$LOG_DIR/competition_${run_id}.log"

    echo "Starting competition $run_id (OJ:$oj_port, Server:$server_port, Problem:$problem_file)..."
    echo "Starting competition $run_id (OJ:$oj_port, Server:$server_port, Problem:$problem_file)..." >> "$log_file"

    # 运行竞赛并记录日志（完全静默，只输出到日志文件）
    ./run_full_competition.sh \
        --oj-port "$oj_port" \
        --server-port "$server_port" \
        --competitors-config "$COMPETITORS_CONFIG" \
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

# 并发控制
export -f run_competition
export LOG_DIR BASE_OJ_PORT BASE_SERVER_PORT COMPETITORS_CONFIG

# 创建任务列表，格式：run_id problem_file
TASK_LIST=""
for i in $(seq 0 $((TOTAL_RUNS-1))); do
    TASK_LIST="$TASK_LIST$i ${PROBLEM_FILES[$i]}\n"
done

# 使用GNU parallel或xargs进行并发执行
if command -v parallel >/dev/null 2>&1; then
    echo "Using GNU parallel for concurrent execution..."
    echo -e "$TASK_LIST" | parallel -j "$CONCURRENCY" --colsep ' ' run_competition {1} {2}
else
    echo "Using xargs for concurrent execution..."
    echo -e "$TASK_LIST" | xargs -n 2 -P "$CONCURRENCY" -I {} bash -c 'run_competition $1 "$2"' _ {}
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
    if grep -q "Competition completed!" "$log_file" 2>/dev/null; then
        echo "Competition $i ($problem_file): SUCCESS"
    else
        echo "Competition $i ($problem_file): FAILED"
    fi
done