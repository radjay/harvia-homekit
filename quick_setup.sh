#!/bin/bash
# Quick setup script for Harvia HomeKit integration
# This script helps you set up the Harvia HomeKit integration without cloning the repository manually

set -e

echo "======================= Harvia Sauna HomeKit Setup ======================="
echo ""
echo "This script will help you set up the Harvia Sauna HomeKit integration."
echo "It will:"
echo "  1. Clone the repository"
echo "  2. Set up a Python virtual environment"
echo "  3. Configure your credentials"
echo "  4. Run the service"
echo ""
echo "Press CTRL+C at any time to cancel."
echo ""
read -p "Press Enter to continue..."

# Check for required commands
for cmd in git python3 pip; do
    if ! command -v $cmd &> /dev/null; then
        echo "Error: $cmd is required but not installed." 
        echo "Please install $cmd and try again."
        exit 1
    fi
done

# Get the repo URL
REPO_URL="https://github.com/yourusername/harvia-homekit.git"
read -p "GitHub repository URL (press Enter for default): " user_repo
if [ ! -z "$user_repo" ]; then
    REPO_URL=$user_repo
fi

# Create a directory for the project
INSTALL_DIR="$HOME/harvia-homekit"
read -p "Installation directory (press Enter for $INSTALL_DIR): " user_dir
if [ ! -z "$user_dir" ]; then
    INSTALL_DIR=$user_dir
fi

if [ -d "$INSTALL_DIR" ]; then
    echo ""
    echo "Directory $INSTALL_DIR already exists."
    read -p "Do you want to remove it and start fresh? (y/n): " remove_dir
    if [ "$remove_dir" == "y" ]; then
        rm -rf "$INSTALL_DIR"
    else
        echo "Please choose a different directory or delete the existing one."
        exit 1
    fi
fi

# Clone the repository
echo ""
echo "Cloning repository to $INSTALL_DIR..."
git clone $REPO_URL "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Set up virtual environment
echo ""
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Get user credentials
echo ""
echo "Now we need your Harvia account credentials."
echo "These will be stored locally in your configuration file."
echo ""
read -p "Harvia username (email): " harvia_username
read -s -p "Harvia password: " harvia_password
echo ""
read -p "Device ID (leave blank to try auto-discovery): " device_id
read -p "Device name (press Enter for 'My Sauna'): " device_name
if [ -z "$device_name" ]; then
    device_name="My Sauna"
fi

# Create config directory
CONFIG_DIR="$HOME/.config/harvia-homekit"
mkdir -p "$CONFIG_DIR"

# Create config file
echo ""
echo "Creating configuration file..."
cat > "$CONFIG_DIR/config.json" << EOF
{
    "username": "$harvia_username",
    "password": "$harvia_password",
    "pin_code": "031-45-154",
    "service_name": "Harvia Sauna",
    "device_id": "$device_id",
    "device_name": "$device_name"
}
EOF

# Make scripts executable
chmod +x main.py
chmod +x setup_dev.sh
chmod +x install.sh

# Run the service
echo ""
echo "Setup complete! You can now run the service with:"
echo ""
echo "cd $INSTALL_DIR"
echo "source venv/bin/activate"
echo "python main.py"
echo ""
echo "To install as a system service, run:"
echo "sudo $INSTALL_DIR/install.sh"
echo ""

# Ask if they want to run it now
read -p "Do you want to run the service now? (y/n): " run_now
if [ "$run_now" == "y" ]; then
    echo "Running service in debug mode..."
    python main.py --debug
else
    echo "You can run the service later using the commands above."
fi 