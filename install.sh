#!/bin/bash
# Installation script for Harvia HomeKit Service

set -e

# Script must be run as root for system-wide installation
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Get the current user who called sudo
SUDO_USER_HOME=$(eval echo ~${SUDO_USER})
CURRENT_USER=${SUDO_USER}

# Determine installation path
echo "Installing Harvia HomeKit service..."
INSTALL_PATH="/opt/harvia-homekit"
CONFIG_PATH="${SUDO_USER_HOME}/.config/harvia-homekit"

# Detect OS type
IS_MACOS=false
if [[ "$OSTYPE" == "darwin"* ]]; then
  IS_MACOS=true
  LAUNCHD_PATH="/Library/LaunchDaemons"
  USER_GROUP="staff"  # Default user group on macOS
  echo "Detected macOS: Will use launchd for service management"
else
  SYSTEMD_PATH="/etc/systemd/system"
  USER_GROUP=${CURRENT_USER}  # On Linux, group often matches username
  echo "Detected Linux: Will use systemd for service management"
fi

# Create directories
mkdir -p ${INSTALL_PATH}
mkdir -p ${CONFIG_PATH}

# Copy files
echo "Copying files to ${INSTALL_PATH}..."
cp -r ./* ${INSTALL_PATH}/

# Check for existing user configuration
if [ -f "${CONFIG_PATH}/config.json" ]; then
  echo "Found existing configuration, will use it for the service."
else
  echo "Creating default config file..."
  cp ${INSTALL_PATH}/config.json ${CONFIG_PATH}/
  echo "Please edit ${CONFIG_PATH}/config.json with your credentials."
fi

# Always copy the latest user configuration to the service directory
echo "Updating service configuration..."
cp ${CONFIG_PATH}/config.json ${INSTALL_PATH}/config.json

# Set up virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv ${INSTALL_PATH}/venv
${INSTALL_PATH}/venv/bin/pip install --upgrade pip
${INSTALL_PATH}/venv/bin/pip install -r ${INSTALL_PATH}/requirements.txt

if [ "$IS_MACOS" = true ]; then
  # Create launchd plist file for macOS
  echo "Creating launchd service file..."
  cat > ${INSTALL_PATH}/com.harvia.homekit.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.harvia.homekit</string>
    <key>ProgramArguments</key>
    <array>
        <string>${INSTALL_PATH}/venv/bin/python</string>
        <string>${INSTALL_PATH}/main.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardErrorPath</key>
    <string>/tmp/harvia-homekit.err</string>
    <key>StandardOutPath</key>
    <string>/tmp/harvia-homekit.out</string>
    <key>UserName</key>
    <string>${CURRENT_USER}</string>
    <key>WorkingDirectory</key>
    <string>${INSTALL_PATH}</string>
</dict>
</plist>
EOF

  # Install launchd service
  echo "Installing launchd service..."
  cp ${INSTALL_PATH}/com.harvia.homekit.plist ${LAUNCHD_PATH}/
  
  # Stop the service if it's running
  echo "Stopping any existing service..."
  launchctl unload ${LAUNCHD_PATH}/com.harvia.homekit.plist 2>/dev/null || true
  
  # Load the service
  echo "Loading and starting service..."
  launchctl load ${LAUNCHD_PATH}/com.harvia.homekit.plist || {
    echo "Warning: Failed to load service. Will try alternative method..."
    launchctl bootstrap system ${LAUNCHD_PATH}/com.harvia.homekit.plist || {
      echo "Error: Could not start service. You may need to restart your system."
    }
  }
else
  # Update systemd service file with correct username and paths
  echo "Configuring systemd service file with user: ${CURRENT_USER}"
  sed -i "s/YOUR_USERNAME/${CURRENT_USER}/g" ${INSTALL_PATH}/harvia-homekit.service
  sed -i "s|ExecStart=/usr/bin/python3 /opt/harvia-homekit/main.py|ExecStart=${INSTALL_PATH}/venv/bin/python ${INSTALL_PATH}/main.py|g" ${INSTALL_PATH}/harvia-homekit.service

  # Copy service file
  echo "Installing systemd service..."
  cp ${INSTALL_PATH}/harvia-homekit.service ${SYSTEMD_PATH}/

  # Enable and start service
  echo "Enabling and starting service..."
  systemctl daemon-reload
  systemctl enable harvia-homekit
  systemctl restart harvia-homekit
fi

# Set permissions with correct group
echo "Setting permissions..."
chown -R ${CURRENT_USER}:${USER_GROUP} ${CONFIG_PATH}
chmod -R 750 ${CONFIG_PATH}
chmod +x ${INSTALL_PATH}/main.py

echo ""
echo "Installation complete!"
if [ "$IS_MACOS" = true ]; then
  echo "Service has been installed with launchd."
  echo ""
  echo "To check service status:"
  echo "  sudo launchctl list | grep harvia"
  echo ""
  echo "To view logs:"
  echo "  cat /tmp/harvia-homekit.out"
  echo "  cat /tmp/harvia-homekit.err"
  echo ""
  echo "To stop the service:"
  echo "  sudo launchctl unload ${LAUNCHD_PATH}/com.harvia.homekit.plist"
  echo ""
  echo "To start the service:"
  echo "  sudo launchctl load ${LAUNCHD_PATH}/com.harvia.homekit.plist"
else
  echo "Service status:"
  systemctl status harvia-homekit
  echo ""
  echo "To check logs:"
  echo "  journalctl -u harvia-homekit -f"
fi

echo ""
echo "Don't forget to edit your configuration if needed:"
echo "  nano ${CONFIG_PATH}/config.json"
echo ""
echo "After editing the configuration, restart the service to apply changes." 