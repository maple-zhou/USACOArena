#!/bin/bash

# Competition run loop script
# Usage: ./run_competition_loop.sh <run_count> [--server-args "..."] [--client-args "..."]

# Check parameters
if [ $# -eq 0 ]; then
    echo "Usage: $0 <run_count> [--server-args \"...\"] [--client-args \"...\"]"
    echo "Example: $0 5 --server-args \"--config config/server_config.json --port 5000\" --client-args \"--competitors_config config/1v3.json --problem_ids problems.txt\""
    exit 1
fi

# Get run count
N=$1
shift

# Parse server/client arguments
SERVER_ARGS=""
CLIENT_ARGS=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --server-args)
            SERVER_ARGS="$2"
            shift 2
            ;;
        --client-args)
            CLIENT_ARGS="$2"
            shift 2
            ;;
        *)
            echo "Unknown parameter: $1"
            exit 1
            ;;
    esac
done

echo "Starting competition loop, total runs: $N"
echo "=================================="

# Create log dir
mkdir -p logs/competition_loops
timestamp=$(date +"%Y%m%d_%H%M%S")
log_file="logs/competition_loops/loop_${timestamp}.log"

# Record start time
echo "Competition loop start time: $(date)" | tee -a "$log_file"

for ((i=1; i<=N; i++)); do
    echo ""
    echo "=================================="
    echo "Round $i (of $N)"
    echo "Start time: $(date)"
    echo "==================================" | tee -a "$log_file"
    echo "Round $i start time: $(date)" | tee -a "$log_file"
    
    # Start competition_server
    # echo "Starting competition_server..."
    echo "Starting competition_server..." | tee -a "$log_file"
    
    # Start server directly (background)
    source .venv/bin/activate
    eval competition_server $SERVER_ARGS > "logs/competition_loops/server_round_${i}.log" 2>&1 &
    server_pid=$!
    
    # echo "Server process ID: $server_pid"
    echo "Server process ID: $server_pid" | tee -a "$log_file"
    
    # Wait for server to start
    # echo "Waiting for server to start..."
    echo "Waiting for server to start..." | tee -a "$log_file"
    
    # Check if server started (wait up to 60 seconds)
    server_started=false
    
    # Extract port from SERVER_ARGS, default 5000
    port=5000
    if [[ "$SERVER_ARGS" == *"--port"* ]]; then
        port=$(echo "$SERVER_ARGS" | grep -o -- '--port [0-9]*' | awk '{print $2}')
    fi

    echo "port: $port"
    
    for ((wait_time=0; wait_time<60; wait_time++)); do
        if curl -s "http://localhost:${port}/api/system/oj-status" > /dev/null 2>&1; then
            server_started=true
            break
        fi
        echo "Waiting for server to start... ($((wait_time+1))/60)"
        sleep 1
    done
    
    if [ "$server_started" = false ]; then
        echo "Error: Server startup timeout"
        echo "Error: Server startup timeout" | tee -a "$log_file"
        # Clean up processes
        if [ ! -z "$server_pid" ]; then
            kill $server_pid 2>/dev/null
            sleep 2
            # If process still exists, force kill
            if kill -0 $server_pid 2>/dev/null; then
                kill -9 $server_pid 2>/dev/null
            fi
        fi
        continue
    fi
    
    sleep 5
    # echo "Server started, starting competition_run..."
    echo "Server started, starting competition_run..." | tee -a "$log_file"
    
    # Start competition_run client (foreground)
    # echo "Running competition_run client..."
    echo "Running competition_run client..." | tee -a "$log_file"
    
    source .venv/bin/activate
    eval competition_run $CLIENT_ARGS > "logs/competition_loops/client_round_${i}.log" 2>&1
    client_exit_code=$?
    
    timestamp=$(date +"%Y%m%d_%H%M%S")
    # echo "Client run completed, exit code: $client_exit_code"
    echo "Client run completed, exit code: $client_exit_code exit time: $timestamp" | tee -a "$log_file"
    
    sleep 5
    # echo "Client run completed, shutting down server..."
    timestamp=$(date +"%Y%m%d_%H%M%S")
    echo "Client run completed, shutting down server... shutdown time: $timestamp" | tee -a "$log_file"
    
    # Shutdown server
    if [ ! -z "$server_pid" ]; then
        # echo "Shutting down server process $server_pid..."
        echo "Shutting down server process: $server_pid..." | tee -a "$log_file"
        
        # Check and kill processes on specific port
        port=$(ps -o args= -p $server_pid 2>/dev/null | grep -o -- '--port [0-9]*' | awk '{print $2}')
        if [ ! -z "$port" ]; then
            echo "Cleaning up processes on port: $port..."
            fuser -k $port/tcp 2>/dev/null
        fi
        
        # Wait for port to be released
        sleep 2
    fi
    
    # Wait for server to fully shutdown
    sleep 3
    
    echo "Round $i completed"
    echo "End time: $(date)"
    echo "Round $i end time: $(date)" | tee -a "$log_file"
    
    # If not the last round, wait before starting next round
    if [ $i -lt $N ]; then
        echo "Waiting 5 seconds before starting next round..."
        echo "Waiting 5 seconds before starting next round..." | tee -a "$log_file"
        sleep 5
    fi
done

bash convert_all_json_to_csv.sh > "$log_file" 2>&1

echo ""
echo "=================================="
echo "All $N rounds completed!"
echo "End time: $(date)"
echo "Log file: $log_file"
echo "==================================" | tee -a "$log_file"
echo "All $N rounds completed! End time: $(date)" | tee -a "$log_file"