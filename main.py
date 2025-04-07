#!/usr/bin/env python3
"""
Main module for the Harvia Sauna HomeKit service.
This script connects to Harvia Cloud API and creates a HomeKit bridge with accessories for the sauna.
"""

import os
import sys
import json
import signal
import asyncio
import logging
import argparse
from pathlib import Path

from pyhap.accessory import Bridge
from pyhap.accessory_driver import AccessoryDriver
import pyhap.loader as loader

from pyhap_harvia.api import HarviaSaunaAPI
from pyhap_harvia.device import HarviaDevice
from pyhap_harvia.accessories.sauna import HarviaSaunaAccessory

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("harvia_sauna")

# Set higher log level for some noisy libraries
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('pyhap').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

async def find_sauna_devices(api):
    """Find all sauna devices available to the user"""
    devices = []
    
    try:
        # Get the list of devices from the API
        device_list = await api.get_devices()
        logger.info(f"Found {len(device_list)} devices")
        
        for device_data in device_list:
            device_id = device_data['id']
            device_name = device_data.get('displayName', f'Sauna {device_id}')
            logger.info(f"Initializing device: {device_name} (ID: {device_id})")
            
            # Create a device object
            device = HarviaDevice(api, device_id, device_name)
            await device.initialize()
            devices.append(device)
    
    except Exception as e:
        logger.error(f"Error finding sauna devices: {str(e)}")
    
    return devices

def get_config(config_path=None):
    """Load configuration from file"""
    if config_path is None:
        # Use default paths
        default_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json'),
            os.path.expanduser('~/.config/harvia-homekit/config.json'),
            '/etc/harvia-homekit/config.json'
        ]
        
        for path in default_paths:
            if os.path.exists(path):
                config_path = path
                break
        
        if config_path is None:
            logger.error("No configuration file found")
            return None
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return None

def setup_homekit_bridge(driver, sauna_devices):
    """Set up the HomeKit bridge with accessories"""
    # Create a bridge to add all accessories to
    bridge = Bridge(driver, 'Harvia Sauna Bridge')
    
    # Add each sauna device as an accessory
    for device in sauna_devices:
        logger.info(f"Adding accessory for {device.name}")
        sauna_accessory = HarviaSaunaAccessory(driver, device)
        bridge.add_accessory(sauna_accessory)
    
    # Add the bridge to the driver
    driver.add_accessory(accessory=bridge)
    
    return bridge

def create_storage_dir(path):
    """Create storage directory if it doesn't exist"""
    try:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Error creating storage directory: {str(e)}")
        return False

async def main_async(args):
    """Main async entry point"""
    # Load configuration
    config = get_config(args.config)
    if not config:
        logger.error("No valid configuration found. Exiting.")
        return 1
    
    # Create storage directory
    storage_path = args.storage or os.path.expanduser('~/.homekit/harvia')
    if not create_storage_dir(storage_path):
        logger.error("Failed to create storage directory. Exiting.")
        return 1
    
    # Create API client
    api = HarviaSaunaAPI(config['username'], config['password'])
    
    try:
        # Initialize API
        logger.info("Initializing API connection")
        await api.initialize()
        
        # Find sauna devices
        logger.info("Searching for sauna devices")
        sauna_devices = await find_sauna_devices(api)
        
        if not sauna_devices:
            logger.error("No sauna devices found. Exiting.")
            await api.close()
            return 1
        
        # Set up the HomeKit driver
        logger.info("Setting up HomeKit driver")
        
        # Create the accessory driver
        driver = AccessoryDriver(
            port=51826,
            persist_file=os.path.join(storage_path, 'harvia.state'),
            pincode=config.get('pin_code', '031-45-154'),
            display_name=config.get('service_name', 'Harvia Sauna')
        )
        
        # Set up the bridge with accessories
        bridge = setup_homekit_bridge(driver, sauna_devices)
        
        # Start the driver
        logger.info("Starting HomeKit service")
        signal.signal(signal.SIGTERM, lambda *args: driver.stop())
        
        # Create a task to keep the API session alive
        async def keep_alive():
            while True:
                try:
                    await api.checkAndRenewTokens()
                except Exception as e:
                    logger.error(f"Error in keep-alive: {str(e)}")
                await asyncio.sleep(60 * 10)  # Check every 10 minutes
        
        keep_alive_task = asyncio.create_task(keep_alive())
        
        # Start the driver (this will block until driver.stop() is called)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, driver.start)
        
        # Clean up
        keep_alive_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
        
        # Close the API
        await api.close()
        
        logger.info("Service stopped")
        return 0
    
    except Exception as e:
        logger.error(f"Error in main application: {str(e)}")
        await api.close()
        return 1

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Harvia Sauna HomeKit Integration')
    parser.add_argument('--config', type=str, help='Path to configuration file')
    parser.add_argument('--storage', type=str, help='Path to storage directory')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger('pyhap').setLevel(logging.INFO)
    
    try:
        loop = asyncio.get_event_loop()
        exit_code = loop.run_until_complete(main_async(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        sys.exit(1)

if __name__ == '__main__':
    main() 