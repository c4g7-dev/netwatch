#!/bin/bash
# NetWatch Launcher Script for Linux/macOS

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Error: Virtual environment not found. Run 'python3 -m venv .venv' first."
    exit 1
fi

# Activate virtual environment and run
source .venv/bin/activate
exec python main.py "$@"
