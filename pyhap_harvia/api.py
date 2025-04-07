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
from datetime import datetime
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("harvia_sauna")

# Set up dedicated API logger for full request/response logging
api_logger = logging.getLogger("harvia_api")
api_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
os.makedirs('/tmp/harvia-homekit', exist_ok=True)

# Add file handler for API logs
api_log_file = '/tmp/harvia-homekit/api.log'
api_file_handler = logging.FileHandler(api_log_file)
api_file_handler.setLevel(logging.DEBUG)
api_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
api_file_handler.setFormatter(api_formatter)
api_logger.addHandler(api_file_handler)

# Add stdout handler for API logs during development
api_stdout_handler = logging.StreamHandler()
api_stdout_handler.setLevel(logging.INFO)
api_stdout_handler.setFormatter(api_formatter)
api_logger.addHandler(api_stdout_handler)

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
            logger.info("Using existing authentication tokens")
            return True

        u = await self.getClient()
        logger.info("Authenticating with Harvia cloud service")
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
        # Log a short portion of the token to verify in logs
        token_preview = self.token_data['id_token'][:20] + "..." if self.token_data['id_token'] else "None"
        logger.info(f"Token received (preview): {token_preview}")
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
        # Generate a unique request ID for correlation
        request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{endpoint}"
        
        headers = await self.getHeaders()
        url = self.endpoints[endpoint]['endpoint']
        queryDump = json.dumps(query, indent=4)
        
        # Log the request with the unique ID
        api_logger.debug(f"=== API REQUEST {request_id} ===")
        api_logger.debug(f"Endpoint: {url}")
        api_logger.debug(f"Headers: {headers}")
        api_logger.debug(f"Query: {queryDump}")
        
        logger.debug(f"Endpoint request on '{url}':")
        logger.debug(f"\tQuery: {queryDump}")
        
        try:
            async with self.session.post(url, json=query, headers=headers) as response:
                data = await response.json()
                dataString = json.dumps(data, indent=4)
                
                # Log the response with the same unique ID
                api_logger.debug(f"=== API RESPONSE {request_id} ===")
                api_logger.debug(f"Status: {response.status}")
                api_logger.debug(f"Response: {dataString}")
                
                # Log a summary for info level
                if 'errors' in data:
                    error_msg = data['errors'][0]['message'] if data['errors'] else "Unknown error"
                    api_logger.info(f"API Error {request_id}: {error_msg}")
                    logger.warning(f"API Error in {endpoint}: {error_msg}")
                else:
                    api_logger.info(f"API Success {request_id}: {endpoint} request completed")
                
                logger.debug(f"\tReturned data: {dataString}")
                return data
        except Exception as e:
            api_logger.error(f"=== API EXCEPTION {request_id} ===")
            api_logger.error(f"Error: {str(e)}")
            logger.error(f"API request error: {str(e)}")
            raise

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
            logger.info(f"Fetching current device data for device ID: {device_id}")
            
            # Create default data
            default_data = {
                'deviceId': device_id,
                'active': False,
                'light': False,
                'fan': False,
                'steamEn': False,
                'targetTemp': 60,
                'targetRh': 30,
                'temperature': 20,  # Set to more realistic room temperature
                'humidity': 30,
                'statusCodes': "000"
            }
            
            # Try the Home Assistant plugin's query format for getLatestData
            try:
                query = {
                    "operationName": "Query",
                    "variables": {
                        "deviceId": device_id
                    },
                    "query": "query Query($deviceId: String!) {\n  getLatestData(deviceId: $deviceId) {\n    deviceId\n    timestamp\n    sessionId\n    type\n    data\n    __typename\n  }\n}\n"
                }
                
                logger.info(f"Trying Home Assistant plugin's getLatestData query format")
                response = await self.endpoint("data", query)
                
                # Extra safety checks for None or malformed responses
                if not response:
                    logger.warning(f"Received None response from API for device {device_id}")
                    logger.warning(f"Using default device data: {json.dumps(default_data)}")
                    return default_data
                    
                if 'data' in response and response['data'] and 'getLatestData' in response['data'] and response['data']['getLatestData']:
                    data_str = response['data']['getLatestData']['data']
                    data = json.loads(data_str)
                    # Add additional metadata
                    data['deviceId'] = device_id
                    data['timestamp'] = response['data']['getLatestData']['timestamp']
                    data['type'] = response['data']['getLatestData']['type']
                    
                    logger.info(f"Device data retrieved successfully: temperature={data.get('temperature', 'N/A')}°C, active={data.get('active', 'N/A')}")
                    logger.info(f"Complete device data: {json.dumps(data)}")
                    return data
                else:
                    logger.warning(f"Unexpected API response format for device {device_id}: {json.dumps(response)}")
            except Exception as inner_e:
                logger.error(f"Error fetching device data with getLatestData: {str(inner_e)}")
            
            # If the first approach failed, try the get_device approach
            try:
                query = {
                    "operationName": "Query",
                    "variables": {
                        "deviceId": device_id
                    },
                    "query": "query Query($deviceId: ID!) {\n  getDeviceState(deviceId: $deviceId) {\n    desired\n    reported\n    timestamp\n    __typename\n  }\n}\n"
                }
                
                logger.info(f"Trying getDeviceState query format")
                response = await self.endpoint("device", query)
                
                if 'data' in response and response['data'] and 'getDeviceState' in response['data'] and response['data']['getDeviceState'] and 'reported' in response['data']['getDeviceState']:
                    data_str = response['data']['getDeviceState']['reported']
                    data = json.loads(data_str)
                    # Add timestamp
                    data['timestamp'] = response['data']['getDeviceState']['timestamp']
                    
                    logger.info(f"Device state retrieved successfully")
                    logger.info(f"Complete device state: {json.dumps(data)}")
                    return data
                else:
                    logger.warning(f"Unexpected API response format for getDeviceState: {json.dumps(response)}")
            except Exception as inner_e:
                logger.error(f"Error fetching device state: {str(inner_e)}")
            
            # If all approaches failed, return default data
            logger.warning(f"No valid data found for device {device_id}, using defaults")
            logger.warning(f"Using default device data: {json.dumps(default_data)}")
            return default_data
            
        except Exception as e:
            logger.error(f"Error getting device data: {str(e)}")
            # Return basic default data even in case of error
            default_data = {
                'deviceId': device_id,
                'active': False,
                'targetTemp': 60,
                'temperature': 20,
            }
            logger.warning(f"Using minimal default data after error: {json.dumps(default_data)}")
            return default_data
    
    async def device_mutation(self, device_id: str, payload: dict) -> dict:
        """Send a mutation to control a device"""
        # Generate a unique request ID for correlation
        request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-device-{device_id}"
        
        # Convert payload to string format as expected by the API
        payload_string = json.dumps(payload, indent=4)
        
        # Create the GraphQL mutation in the format used by Home Assistant
        mutation = {
            "operationName": "Mutation",
            "variables": {
                "deviceId": device_id,
                "state": payload_string,
                "getFullState": False
            },
            "query": "mutation Mutation($deviceId: ID!, $state: AWSJSON!, $getFullState: Boolean) {\n  requestStateChange(deviceId: $deviceId, state: $state, getFullState: $getFullState)\n}\n"
        }
        
        # Log the mutation details to the dedicated API log
        api_logger.debug(f"=== DEVICE MUTATION REQUEST {request_id} ===")
        api_logger.debug(f"Device ID: {device_id}")
        api_logger.debug(f"Payload: {payload_string}")
        api_logger.debug(f"Full Mutation: {json.dumps(mutation, indent=4)}")
        
        # Attempt the mutation with retries
        max_retries = 3
        retry_delay = 1  # Start with 1 second delay
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending device control mutation (attempt {attempt+1}/{max_retries}): {json.dumps(payload)}")
                api_logger.info(f"Attempt {attempt+1}/{max_retries} for mutation {request_id}")
                
                # Try to authenticate before each attempt
                try:
                    auth_success = await self.authenticate()
                    if not auth_success:
                        logger.warning("Authentication unsuccessful, but continuing with request")
                except Exception as auth_error:
                    logger.error(f"Authentication error before mutation: {str(auth_error)}")
                    api_logger.error(f"Authentication error before mutation {request_id}: {str(auth_error)}")
                    # Continue anyway in case we have valid tokens
                
                # Get headers for the request
                headers = await self.getHeaders()
                url = self.endpoints["device"]['endpoint']
                
                # Create a ClientTimeout with generous timeouts
                # This replaces the default timeout behavior
                timeout = aiohttp.ClientTimeout(
                    total=30,      # 30 second total timeout
                    connect=10,    # 10 seconds to establish connection
                    sock_read=20,  # 20 seconds to read response
                    sock_connect=10 # 10 seconds to connect to socket
                )
                
                # Use a new ClientSession with the custom timeout for just this request
                # This avoids timeout context manager issues
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url, 
                        json=mutation, 
                        headers=headers
                    ) as response:
                        data = await response.json()
                        
                        # Log the response
                        api_logger.debug(f"=== DEVICE MUTATION RESPONSE {request_id} ===")
                        api_logger.debug(f"Status: {response.status}")
                        api_logger.debug(f"Response: {json.dumps(data, indent=4)}")
                
                # Check if the response contains errors
                if 'errors' in data:
                    error_msg = data['errors'][0]['message'] if data['errors'] else "Unknown error"
                    logger.error(f"API error in mutation response: {error_msg}")
                    api_logger.error(f"Mutation error {request_id}: {error_msg}")
                    
                    # If we get an authentication error, try to re-authenticate
                    if 'Unauthorized' in error_msg or 'Authentication' in error_msg:
                        logger.info("Auth error detected, re-authenticating...")
                        api_logger.info(f"Auth error in {request_id}, re-authenticating...")
                        await self.authenticate()
                    
                    # Continue with retry
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                
                # Log the successful response
                logger.info(f"Mutation response: {json.dumps(data)}")
                api_logger.info(f"Mutation {request_id} successful")
                
                # Return the result
                return {
                    "success": True,
                    "data": data
                }
            
            except Exception as e:
                logger.error(f"Error in device mutation (attempt {attempt+1}/{max_retries}): {str(e)}")
                api_logger.error(f"Error in mutation {request_id} (attempt {attempt+1}/{max_retries}): {str(e)}")
                
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    api_logger.info(f"Retrying mutation {request_id} in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("All mutation attempts failed")
                    api_logger.error(f"All attempts for mutation {request_id} failed")
                    return {"success": False, "message": f"Error: {str(e)}"}
        
        # If we exhausted all retries
        logger.error("Failed to send device command after max retries")
        api_logger.error(f"Failed to send mutation {request_id} after max retries")
        return {"success": False, "message": "Failed to send command after multiple attempts"}

    async def get_user_data(self):
        """Get current user data including organization ID"""
        try:
            logger.info("Fetching user data to get organization ID")
            api_logger.info("Fetching user data to get organization ID")
            
            query = {
                "operationName": "Query",
                "variables": {},
                "query": "query Query {\n  getCurrentUserDetails {\n    email\n    organizationId\n    admin\n    given_name\n    family_name\n    superAdmin\n    rdUser\n    appSettings\n    __typename\n  }\n}\n"
            }
            
            response = await self.endpoint("users", query)
            
            if 'data' in response and 'getCurrentUserDetails' in response['data']:
                user_data = response['data']['getCurrentUserDetails']
                organization_id = user_data.get('organizationId')
                email = user_data.get('email')
                
                logger.info(f"User data retrieved. Organization ID: {organization_id}, Email: {email}")
                api_logger.info(f"User data retrieved. Organization ID: {organization_id}, Email: {email}")
                
                return user_data
            else:
                logger.warning("Failed to get user data")
                api_logger.warning("Failed to get user data")
                return None
        except Exception as e:
            logger.error(f"Error getting user data: {str(e)}")
            api_logger.error(f"Error getting user data: {str(e)}")
            return None
            
    async def get_organization_id(self):
        """Get the organization ID for the current user"""
        user_data = await self.get_user_data()
        if user_data and 'organizationId' in user_data:
            return user_data['organizationId']
        return None 