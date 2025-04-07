#!/usr/bin/env python3
"""
Test script for testing temperature setting with the Harvia API.
This helps verify that our fix for the timeout issue is working.
"""

import asyncio
import json
import logging
import os
import sys

from pyhap_harvia.api import HarviaSaunaAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_temp")

async def main():
    """Main test function"""
    # Load configuration
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Extract credentials and device ID
    username = config['username']
    password = config['password']
    device_id = config['device_id']
    
    if not device_id:
        logger.error("No device ID specified in config.json")
        return 1
    
    # Create API client
    api = HarviaSaunaAPI(username, password)
    
    try:
        # Initialize API
        logger.info("Initializing API connection")
        await api.initialize()
        
        # Test mutation: set temperature
        target_temp = 85
        logger.info(f"Testing 'set temperature to {target_temp}°C' mutation")
        result = await api.device_mutation(device_id, {'targetTemp': target_temp})
        logger.info(f"Set temperature mutation result: {json.dumps(result)}")
        
        # Close the API
        await api.close()
        
        logger.info("Test completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
        await api.close()
        return 1

if __name__ == "__main__":
    asyncio.run(main()) 