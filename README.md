# Harvia Sauna HomeKit Integration

This project provides a standalone Python service that integrates with Apple HomeKit to control your Harvia Xenio WiFi sauna without needing Home Assistant.

## Features

- Direct integration with Apple HomeKit
- Control sauna power, temperature, humidity, fan, and lights
- Door state sensor
- Real-time updates via websocket connections
- Runs as a system service (supports both Linux systemd and macOS launchd)

## Repository Structure

The repository is organized as follows:

- `main.py` - Main entry point for the service
- `pyhap_harvia/` - Core implementation of the Harvia API and HomeKit integration
  - `api.py` - API client for Harvia Cloud services
  - `device.py` - Device state management and websocket communication
  - `accessories/` - HomeKit accessory implementations
    - `sauna.py` - Sauna accessory implementation for HomeKit
- `tests/` - Test scripts for development and debugging
  - `test_temp.py` - Simple test to set the sauna temperature
  - `test_websocket.py` - Test for websocket communication
  - `test_device_discovery.py` - Test for device discovery
  - Additional test scripts for various functionality
- Installation scripts:
  - `install.sh` - Main installation script for system service

## Requirements

- Python 3.6 or higher
- Harvia Xenio WiFi sauna with cloud connection
- Apple HomeKit compatible device (iPhone, iPad, or Mac)
- macOS or Debian/Ubuntu-based system for service installation

## Installation

Follow these steps to install the service:

### 1. Clone the repository

```bash
git clone https://github.com/radjay/harvia-homekit.git
cd harvia-homekit
```

### 2. Set up a Python virtual environment

It's recommended to use a virtual environment to avoid conflicts with system packages:

```bash
# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Now install the dependencies
pip install -r requirements.txt
```

Always activate the virtual environment before running the service manually.

### 3. Configure the service

Create your configuration file from the example:

```bash
# Create the config directory
mkdir -p ~/.config/harvia-homekit/

# Copy the example config as a starting point
cp config.example.json ~/.config/harvia-homekit/config.json
```

Edit the configuration with your Harvia cloud credentials:

```bash
nano ~/.config/harvia-homekit/config.json
```

Your config.json file should look like this:

```json
{
  "username": "your_harvia_username",
  "password": "your_harvia_password",
  "pin_code": "031-45-154",
  "service_name": "Harvia Sauna",
  "device_id": "",
  "device_name": "My Sauna"
}
```

**Security Warning**: Never commit your config.json file with real credentials to version control. The example config file is provided as a template only.

