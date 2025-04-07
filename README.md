# Harvia Sauna HomeKit Integration

This project provides a standalone Python service that integrates with Apple HomeKit to control your Harvia Xenio WiFi sauna without needing Home Assistant.

## Features

- Direct integration with Apple HomeKit
- Control sauna power, temperature, humidity, fan, and lights
- Door state sensor
- Real-time updates via websocket connections
- Runs as a system service

## Requirements

- Python 3.6 or higher
- Harvia Xenio WiFi sauna with cloud connection
- Apple HomeKit compatible device (iPhone, iPad, or Mac)
- Debian/Ubuntu-based system for service installation (optional)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/harvia-homekit.git
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

Copy the example configuration:

```bash
# Create the config directory
mkdir -p ~/.config/harvia-homekit/

# Copy the example config
cp config.json ~/.config/harvia-homekit/
```

Edit the configuration with your Harvia cloud credentials:

```bash
nano ~/.config/harvia-homekit/config.json
```

```json
{
  "username": "your_harvia_username",
  "password": "your_harvia_password",
  "pin_code": "031-45-154",
  "service_name": "Harvia Sauna"
}
```

### 4. Run the service manually

Ensure your virtual environment is activated, then run:

```bash
python main.py
```

To run with debug logging:

```bash
python main.py --debug
```

### 5. Install as a system service (optional)

For a system service, we'll need to modify the installation script to use the virtual environment.

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
cp config.json ~/.config/harvia-homekit/ # if you haven't already

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable harvia-homekit
sudo systemctl start harvia-homekit
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

Check the service status and logs:

```bash
sudo systemctl status harvia-homekit
sudo journalctl -u harvia-homekit -f
```

For more detailed logging, run with the debug flag:

```bash
# If running manually with virtual environment:
python main.py --debug

# If running as a service:
sudo systemctl stop harvia-homekit
sudo -u YOUR_USERNAME /opt/harvia-homekit/venv/bin/python /opt/harvia-homekit/main.py --debug
```

## License

MIT License
