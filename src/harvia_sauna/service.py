"""HomeKit bridge service logic, extracted from the old main.py."""

import asyncio
import logging
import os
import signal
from pathlib import Path

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver

from .api import HarviaSaunaAPI
from .accessories.sauna import HarviaSaunaAccessory
from .config import get_config

logger = logging.getLogger("harvia_sauna")


def _fallback_device_from_config(config):
    """Build a fallback device dict from config values, or ``None``."""
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


async def find_sauna_devices(api, *, fallback_device=None):
    """Find all sauna devices available to the user."""
    from .device import HarviaDevice

    devices = []

    try:
        device_list = await api.get_devices(fallback_device=fallback_device)
        logger.info(f"Found {len(device_list)} devices")

        for device_data in device_list:
            device_id = device_data["id"]
            device_name = device_data.get("displayName", f"Sauna {device_id}")
            logger.info(f"Initializing device: {device_name} (ID: {device_id})")

            device = HarviaDevice(api, device_id, device_name)
            await device.initialize()
            devices.append(device)

    except Exception as e:
        logger.error(f"Error finding sauna devices: {e}")

    return devices


def setup_homekit_bridge(driver, sauna_devices):
    """Set up the HomeKit bridge with accessories."""
    bridge = Bridge(driver, "Harvia Sauna Bridge")

    for device in sauna_devices:
        logger.info(f"Adding accessory for {device.name}")
        sauna_accessory = HarviaSaunaAccessory(driver, device)
        bridge.add_accessory(sauna_accessory)

    driver.add_accessory(accessory=bridge)

    return bridge


async def run_service(*, config_path=None, storage_path=None):
    """Main async entry point for the HomeKit service.

    Returns an integer exit code.
    """
    config = get_config(config_path)
    if not config:
        logger.error("No valid configuration found. Exiting.")
        return 1

    storage_path = storage_path or os.path.expanduser("~/.homekit/harvia")
    try:
        Path(storage_path).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating storage directory: {e}")
        return 1

    api = HarviaSaunaAPI(config["username"], config["password"])

    try:
        logger.info("Initializing API connection")
        await api.initialize()

        logger.info("Searching for sauna devices")
        fallback = _fallback_device_from_config(config)
        sauna_devices = await find_sauna_devices(api, fallback_device=fallback)

        if not sauna_devices:
            logger.error("No sauna devices found. Exiting.")
            await api.close()
            return 1

        logger.info("Setting up HomeKit driver")

        driver = AccessoryDriver(
            port=51826,
            persist_file=os.path.join(storage_path, "harvia.state"),
            pincode=config.get("pin_code", "031-45-154").encode(),
        )

        setup_homekit_bridge(driver, sauna_devices)

        logger.info("Starting HomeKit service")
        signal.signal(signal.SIGTERM, lambda *_args: driver.stop())

        async def keep_alive():
            while True:
                try:
                    await api.checkAndRenewTokens()
                except Exception as e:
                    logger.error(f"Error in keep-alive: {e}")
                await asyncio.sleep(60 * 10)

        keep_alive_task = asyncio.create_task(keep_alive())

        await asyncio.get_running_loop().run_in_executor(None, driver.start)

        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass

        await api.close()

        logger.info("Service stopped")
        return 0

    except Exception as e:
        logger.error(f"Error in main application: {e}")
        await api.close()
        return 1