**Note**: The `device_id` field is used when the service cannot automatically discover your sauna through the API. See the [Finding Your Device ID](#finding-your-device-id) section below.

### 4. Run the service manually

Ensure your virtual environment is activated, then run:

```bash
python main.py
```

To run with debug logging:

```bash
python main.py --debug
```

### 5. Install as a system service

The simplest way to install as a system service is to use our installation script:

```bash
sudo ./install.sh
```

This script automatically detects your operating system and installs the appropriate service:

- On Linux: Creates a systemd service
- On macOS: Creates a launchd service

#### Manual service installation (Linux)

If you prefer to install the systemd service manually on Linux:

```bash
# First, edit the service file to set your username
nano harvia-homekit.service
```

Modify the service file to use the virtual environment:

```ini
[Unit]
Description=Harvia Sauna HomeKit Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/opt/harvia-homekit
# Update this line to use the virtual environment
ExecStart=/opt/harvia-homekit/venv/bin/python /opt/harvia-homekit/main.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Then install the service:

```bash
# Create installation directory
sudo mkdir -p /opt/harvia-homekit

# Copy files
sudo cp -r * /opt/harvia-homekit/

# Set up virtual environment in the installation directory
sudo python3 -m venv /opt/harvia-homekit/venv
sudo /opt/harvia-homekit/venv/bin/pip install -r /opt/harvia-homekit/requirements.txt

# Copy service file (after editing it with your username)
sudo cp /opt/harvia-homekit/harvia-homekit.service /etc/systemd/system/

# Set permissions
sudo chmod +x /opt/harvia-homekit/main.py

# Create config directory if it doesn't exist
mkdir -p ~/.config/harvia-homekit/
cp config.example.json ~/.config/harvia-homekit/config.json # Use the example config as a template

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable harvia-homekit
sudo systemctl start harvia-homekit
```

#### Manual service installation (macOS)

If you prefer to install the launchd service manually on macOS:

```bash
# Create a plist file
cat > com.harvia.homekit.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.harvia.homekit</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/harvia-homekit/venv/bin/python</string>
        <string>/opt/harvia-homekit/main.py</string>
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
    <string>YOUR_USERNAME</string>
    <key>WorkingDirectory</key>
    <string>/opt/harvia-homekit</string>
</dict>
</plist>
EOF

# Edit the plist file to set your username
nano com.harvia.homekit.plist

# Create installation directory and copy files
sudo mkdir -p /opt/harvia-homekit
sudo cp -r * /opt/harvia-homekit/

# Set up virtual environment
sudo python3 -m venv /opt/harvia-homekit/venv
sudo /opt/harvia-homekit/venv/bin/pip install -r /opt/harvia-homekit/requirements.txt

# Copy the plist file to LaunchDaemons
sudo cp com.harvia.homekit.plist /Library/LaunchDaemons/

# Set permissions
sudo chmod +x /opt/harvia-homekit/main.py

# Create config directory if it doesn't exist and use example config
mkdir -p ~/.config/harvia-homekit/
cp config.example.json ~/.config/harvia-homekit/config.json

# Edit the config with your actual credentials (never commit this file to git)
nano ~/.config/harvia-homekit/config.json

# Load the service
sudo launchctl load /Library/LaunchDaemons/com.harvia.homekit.plist
sudo launchctl start com.harvia.homekit
```

## Finding Your Device ID

If the service fails to automatically discover your sauna, you'll need to manually specify the device ID in your configuration file. Here are several ways to find your device ID:

### Method 1: Using the Harvia mobile app

1. Install and login to the official Harvia mobile app
2. Navigate to your sauna in the app
3. Look for device information in the settings or about section
4. The device ID may be displayed as a serial number or device identifier

### Method 2: Using the debug mode

The debug mode can help you see what's happening with the API:

1. Ensure your virtual environment is activated
2. Run the service with debug logging enabled:
   ```bash
   python main.py --debug
   ```
3. Look for errors or device discovery attempts in the logs
4. Check if any partial device information is displayed

### Method 3: Using Network Inspection

If you have access to a network monitoring tool or can capture the traffic from the official Harvia app:

1. Use a tool like Wireshark or a proxy like Charles to inspect the network traffic
2. Look for GraphQL requests to the Harvia cloud API
3. Find requests containing device information and extract the device ID

Once you have found your device ID, add it to your config.json file:

```json
{
  "username": "your_harvia_username",
  "password": "your_harvia_password",
  "pin_code": "031-45-154",
  "service_name": "Harvia Sauna",
  "device_id": "your-device-id-here",
  "device_name": "My Sauna"
}
```

## Adding to Apple Home

1. Open the Home app on your iOS device
2. Tap the "+" button to add an accessory
3. Tap "Add Accessory"
4. Tap "I Don't Have a Code or Cannot Scan"
5. Look for "Harvia Sauna Bridge" under "Nearby Accessories"
6. Enter the PIN code from your config (default: 031-45-154)
7. Follow the prompts to complete the setup

## Controlling the Sauna

After adding to Apple Home, you'll see the following accessories:

- **Thermostat**: Control power and temperature
- **Light**: Control the sauna lights
- **Fan**: Control the ventilation fan
- **Steamer**: Control the steam generator (if available)
- **Door Sensor**: Shows if the sauna door is open/closed

## Troubleshooting

### Common Issues

#### Cannot Find Devices

If you see an error like `No sauna devices found` or `Field 'listDevices' in type 'Query' is undefined`:

1. The Harvia API structure has changed or your account doesn't have the correct permissions
2. Add your device ID manually to the configuration file (see [Finding Your Device ID](#finding-your-device-id))
3. Check your internet connection and firewall settings

#### Authentication Failures

If you see errors about authentication:

1. Verify your username and password are correct
2. Ensure you're using the same credentials as the official Harvia app
3. Check if your account has been locked due to too many failed attempts

#### Connection Issues

If the service starts but doesn't respond to commands:

1. Make sure your sauna is connected to your home Wi-Fi
2. Verify the sauna is registered to your Harvia account
3. Check if the sauna can be controlled via the official Harvia app

### Checking Logs

For service logs:

```bash
sudo systemctl status harvia-homekit
sudo journalctl -u harvia-homekit -f
```

For detailed logging, run with the debug flag:

```bash
# If running manually with virtual environment:
python main.py --debug

# If running as a service:
sudo systemctl stop harvia-homekit
sudo -u YOUR_USERNAME /opt/harvia-homekit/venv/bin/python /opt/harvia-homekit/main.py --debug
```

## License

MIT License
