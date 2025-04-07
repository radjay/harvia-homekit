#!/bin/bash

# Script to monitor all Harvia HomeKit logs in real-time

# Create a temp directory for logs if it doesn't exist
mkdir -p /tmp/harvia-homekit

# Colors for different log files
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to monitor a log file with a specific color and prefix
monitor_log() {
    local log_file=$1
    local color=$2
    local prefix=$3
    
    # Check if the file exists, create it if not
    touch $log_file
    
    # Start tail in background
    tail -F $log_file | while read line; do
        echo -e "${color}[${prefix}]${NC} $line"
    done &
}

# Clear screen
clear

echo "====================================================="
echo "Harvia HomeKit Log Monitor"
echo "Press Ctrl+C to exit"
echo "====================================================="

# Monitor all the log files
monitor_log "/tmp/harvia-homekit.err" "$RED" "ERROR"
monitor_log "/tmp/harvia-homekit/api.log" "$GREEN" "API"
monitor_log "/tmp/harvia-homekit/websocket.log" "$YELLOW" "WEBSOCKET"
monitor_log "/tmp/harvia-homekit/sauna_state.log" "$BLUE" "SAUNA"

# Wait for user interrupt
echo "Monitoring logs... press Ctrl+C to exit"
trap "echo -e '\nStopping log monitoring'; kill 0; exit" SIGINT
wait 