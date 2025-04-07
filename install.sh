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
SYSTEMD_PATH="/etc/systemd/system"

# Create directories
mkdir -p ${INSTALL_PATH}
mkdir -p ${CONFIG_PATH}

# Copy files
echo "Copying files to ${INSTALL_PATH}..."
cp -r ./* ${INSTALL_PATH}/

# Update systemd service file with correct username
echo "Configuring service file with user: ${CURRENT_USER}"
sed -i "s/YOUR_USERNAME/${CURRENT_USER}/g" ${INSTALL_PATH}/harvia-homekit.service

# Copy service file
echo "Installing systemd service..."
cp ${INSTALL_PATH}/harvia-homekit.service ${SYSTEMD_PATH}/

# Create config if it doesn't exist
if [ ! -f "${CONFIG_PATH}/config.json" ]; then
  echo "Creating default config file..."
  cp ${INSTALL_PATH}/config.json ${CONFIG_PATH}/
  echo "Please edit ${CONFIG_PATH}/config.json with your credentials."
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r ${INSTALL_PATH}/requirements.txt

# Set permissions
echo "Setting permissions..."
chown -R ${CURRENT_USER}:${CURRENT_USER} ${CONFIG_PATH}
chmod -R 750 ${CONFIG_PATH}
chmod +x ${INSTALL_PATH}/main.py

# Enable and start service
echo "Enabling and starting service..."
systemctl daemon-reload
systemctl enable harvia-homekit
systemctl restart harvia-homekit

echo ""
echo "Installation complete!"
echo "Service status:"
systemctl status harvia-homekit
echo ""
echo "To check logs:"
echo "  journalctl -u harvia-homekit -f"
echo ""
echo "Don't forget to edit your configuration:"
echo "  nano ${CONFIG_PATH}/config.json" 