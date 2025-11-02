#!/bin/bash

# Script to repeat the competition_run command

set -e

# Default parameters
COMPETITION_CONFIG="config/competition_main.json"
COMPETITORS_CONFIG="config/9llm.json"
PORT="5001"
PROBLEM_IDS="config/problems_contest1.json"
REPEAT_COUNT=3
DELAY=0
LOG_DIR=""

# Show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --competition-config FILE   Competition config (default: config/competition_main.json)"
    echo "  --competitors-config FILE   Competitors config (default: config/9llm.json)"
    echo "  --port PORT                 Server port (default: 5001)"
    echo "  --problem-ids FILE          Problem IDs file (default: config/problems_contest1.json)"
    echo "  --repeat N                  Number of times to repeat (default: 1)"
    echo "  --delay SECONDS             Delay between runs in seconds (default: 0)"
    echo "  --log-dir DIR               Directory to save logs (optional)"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Run the default configuration five times"
    echo "  $0 --repeat 5"
    echo ""
    echo "  # Use alternate configuration files"
    echo "  $0 --competitors-config config/10llm.json --problem-ids config/problems_contest2.json --repeat 3"
    echo ""
    echo "  # Repeat runs with delay and logging"
    echo "  $0 --repeat 10 --delay 60 --log-dir logs/contest_runs"
    echo ""
    echo "Default command that will be run:"
    echo "competition_run --competition-config $COMPETITION_CONFIG --competitors-config $COMPETITORS_CONFIG --port $PORT --problem-ids $PROBLEM_IDS"
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --competition-config)
            COMPETITION_CONFIG="$2"
            shift 2
            ;;
        --competitors-config)
            COMPETITORS_CONFIG="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --problem-ids)
            PROBLEM_IDS="$2"
            shift 2
            ;;
        --repeat)
            REPEAT_COUNT="$2"
            shift 2
            ;;
        --delay)
            DELAY="$2"
            shift 2
            ;;
        --log-dir)
            LOG_DIR="$2"
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

# Configure log directory
if [[ -n "$LOG_DIR" ]]; then
    mkdir -p "$LOG_DIR"
    echo "Logs will be saved to: $LOG_DIR"
fi

# Display configuration
echo "=== Competition Runner Configuration ==="
echo "Competition config: $COMPETITION_CONFIG"
echo "Competitors config: $COMPETITORS_CONFIG"
echo "Port: $PORT"
echo "Problem IDs: $PROBLEM_IDS"
echo "Repeat count: $REPEAT_COUNT"
echo "Delay between runs: ${DELAY}s"
echo "Log directory: ${LOG_DIR:-"(none - output to console)"}"
echo ""

# Build the command
COMMAND="competition_run --competition-config $COMPETITION_CONFIG --competitors-config $COMPETITORS_CONFIG --port $PORT --problem-ids $PROBLEM_IDS"

echo "Command to run: $COMMAND"
echo ""

# Execute repeated runs
SUCCESS_COUNT=0
FAILED_COUNT=0

for i in $(seq 1 $REPEAT_COUNT); do
    echo "=== Competition Run $i/$REPEAT_COUNT ==="
    echo "Starting at: $(date)"

    # Configure the log file
    if [[ -n "$LOG_DIR" ]]; then
        LOG_FILE="$LOG_DIR/competition_${i}_$(date +%Y%m%d_%H%M%S).log"
        echo "Log file: $LOG_FILE"

        # Run the command and capture logs
        echo "Running: $COMMAND" | tee "$LOG_FILE"
        if eval "$COMMAND" >> "$LOG_FILE" 2>&1; then
            echo "Competition run $i: SUCCESS"
            ((SUCCESS_COUNT++))
        else
            echo "Competition run $i: FAILED (see $LOG_FILE for details)"
            ((FAILED_COUNT++))
        fi
    else
        # Run the command directly
        echo "Running: $COMMAND"
        if eval "$COMMAND"; then
            echo "Competition run $i: SUCCESS"
            ((SUCCESS_COUNT++))
        else
            echo "Competition run $i: FAILED"
            ((FAILED_COUNT++))
        fi
    fi

    echo "Completed at: $(date)"

    # Wait before the next run when applicable
    if [[ $i -lt $REPEAT_COUNT && $DELAY -gt 0 ]]; then
        echo "Waiting ${DELAY}s before next run..."
        sleep $DELAY
    fi

    echo ""
done

# Display final statistics
echo "=== Final Summary ==="
echo "Total competitions: $REPEAT_COUNT"
echo "Successful: $SUCCESS_COUNT"
echo "Failed: $FAILED_COUNT"
echo "Success rate: $((SUCCESS_COUNT * 100 / REPEAT_COUNT))%"

if [[ -n "$LOG_DIR" ]]; then
    echo "All logs saved in: $LOG_DIR"
fi

# Set exit code
if [[ $FAILED_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi