from pycognito import Cognito
import boto3
import logging
import json
import re
import base64
import botocore.exceptions
import asyncio
import aiohttp
from urllib.parse import quote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("harvia_sauna")

# Constants
REGION = "eu-west-1"

class HarviaSaunaAPI:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.endpoints = None
        self.client = None
        self.token_data = None
        self.session = None
    
    async def initialize(self):
        """Initialize the API session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        await self.getEndpoints()
        await self.authenticate()
        return True

    async def close(self):
        """Close the API session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def getEndpoints(self):
        """Fetch endpoints from the Harvia cloud service"""
        logger.debug("Fetching endpoints.")

        if self.endpoints is None:
            self.endpoints = {}
            
            if self.session is None:
                self.session = aiohttp.ClientSession()
                
            endpoints = ["users", "device", "events", "data"]
            for endpoint in endpoints:
                url = f'https://prod.myharvia-cloud.net/{endpoint}/endpoint'
                logger.debug(f"Fetching endpoint: {url}")
                async with self.session.get(url) as response:
                    self.endpoints[endpoint] = await response.json()
                    data_string = json.dumps(self.endpoints[endpoint], indent=4)
                    logger.debug(f"Received data: {data_string}")

            logger.info("Endpoints successfully fetched and saved.")
        else:
            logger.info("Endpoints already exist and were not fetched.")
            data_string = json.dumps(self.endpoints, indent=4)
            logger.debug(f"Endpoint data: {data_string}")

        return self.endpoints

    async def authenticate(self):
        """Authenticate with the Harvia cloud service"""
        if self.token_data is not None:
            return True

        u = await self.getClient()
        logger.debug("Authenticating")
        logger.debug(f"Using username: {self.username} with password: {self.password}")

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: u.authenticate(password=self.password)
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Authentication failed: {str(e)}")
            return False

        self.token_data = {
            "access_token": u.access_token,
            "refresh_token": u.refresh_token,
            "id_token": u.id_token,
        }

        logger.info("Authentication successful, tokens saved.")
        data_string = json.dumps(self.token_data, indent=4)
        logger.debug(f"Token data: {data_string}")

        return True

    async def getClient(self) -> Cognito:
        """Get the Cognito client for authentication"""
        if self.client is None:
            endpoints = await self.getEndpoints()
            user_pool_id = endpoints["users"]["userPoolId"]
            client_id = endpoints["users"]["clientId"]
            id_token = endpoints["users"]["identityPoolId"]

            username = self.username
            loop = asyncio.get_event_loop()
            u = await loop.run_in_executor(
                None, 
                lambda: Cognito(
                    user_pool_id, 
                    client_id, 
                    username=username, 
                    user_pool_region=REGION, 
                    id_token=id_token
                )
            )
            self.client = u

        return self.client

    async def getAuthenticatedClient(self) -> Cognito:
        """Get an authenticated client"""
        client = await self.getClient()
        await self.authenticate()
        return client

    async def checkAndRenewTokens(self):
        """Check and renew tokens if needed"""
        client = await self.getAuthenticatedClient()
        current_id_token = self.token_data['id_token']
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: client.check_token(renew=True)
        )
        self.token_data = {
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "id_token": client.id_token,
        }

        if current_id_token != client.id_token:
            logger.debug(f"Token renewed! {current_id_token} != {client.id_token}")

    async def getIdToken(self) -> str:
        """Get the ID token for API requests"""
        await self.checkAndRenewTokens()
        return self.token_data['id_token']

    async def getHeaders(self) -> dict:
        """Get headers for API requests"""
        idToken = await self.getIdToken()
        headers = {
            'authorization': idToken
        }
        return headers

    async def endpoint(self, endpoint: str, query: dict) -> dict:
        """Make a request to an endpoint"""
        headers = await self.getHeaders()
        url = self.endpoints[endpoint]['endpoint']
        queryDump = json.dumps(query, indent=4)
        logger.debug(f"Endpoint request on '{url}':")
        logger.debug(f"\tQuery: {queryDump}")
        
        async with self.session.post(url, json=query, headers=headers) as response:
            data = await response.json()
            dataString = json.dumps(data, indent=4)
            logger.debug(f"\tReturned data: {dataString}")
            return data

    async def getWebsocketEndpoint(self, endpoint: str) -> dict:
        """Get a websocket endpoint"""
        endpoint = self.endpoints[endpoint]['endpoint']
        regex = r"^https:\/\/(.+)\.appsync-api\.(.+)\/graphql$"
        regexReplace = r"wss://\1.appsync-realtime-api.\2/graphql"
        regexReplaceHost = r"\1.appsync-api.\2"
        wssUrl = re.sub(regex, regexReplace, endpoint)
        host = re.sub(regex, regexReplaceHost, endpoint)
        return {'wssUrl': wssUrl, 'host': host}

    async def getWebsockUrlByEndpoint(self, endpoint) -> str:
        """Get a websocket URL for an endpoint"""
        websockEndpoint = await self.getWebsocketEndpoint(endpoint)
        id_token = await self.getIdToken()
        headerPayload = {"Authorization": id_token, "host": websockEndpoint['host']}
        data_string = str(json.dumps(headerPayload, indent=4))
        encoded_header = base64.b64encode(data_string.encode())
        wssUrl = websockEndpoint['wssUrl'] + '?header=' + quote(encoded_header.decode('utf-8')) + '&payload=e30='
        return wssUrl
    
    async def get_devices(self) -> list:
        """Get all sauna devices available to the user"""
        # The API has changed - try different query formats
        
        # Try to get devices using user query first
        try:
            logger.debug("Trying to get devices using 'user' query")
            response = await self.endpoint("users", {
                "query": "query GetUser { getUser { devices { id displayName type active connectionState } } }"
            })
            
            if 'data' in response and 'getUser' in response['data'] and response['data']['getUser'] and 'devices' in response['data']['getUser']:
                devices = response['data']['getUser']['devices']
                logger.info(f"Found {len(devices)} devices using user query")
                return devices
        except Exception as e:
            logger.warning(f"Error getting devices via user query: {str(e)}")
        
        # Try alternative queries if the first approach failed
        try:
            logger.debug("Trying to get devices using 'listDevices' query")
            response = await self.endpoint("device", {
                "query": "query ListDevices {listDevices {items {id displayName type hwVersion swVersion connectionState active }}}"
            })
            
            if 'data' in response and 'listDevices' in response['data'] and 'items' in response['data']['listDevices']:
                devices = response['data']['listDevices']['items']
                logger.info(f"Found {len(devices)} devices using listDevices query")
                return devices
        except Exception as e:
            logger.warning(f"Error getting devices via listDevices query: {str(e)}")
            
        # Try another alternative approach - list the user's assigned devices
        try:
            logger.debug("Trying to get devices using 'getAssignedDevices' query")
            response = await self.endpoint("device", {
                "query": "query GetAssignedDevices {getAssignedDevices {id displayName type active connectionState}}"
            })
            
            if 'data' in response and 'getAssignedDevices' in response['data']:
                devices = response['data']['getAssignedDevices']
                logger.info(f"Found {len(devices)} devices using getAssignedDevices query")
                return devices
        except Exception as e:
            logger.warning(f"Error getting devices via getAssignedDevices query: {str(e)}")
        
        # If we can't find devices via API, ask user to provide device ID
        logger.warning("Could not find devices through API queries. Will try manual device ID from config")
        
        from pathlib import Path
        import os
        
        # Try to read from config file
        config_paths = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.json'),
            os.path.expanduser('~/.config/harvia-homekit/config.json'),
            '/etc/harvia-homekit/config.json'
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        if 'device_id' in config and config['device_id']:
                            device_id = config['device_id']
                            device_name = config.get('device_name', f'Sauna {device_id}')
                            logger.info(f"Using manually configured device ID: {device_id}")
                            return [{
                                'id': device_id,
                                'displayName': device_name,
                                'type': 'XENIO',
                                'active': False,
                                'connectionState': 'UNKNOWN'
                            }]
                except Exception as e:
                    logger.warning(f"Error reading config file {config_path}: {str(e)}")
        
        # If no devices found, return empty list
        logger.error("No devices found. Please add a device_id to your config.json file.")
        return []
    
    async def get_device_data(self, device_id: str) -> dict:
        """Get data for a specific device"""
        try:
            response = await self.endpoint("data", {
                "query": "query GetLatestDeviceData($deviceId: ID!) {getLatestDeviceData(deviceId: $deviceId) {active deviceId fan humidity light moisture remoteStartEn remainingTime steamEn steamOn statusCodes targetRh targetTemp temperature timestamp}}",
                "variables": {"deviceId": device_id}
            })
            
            if 'data' in response and 'getLatestDeviceData' in response['data']:
                return response['data']['getLatestDeviceData']
            
            logger.warning(f"No data found for device {device_id}. Response: {json.dumps(response)}")
            
            # Return default data if we couldn't get actual data
            return {
                'deviceId': device_id,
                'active': False,
                'light': False,
                'fan': False,
                'steamEn': False,
                'targetTemp': 60,
                'targetRh': 30,
                'temperature': 25,
                'humidity': 30,
                'statusCodes': "000"
            }
            
        except Exception as e:
            logger.error(f"Error getting device data: {str(e)}")
            return {}
    
    async def device_mutation(self, device_id: str, payload: dict) -> dict:
        """Send a mutation to control a device"""
        mutation = {
            "query": "mutation UpdateDevice($deviceId: ID!, $input: UpdateDeviceInput!) {updateDevice(deviceId: $deviceId, input: $input) {active fan light moisture steamEn steamOn statusCodes targetRh targetTemp}}",
            "variables": {"deviceId": device_id, "input": payload}
        }
        return await self.endpoint("device", mutation) 