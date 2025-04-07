#!/bin/bash
# Setup development environment for Harvia HomeKit Service

set -e

echo "Setting up development environment for Harvia HomeKit..."

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created at ./venv"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create config directory
CONFIG_DIR="${HOME}/.config/harvia-homekit"
if [ ! -d "$CONFIG_DIR" ]; then
    echo "Creating config directory at $CONFIG_DIR..."
    mkdir -p "$CONFIG_DIR"
fi

# Copy config file if it doesn't exist
if [ ! -f "${CONFIG_DIR}/config.json" ]; then
    echo "Copying example config.json to $CONFIG_DIR..."
    cp config.json "$CONFIG_DIR/"
    echo "Please edit ${CONFIG_DIR}/config.json with your credentials."
fi

echo ""
echo "Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the service in debug mode:"
echo "  python main.py --debug"
echo ""
echo "Don't forget to edit your configuration:"
echo "  nano ${CONFIG_DIR}/config.json" 