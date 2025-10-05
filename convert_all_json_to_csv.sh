#!/bin/bash

# JSON to CSV batch conversion script
# Traverse all subdirectories in run_logs folder, convert first-level JSON files to CSV

# Set color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if converter script exists
CONVERTER_SCRIPT="json_to_csv_converter.py"
if [ ! -f "$CONVERTER_SCRIPT" ]; then
    log_error "Converter script $CONVERTER_SCRIPT does not exist!"
    exit 1
fi

# Check if run_logs directory exists
RUN_LOGS_DIR="logs/run_logs"
if [ ! -d "$RUN_LOGS_DIR" ]; then
    log_error "run_logs directory $RUN_LOGS_DIR does not exist!"
    exit 1
fi

log_info "Starting batch conversion of JSON files to CSV..."

# Statistics variables
total_dirs=0
processed_dirs=0
total_files=0
converted_files=0
skipped_files=0
failed_files=0

# Traverse all subdirectories in run_logs
for dir in "$RUN_LOGS_DIR"/*/; do
    if [ -d "$dir" ]; then
        total_dirs=$((total_dirs + 1))
        dir_name=$(basename "$dir")
        log_info "Processing directory: $dir_name"
        
        # Find first-level JSON files in this directory (excluding files in subdirectories)
        json_files=()
        while IFS= read -r -d '' file; do
            json_files+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.json" -type f -print0)
        
        if [ ${#json_files[@]} -eq 0 ]; then
            log_warning "No JSON files found in directory $dir_name"
            continue
        fi
        
        processed_dirs=$((processed_dirs + 1))
        
        # Process each JSON file
        for json_file in "${json_files[@]}"; do
            total_files=$((total_files + 1))
            filename=$(basename "$json_file")
            
            # Generate CSV filename (in the same directory as JSON file)
            csv_file="${json_file%.json}.csv"
            
            # Check if CSV file already exists
            if [ -f "$csv_file" ]; then
                log_warning "  ⚠ CSV file already exists, skipping: $(basename "$csv_file")"
                skipped_files=$((skipped_files + 1))
                continue
            fi
            
            log_info "  Converting: $filename -> $(basename "$csv_file")"
            
            # Call converter script
            if python3 "$CONVERTER_SCRIPT" "$json_file" "$csv_file" > /dev/null 2>&1; then
                log_success "  ✓ Successfully converted: $filename"
                converted_files=$((converted_files + 1))
            else
                log_error "  ✗ Conversion failed: $filename"
                failed_files=$((failed_files + 1))
            fi
        done
    fi
done

# Output statistics
echo
log_info "=== Conversion Statistics ==="
log_info "Total directories: $total_dirs"
log_info "Processed directories: $processed_dirs"
log_info "Total files: $total_files"
log_success "Successfully converted: $converted_files"
log_warning "Skipped existing: $skipped_files"
if [ $failed_files -gt 0 ]; then
    log_error "Conversion failed: $failed_files"
else
    log_success "Conversion failed: $failed_files"
fi

# If there are failed files, provide suggestions
if [ $failed_files -gt 0 ]; then
    echo
    log_warning "Suggest checking if the failed JSON files have correct format"
fi

log_info "Batch conversion completed!" 