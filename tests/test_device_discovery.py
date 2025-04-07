#!/usr/bin/env python3
import asyncio
from pyhap_harvia.api import HarviaSaunaAPI
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_device_discovery")

async def discover_devices():
    # Load credentials from config.json
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Create API client
    api = HarviaSaunaAPI(config['username'], config['password'])
    
    # Initialize API
    await api.initialize()
    
    logger.info('Testing device discovery methods...')
    
    # Method 1: getDeviceTree (HA plugin approach)
    logger.info("Method 1: Testing getDeviceTree approach from Home Assistant plugin")
    try:
        query = {
            "operationName": "Query",
            "variables": {},
            "query": 'query Query {\n  getDeviceTree\n}\n'
        }
        
        response = await api.endpoint('device', query)
        
        if 'data' in response and 'getDeviceTree' in response['data']:
            devices_tree_data = json.loads(response['data']['getDeviceTree'])
            logger.info(f"Device tree data: {json.dumps(devices_tree_data, indent=2)}")
            
            if devices_tree_data:
                devices = devices_tree_data[0]['c']
                logger.info(f"Found {len(devices)} devices in the device tree")
                
                for device in devices:
                    device_id = device['i']['name']
                    logger.info(f"Found device: {device_id}")
                    
                    # Now try to get device data from both endpoints
                    try:
                        # Get device data
                        device_data = await api.get_device_data(device_id)
                        logger.info(f"Device data for {device_id}: {json.dumps(device_data, indent=2)}")
                    except Exception as e:
                        logger.error(f"Failed to get device data: {str(e)}")
            else:
                logger.error("No devices found in the getDeviceTree response")
        else:
            logger.error("Unexpected structure in getDeviceTree response")
    except Exception as e:
        logger.error(f"Error testing getDeviceTree approach: {str(e)}")
    
    # Method 2: getDevices
    logger.info("\nMethod 2: Testing our existing get_devices methods")
    try:
        devices = await api.get_devices()
        logger.info(f"Found {len(devices)} devices using get_devices")
        logger.info(f"Devices: {json.dumps(devices, indent=2)}")
        
        for device in devices:
            device_id = device['id']
            logger.info(f"Testing device data for {device_id}")
            
            try:
                device_data = await api.get_device_data(device_id)
                logger.info(f"Device data: {json.dumps(device_data, indent=2)}")
            except Exception as e:
                logger.error(f"Failed to get device data: {str(e)}")
    except Exception as e:
        logger.error(f"Error testing get_devices methods: {str(e)}")
    
    # Method 3: Get organization ID and user info
    logger.info("\nMethod 3: Testing user data and organization ID")
    try:
        user_data = await api.get_user_data()
        logger.info(f"User data: {json.dumps(user_data, indent=2)}")
        
        org_id = await api.get_organization_id()
        logger.info(f"Organization ID: {org_id}")
    except Exception as e:
        logger.error(f"Error getting user data: {str(e)}")
    
    # Close API
    await api.close()

if __name__ == "__main__":
    asyncio.run(discover_devices()) 