#!/bin/bash

# Lightweight batch competition script – run experiments against existing services
set -e

# Default parameters
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

# Parse command-line arguments
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

# Build list of problem files
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

# Ensure at least one problem file is found
if [[ ${#PROBLEM_FILES[@]} -eq 0 ]]; then
    echo "Error: No problem files found!"
    echo "Please use --problem-ids-list or --problem-pattern to specify problem files."
    exit 1
fi

TOTAL_RUNS=${#PROBLEM_FILES[@]}

# Discover services or use manually supplied ports
setup_services() {
    if [[ -n "$MANUAL_PORTS" ]]; then
        echo "Using manually specified ports: $MANUAL_PORTS"
        IFS=',' read -ra AVAILABLE_SERVICES <<< "$MANUAL_PORTS"

        # Validate port formatting and availability
        for port in "${AVAILABLE_SERVICES[@]}"; do
            # Strip whitespace around the port
            port=$(echo "$port" | xargs)

            # Verify the port is numeric
            if ! [[ "$port" =~ ^[0-9]+$ ]]; then
                echo "Error: Invalid port number '$port'"
                exit 1
            fi

            # Optional: verify the port is listening if desired
            # if ! nc -z localhost "$port" 2>/dev/null; then
            #     echo "Warning: Port $port may not be available"
            # fi
        done

        echo "Manually configured ${#AVAILABLE_SERVICES[@]} services: ${AVAILABLE_SERVICES[*]}"
    else
        echo "Auto-discovering services..."
        discover_services
    fi

    # Adjust concurrency to available ports
    adjust_concurrency
}

# Service discovery - obtain available server ports
discover_services() {
    echo "Discovering available services..."

    if [[ ! -f "pids/service_status.json" ]]; then
        echo "Error: No services found! Please start services first:"
        echo "  ./service_manager.sh start"
        exit 1
    fi

    # Retrieve available service endpoints
    AVAILABLE_SERVICES=()
    local retry_count=0

    while [[ ${#AVAILABLE_SERVICES[@]} -eq 0 && $retry_count -lt $SERVICE_DISCOVERY_RETRIES ]]; do
        echo "Service discovery attempt $((retry_count + 1))/$SERVICE_DISCOVERY_RETRIES"

        # Query service_manager for available endpoints
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

# Adjust concurrency to available ports
adjust_concurrency() {
    local available_ports=${#AVAILABLE_SERVICES[@]}
    local original_concurrency=$CONCURRENCY

    if [ $available_ports -eq 0 ]; then
        echo "Error: No available services found"
        exit 1
    fi

    # Clamp concurrency to available port count when necessary
    if [ $CONCURRENCY -gt $available_ports ]; then
        CONCURRENCY=$available_ports
        echo "Warning: Concurrency ($original_concurrency) exceeds available ports ($available_ports)"
        echo "Automatically adjusted concurrency to $CONCURRENCY"
    else
        echo "Concurrency ($CONCURRENCY) is within available ports limit ($available_ports)"
    fi

    # Provide a hint when concurrency is much lower than available ports
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

# Discover or configure available services
setup_services

echo ""
echo "Final configuration:"
echo "  Actual concurrency: $CONCURRENCY"

# Create log directory
LOG_DIR="logs/batch_lean_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "Logs will be saved to: $LOG_DIR"
echo ""

# Function to run a single competition
run_competition_lean() {
    local run_id=$1
    local problem_file=$2

    # Rebuild available services (arrays cannot be exported to child processes)
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

    # Run only the competition client, connecting to existing services
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

# Concurrency control – convert arrays to strings for export
AVAILABLE_SERVICES_STR="${AVAILABLE_SERVICES[*]}"
export -f run_competition_lean
export LOG_DIR COMPETITORS_CONFIG AVAILABLE_SERVICES_STR

# Build task list in the format: run_id problem_file
TASK_LIST=""
for i in $(seq 0 $((TOTAL_RUNS-1))); do
    TASK_LIST="$TASK_LIST$i ${PROBLEM_FILES[$i]}\n"
done

# Use GNU parallel or xargs for concurrent execution
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

# Generate summary report
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