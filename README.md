# Harvia Sauna HomeKit Integration

Control your Harvia Xenio WiFi sauna from the command line or through Apple HomeKit — no Home Assistant required.

## Features

- **CLI** — `harvia-sauna start/stop/status/temp` for quick control from any terminal
- **HomeKit bridge** — thermostat accessory with real-time temperature updates via WebSocket
- **Runs as a system service** — supports both macOS launchd and Linux systemd

## Quick Start

```bash
# Install in a virtualenv
python3 -m venv venv && source venv/bin/activate
pip install .

# Set up your config
mkdir -p ~/.config/harvia-homekit
cp config.example.json ~/.config/harvia-homekit/config.json
nano ~/.config/harvia-homekit/config.json   # add your credentials

# Use the CLI
harvia-sauna status          # show current state
harvia-sauna start           # turn sauna ON
harvia-sauna stop            # turn sauna OFF
harvia-sauna temp 80         # set temperature to 80°C
harvia-sauna service         # run the HomeKit bridge
```

## Requirements

- Python 3.9+ (tested up to 3.14)
- Harvia Xenio WiFi sauna with cloud connection
- Apple HomeKit compatible device (iPhone, iPad, or Mac)
- For remote control: an Apple Home Hub (Apple TV, HomePod, or iPad) on the same network

## Installation

### 1. Clone and install

```bash
git clone https://github.com/radjay/harvia-homekit.git
cd harvia-homekit
python3 -m venv venv
source venv/bin/activate
pip install .
```

### 2. Configure

Create your configuration file from the example:

```bash
mkdir -p ~/.config/harvia-homekit/
cp config.example.json ~/.config/harvia-homekit/config.json
```

Edit with your Harvia cloud credentials:

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

**Note**: The `device_id` field is used when the service cannot automatically discover your sauna through the API. See [Finding Your Device ID](#finding-your-device-id) below.

### 3. CLI Usage

All one-shot commands connect to the Harvia Cloud API, perform the operation, and disconnect (~2-3 seconds):

```bash
harvia-sauna status                    # print power, temperature, humidity
harvia-sauna start                     # turn the sauna ON
harvia-sauna stop                      # turn the sauna OFF
harvia-sauna temp 80                   # set target temperature to 80°C
harvia-sauna status --debug            # verbose output
harvia-sauna status --config /path/to/config.json
```

### 4. Run the HomeKit bridge

```bash
harvia-sauna service                   # foreground
harvia-sauna service --debug           # with debug logging
```

### 5. Install as a system service

```bash
deactivate  # if you're in a venv
sudo ./install.sh
```

This installs the package into `/opt/harvia-homekit/venv` via `pip install` and sets up a launchd (macOS) or systemd (Linux) service that runs `harvia-sauna service`.

If `install.sh` fails to create the venv (common with macOS system Python), create it manually first:

```bash
brew install python3
sudo rm -rf /opt/harvia-homekit/venv
sudo /opt/homebrew/bin/python3 -m venv /opt/harvia-homekit/venv
sudo ./install.sh
```

**Important**: Make sure to deactivate any virtual environment before running `install.sh`.

## Repository Structure

```
src/harvia_sauna/
├── __init__.py            # Package version
├── cli.py                 # CLI entry point (harvia-sauna command)
├── config.py              # Configuration loading
├── logging_setup.py       # Centralised logging setup
├── api.py                 # Harvia Cloud API client
├── device.py              # Device state + WebSocket communication
├── service.py             # HomeKit bridge service logic
└── accessories/
    └── sauna.py           # HomeKit thermostat accessory
```

## Finding Your Device ID

If the service fails to automatically discover your sauna, you'll need to manually specify the device ID in your configuration file.

**Important**: The device ID is a UUID (e.g. `e9d119f8-76f6-4c6e-831f-231238570790`), not the serial number printed on your sauna.

### Method 1: Using debug mode (recommended)

```bash
harvia-sauna status --debug
```

Check the output or WebSocket log for the device ID:

```bash
tail -f /tmp/harvia-homekit/websocket.log | grep deviceId
```

### Method 2: Using network inspection

Use Wireshark or a proxy like Charles to inspect GraphQL requests from the official Harvia app.

Once you have your device ID, add it to `config.json`:

```json
{
  "device_id": "e9d119f8-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

## Adding to Apple Home

1. Open the Home app on your iOS device
2. Tap "+" > "Add Accessory"
3. Tap "More options..." or "I Don't Have a Code or Cannot Scan"
4. Look for "Harvia Sauna Bridge" under "Nearby Accessories"
5. Enter the PIN code from your config (default: `031-45-154`)

**Your iPhone must be on the same network as the machine running the service.**

## Troubleshooting

### Accessory Not Found in Home App

1. Check the service is running and port 51826 is listening:
   ```bash
   # macOS
   sudo launchctl list | grep harvia
   lsof -i :51826

   # Linux
   sudo systemctl status harvia-homekit
   ```
2. Verify mDNS is broadcasting:
   ```bash
   dns-sd -B _hap._tcp  # should show "Harvia Sauna Bridge"
   ```
3. **macOS firewall**: Allow the Python binary through
4. **VPN/Tailscale**: Enable "Allow local network access" for mDNS discovery

### Temperature Not Updating

1. Check that `device_id` is the **API UUID**, not the serial number
2. Check WebSocket logs for "ignoring update for different device":
   ```bash
   grep "ignoring" /tmp/harvia-homekit/websocket.log
   ```

### Checking Logs

```bash
# macOS (launchd)
sudo launchctl list | grep harvia
cat /tmp/harvia-homekit.out
cat /tmp/harvia-homekit.err
tail -f /tmp/harvia-homekit/api.log
tail -f /tmp/harvia-homekit/websocket.log

# Linux (systemd)
sudo systemctl status harvia-homekit
sudo journalctl -u harvia-homekit -f
```

## License

MIT License
