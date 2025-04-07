#!/usr/bin/env python3
import asyncio
from pyhap_harvia.api import HarviaSaunaAPI
import json

async def set_temp():
    # Load credentials from config.json
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Create API client
    api = HarviaSaunaAPI(config['username'], config['password'])
    
    # Initialize API
    await api.initialize()
    
    # Set temperature
    device_id = config['device_id']
    temp = 70  # Set temperature to 70°C
    
    print(f'Setting temperature to {temp}°C for device {device_id}')
    
    # Create payload
    payload = {'targetTemp': temp}
    
    # Send mutation
    result = await api.device_mutation(device_id, payload)
    
    print(f'Mutation result: {json.dumps(result, indent=2)}')
    
    # Close API
    await api.close()

if __name__ == "__main__":
    asyncio.run(set_temp()) 