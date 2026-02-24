"""CLI entry point for harvia-sauna."""

import argparse
import asyncio
import json
import logging
import sys

from .config import get_config
from .logging_setup import setup_logging

logger = logging.getLogger("harvia_sauna")


# ── helpers ──────────────────────────────────────────────────────────

def _build_fallback_device(config):
    """Return a fallback device dict from config, or None."""
    device_id = config.get("device_id")
    if not device_id:
        return None
    return {
        "id": device_id,
        "displayName": config.get("device_name", f"Sauna {device_id}"),
        "type": "XENIO",
        "active": False,
        "connectionState": "UNKNOWN",
    }


async def _get_first_device(api, config):
    """Initialize the API client and return (device_id, device_data)."""
    await api.initialize()

    fallback = _build_fallback_device(config)
    devices = await api.get_devices(fallback_device=fallback)

    if not devices:
        logger.error("No sauna devices found.")
        return None, None

    device = devices[0]
    device_id = device["id"]
    data = await api.get_device_data(device_id)
    return device_id, data


# ── subcommands ──────────────────────────────────────────────────────

async def _cmd_status(args):
    """Connect to the API, print sauna state, disconnect."""
    from .api import HarviaSaunaAPI

    config = get_config(args.config)
    if not config:
        return 1

    api = HarviaSaunaAPI(config["username"], config["password"])
    try:
        device_id, data = await _get_first_device(api, config)
        if device_id is None:
            return 1

        # The telemetry data uses "heatOn", fallback to "active"
        active = data.get("heatOn", data.get("active", False))
        active = bool(int(active))
        temp = data.get("temperature", "?")
        target = data.get("targetTemp", "?")
        humidity = data.get("humidity", "?")

        print(f"Power:       {'ON' if active else 'OFF'}")
        print(f"Temperature: {temp}\u00b0C")
        print(f"Target:      {target}\u00b0C")
        print(f"Humidity:    {humidity}%")

        return 0
    finally:
        await api.close()


async def _cmd_start(args):
    """Connect to the API, turn the sauna ON, disconnect."""
    from .api import HarviaSaunaAPI

    config = get_config(args.config)
    if not config:
        return 1

    api = HarviaSaunaAPI(config["username"], config["password"])
    try:
        device_id, data = await _get_first_device(api, config)
        if device_id is None:
            return 1

        print(f"Turning sauna ON (device {device_id})...")
        result = await api.device_mutation(device_id, {"active": 1})
        if result.get("success"):
            print("Sauna started.")
            return 0
        else:
            print(f"Failed to start sauna: {result.get('message', 'unknown error')}")
            return 1
    finally:
        await api.close()


async def _cmd_stop(args):
    """Connect to the API, turn the sauna OFF, disconnect."""
    from .api import HarviaSaunaAPI

    config = get_config(args.config)
    if not config:
        return 1

    api = HarviaSaunaAPI(config["username"], config["password"])
    try:
        device_id, data = await _get_first_device(api, config)
        if device_id is None:
            return 1

        print(f"Turning sauna OFF (device {device_id})...")
        result = await api.device_mutation(device_id, {"active": 0})
        if result.get("success"):
            print("Sauna stopped.")
            return 0
        else:
            print(f"Failed to stop sauna: {result.get('message', 'unknown error')}")
            return 1
    finally:
        await api.close()


async def _cmd_temp(args):
    """Connect to the API, set temperature, disconnect."""
    from .api import HarviaSaunaAPI

    config = get_config(args.config)
    if not config:
        return 1

    api = HarviaSaunaAPI(config["username"], config["password"])
    try:
        device_id, data = await _get_first_device(api, config)
        if device_id is None:
            return 1

        temp = args.value
        print(f"Setting temperature to {temp}\u00b0C (device {device_id})...")
        result = await api.device_mutation(device_id, {"targetTemp": temp})
        if result.get("success"):
            print(f"Temperature set to {temp}\u00b0C.")
            return 0
        else:
            print(f"Failed to set temperature: {result.get('message', 'unknown error')}")
            return 1
    finally:
        await api.close()


def _cmd_service(args):
    """Run the HomeKit bridge service (foreground, long-running)."""
    from .service import run_service

    # Re-setup logging with file logs for the long-running service
    setup_logging(debug=args.debug, file_logs=True)

    try:
        exit_code = asyncio.run(
            run_service(config_path=args.config, storage_path=args.storage)
        )
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
        sys.exit(0)


# ── main ─────────────────────────────────────────────────────────────

def main():
    # Shared flags available on every subcommand
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--debug", action="store_true", help="Enable debug logging")
    common.add_argument("--config", type=str, help="Path to configuration file")

    parser = argparse.ArgumentParser(
        prog="harvia-sauna",
        description="Control your Harvia sauna from the command line.",
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", parents=[common], help="Print current sauna state")

    # start (turn sauna on)
    sub.add_parser("start", parents=[common], help="Turn the sauna ON")

    # stop (turn sauna off)
    sub.add_parser("stop", parents=[common], help="Turn the sauna OFF")

    # temp
    temp_parser = sub.add_parser("temp", parents=[common], help="Set the target temperature")
    temp_parser.add_argument("value", type=int, help="Temperature in \u00b0C")

    # service (run HomeKit bridge)
    svc_parser = sub.add_parser("service", parents=[common], help="Run the HomeKit bridge service")
    svc_parser.add_argument("--storage", type=str, help="Path to storage directory")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # One-shot commands: only show warnings unless --debug is set
    is_service = args.command == "service"
    if is_service:
        setup_logging(debug=args.debug, file_logs=True)
    elif args.debug:
        setup_logging(debug=True, file_logs=False)
    else:
        # Quiet mode for one-shot commands — only errors
        logging.basicConfig(level=logging.ERROR)

    if args.command == "service":
        _cmd_service(args)
    elif args.command == "status":
        sys.exit(asyncio.run(_cmd_status(args)))
    elif args.command == "start":
        sys.exit(asyncio.run(_cmd_start(args)))
    elif args.command == "stop":
        sys.exit(asyncio.run(_cmd_stop(args)))
    elif args.command == "temp":
        sys.exit(asyncio.run(_cmd_temp(args)))
