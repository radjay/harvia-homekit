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
        """Get all devices for the user"""
        response = await self.endpoint("device", {"query": "query ListDevices {listDevices {items {id displayName type hwVersion swVersion connectionState active }}}"})
        if 'data' in response and 'listDevices' in response['data'] and 'items' in response['data']['listDevices']:
            return response['data']['listDevices']['items']
        return []
    
    async def get_device_data(self, device_id: str) -> dict:
        """Get data for a specific device"""
        response = await self.endpoint("data", {
            "query": "query GetLatestDeviceData($deviceId: ID!) {getLatestDeviceData(deviceId: $deviceId) {active deviceId fan humidity light moisture remoteStartEn remainingTime steamEn steamOn statusCodes targetRh targetTemp temperature timestamp}}",
            "variables": {"deviceId": device_id}
        })
        if 'data' in response and 'getLatestDeviceData' in response['data']:
            return response['data']['getLatestDeviceData']
        return {}
    
    async def device_mutation(self, device_id: str, payload: dict) -> dict:
        """Send a mutation to control a device"""
        mutation = {
            "query": "mutation UpdateDevice($deviceId: ID!, $input: UpdateDeviceInput!) {updateDevice(deviceId: $deviceId, input: $input) {active fan light moisture steamEn steamOn statusCodes targetRh targetTemp}}",
            "variables": {"deviceId": device_id, "input": payload}
        }
        return await self.endpoint("device", mutation) 