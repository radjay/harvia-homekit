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

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Configure the service

Copy the example configuration:

```bash
cp config.json ~/.config/harvia-homekit/config.json
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

```bash
python3 main.py
```

### 5. Install as a system service (optional)

```bash
# Edit the service file to set your username
nano harvia-homekit.service

# Copy files to system locations
sudo mkdir -p /opt/harvia-homekit
sudo cp -r * /opt/harvia-homekit/
sudo cp harvia-homekit.service /etc/systemd/system/

# Enable and start the service
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
python3 main.py --debug
```

## License

MIT License
