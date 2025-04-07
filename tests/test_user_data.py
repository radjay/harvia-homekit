#!/usr/bin/env python3
import asyncio
from pyhap_harvia.api import HarviaSaunaAPI
import json

async def get_user_data():
    # Load credentials from config.json
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Create API client
    api = HarviaSaunaAPI(config['username'], config['password'])
    
    # Initialize API
    await api.initialize()
    
    print('Getting user data...')
    
    # Get user data
    user_data = await api.get_user_data()
    
    print(f'User data result: {json.dumps(user_data, indent=2)}')
    
    # Get organization ID
    org_id = await api.get_organization_id()
    print(f'Organization ID: {org_id}')
    
    # Close API
    await api.close()

if __name__ == "__main__":
    asyncio.run(get_user_data()) 