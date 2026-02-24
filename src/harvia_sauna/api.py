"""Harvia Cloud API client."""

import asyncio
import base64
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote

import aiohttp
import botocore.exceptions
from pycognito import Cognito

logger = logging.getLogger("harvia_sauna")
api_logger = logging.getLogger("harvia_api")

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
        """Initialize the API session."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        await self.getEndpoints()
        await self.authenticate()
        return True

    async def close(self):
        """Close the API session."""
        if self.session:
            await self.session.close()
            self.session = None

    async def getEndpoints(self):
        """Fetch endpoints from the Harvia cloud service."""
        logger.debug("Fetching endpoints.")

        if self.endpoints is None:
            self.endpoints = {}

            if self.session is None:
                self.session = aiohttp.ClientSession()

            endpoints = ["users", "device", "events", "data"]
            for endpoint in endpoints:
                url = f"https://prod.myharvia-cloud.net/{endpoint}/endpoint"
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
        """Authenticate with the Harvia cloud service."""
        if self.token_data is not None:
            logger.info("Using existing authentication tokens")
            return True

        u = await self.getClient()
        logger.info("Authenticating with Harvia cloud service")
        logger.debug(f"Using username: {self.username} with password: {self.password}")

        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: u.authenticate(password=self.password)
            )
        except botocore.exceptions.ClientError as e:
            logger.error(f"Authentication failed: {e}")
            return False

        self.token_data = {
            "access_token": u.access_token,
            "refresh_token": u.refresh_token,
            "id_token": u.id_token,
        }

        logger.info("Authentication successful, tokens saved.")
        token_preview = (
            self.token_data["id_token"][:20] + "..."
            if self.token_data["id_token"]
            else "None"
        )
        logger.info(f"Token received (preview): {token_preview}")
        return True

    async def getClient(self) -> Cognito:
        """Get the Cognito client for authentication."""
        if self.client is None:
            endpoints = await self.getEndpoints()
            user_pool_id = endpoints["users"]["userPoolId"]
            client_id = endpoints["users"]["clientId"]
            id_token = endpoints["users"]["identityPoolId"]

            username = self.username
            u = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: Cognito(
                    user_pool_id,
                    client_id,
                    username=username,
                    user_pool_region=REGION,
                    id_token=id_token,
                ),
            )
            self.client = u

        return self.client

    async def getAuthenticatedClient(self) -> Cognito:
        """Get an authenticated client."""
        client = await self.getClient()
        await self.authenticate()
        return client

    async def checkAndRenewTokens(self):
        """Check and renew tokens if needed."""
        client = await self.getAuthenticatedClient()
        current_id_token = self.token_data["id_token"]
        await asyncio.get_running_loop().run_in_executor(
            None, lambda: client.check_token(renew=True)
        )
        self.token_data = {
            "access_token": client.access_token,
            "refresh_token": client.refresh_token,
            "id_token": client.id_token,
        }

        if current_id_token != client.id_token:
            logger.debug(
                f"Token renewed! {current_id_token} != {client.id_token}"
            )

    async def getIdToken(self) -> str:
        """Get the ID token for API requests."""
        await self.checkAndRenewTokens()
        return self.token_data["id_token"]

    async def getHeaders(self) -> dict:
        """Get headers for API requests."""
        idToken = await self.getIdToken()
        return {"authorization": idToken}

    async def endpoint(self, endpoint: str, query: dict) -> dict:
        """Make a request to an endpoint."""
        request_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{endpoint}"

        headers = await self.getHeaders()
        url = self.endpoints[endpoint]["endpoint"]
        queryDump = json.dumps(query, indent=4)

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

                api_logger.debug(f"=== API RESPONSE {request_id} ===")
                api_logger.debug(f"Status: {response.status}")
                api_logger.debug(f"Response: {dataString}")

                if "errors" in data:
                    error_msg = (
                        data["errors"][0]["message"]
                        if data["errors"]
                        else "Unknown error"
                    )
                    api_logger.info(f"API Error {request_id}: {error_msg}")
                    logger.warning(f"API Error in {endpoint}: {error_msg}")
                else:
                    api_logger.info(
                        f"API Success {request_id}: {endpoint} request completed"
                    )

                logger.debug(f"\tReturned data: {dataString}")
                return data
        except Exception as e:
            api_logger.error(f"=== API EXCEPTION {request_id} ===")
            api_logger.error(f"Error: {e}")
            logger.error(f"API request error: {e}")
            raise

    async def getWebsocketEndpoint(self, endpoint: str) -> dict:
        """Get a websocket endpoint."""
        endpoint = self.endpoints[endpoint]["endpoint"]
        regex = r"^https:\/\/(.+)\.appsync-api\.(.+)\/graphql$"
        regexReplace = r"wss://\1.appsync-realtime-api.\2/graphql"
        regexReplaceHost = r"\1.appsync-api.\2"
        wssUrl = re.sub(regex, regexReplace, endpoint)
        host = re.sub(regex, regexReplaceHost, endpoint)
        return {"wssUrl": wssUrl, "host": host}

    async def getWebsockUrlByEndpoint(self, endpoint) -> str:
        """Get a websocket URL for an endpoint."""
        websockEndpoint = await self.getWebsocketEndpoint(endpoint)
        id_token = await self.getIdToken()
        headerPayload = {
            "Authorization": id_token,
            "host": websockEndpoint["host"],
        }
        data_string = str(json.dumps(headerPayload, indent=4))
        encoded_header = base64.b64encode(data_string.encode())
        wssUrl = (
            websockEndpoint["wssUrl"]
            + "?header="
            + quote(encoded_header.decode("utf-8"))
            + "&payload=e30="
        )
        return wssUrl

    async def get_devices(self, *, fallback_device=None) -> list:
        """Get all sauna devices available to the user.

        Parameters
        ----------
        fallback_device : dict | None
            If all API queries fail and *fallback_device* is provided, return
            it wrapped in a list.  The caller can build this from config values.
        """
        # Try user query
        try:
            logger.debug("Trying to get devices using 'user' query")
            response = await self.endpoint(
                "users",
                {
                    "query": "query GetUser { getUser { devices { id displayName type active connectionState } } }"
                },
            )

            if (
                "data" in response
                and "getUser" in response["data"]
                and response["data"]["getUser"]
                and "devices" in response["data"]["getUser"]
            ):
                devices = response["data"]["getUser"]["devices"]
                logger.info(f"Found {len(devices)} devices using user query")
                return devices
        except Exception as e:
            logger.debug(f"Error getting devices via user query: {e}")

        # Try listDevices
        try:
            logger.debug("Trying to get devices using 'listDevices' query")
            response = await self.endpoint(
                "device",
                {
                    "query": "query ListDevices {listDevices {items {id displayName type hwVersion swVersion connectionState active }}}"
                },
            )

            if (
                "data" in response
                and "listDevices" in response["data"]
                and "items" in response["data"]["listDevices"]
            ):
                devices = response["data"]["listDevices"]["items"]
                logger.info(f"Found {len(devices)} devices using listDevices query")
                return devices
        except Exception as e:
            logger.debug(f"Error getting devices via listDevices query: {e}")

        # Try getAssignedDevices
        try:
            logger.debug("Trying to get devices using 'getAssignedDevices' query")
            response = await self.endpoint(
                "device",
                {
                    "query": "query GetAssignedDevices {getAssignedDevices {id displayName type active connectionState}}"
                },
            )

            if (
                "data" in response
                and "getAssignedDevices" in response["data"]
            ):
                devices = response["data"]["getAssignedDevices"]
                logger.info(
                    f"Found {len(devices)} devices using getAssignedDevices query"
                )
                return devices
        except Exception as e:
            logger.debug(f"Error getting devices via getAssignedDevices query: {e}")

        # Fallback to caller-provided device
        if fallback_device:
            logger.info(f"Using manually configured device ID: {fallback_device['id']}")
            return [fallback_device]

        logger.error(
            "No devices found. Please add a device_id to your config.json file."
        )
        return []

    async def get_device_data(self, device_id: str) -> dict:
        """Get data for a specific device."""
        try:
            logger.info(f"Fetching current device data for device ID: {device_id}")

            default_data = {
                "deviceId": device_id,
                "active": False,
                "light": False,
                "fan": False,
                "steamEn": False,
                "targetTemp": 60,
                "targetRh": 30,
                "temperature": 20,
                "humidity": 30,
                "statusCodes": "000",
            }

            # Try getLatestData
            try:
                query = {
                    "operationName": "Query",
                    "variables": {"deviceId": device_id},
                    "query": "query Query($deviceId: String!) {\n  getLatestData(deviceId: $deviceId) {\n    deviceId\n    timestamp\n    sessionId\n    type\n    data\n    __typename\n  }\n}\n",
                }

                logger.info("Trying Home Assistant plugin's getLatestData query format")
                response = await self.endpoint("data", query)

                if not response:
                    logger.warning(
                        f"Received None response from API for device {device_id}"
                    )
                    logger.warning(
                        f"Using default device data: {json.dumps(default_data)}"
                    )
                    return default_data

                if (
                    "data" in response
                    and response["data"]
                    and "getLatestData" in response["data"]
                    and response["data"]["getLatestData"]
                ):
                    data_str = response["data"]["getLatestData"]["data"]
                    data = json.loads(data_str)
                    data["deviceId"] = device_id
                    data["timestamp"] = response["data"]["getLatestData"]["timestamp"]
                    data["type"] = response["data"]["getLatestData"]["type"]

                    logger.info(
                        f"Device data retrieved successfully: temperature={data.get('temperature', 'N/A')}\u00b0C, active={data.get('active', 'N/A')}"
                    )
                    logger.info(f"Complete device data: {json.dumps(data)}")
                    return data
                else:
                    logger.warning(
                        f"Unexpected API response format for device {device_id}: {json.dumps(response)}"
                    )
            except Exception as inner_e:
                logger.error(
                    f"Error fetching device data with getLatestData: {inner_e}"
                )

            # Try getDeviceState
            try:
                query = {
                    "operationName": "Query",
                    "variables": {"deviceId": device_id},
                    "query": "query Query($deviceId: ID!) {\n  getDeviceState(deviceId: $deviceId) {\n    desired\n    reported\n    timestamp\n    __typename\n  }\n}\n",
                }

                logger.info("Trying getDeviceState query format")
                response = await self.endpoint("device", query)

                if (
                    "data" in response
                    and response["data"]
                    and "getDeviceState" in response["data"]
                    and response["data"]["getDeviceState"]
                    and "reported" in response["data"]["getDeviceState"]
                ):
                    data_str = response["data"]["getDeviceState"]["reported"]
                    data = json.loads(data_str)
                    data["timestamp"] = response["data"]["getDeviceState"]["timestamp"]

                    logger.info("Device state retrieved successfully")
                    logger.info(f"Complete device state: {json.dumps(data)}")
                    return data
                else:
                    logger.warning(
                        f"Unexpected API response format for getDeviceState: {json.dumps(response)}"
                    )
            except Exception as inner_e:
                logger.error(f"Error fetching device state: {inner_e}")

            logger.warning(
                f"No valid data found for device {device_id}, using defaults"
            )
            logger.warning(f"Using default device data: {json.dumps(default_data)}")
            return default_data

        except Exception as e:
            logger.error(f"Error getting device data: {e}")
            default_data = {
                "deviceId": device_id,
                "active": False,
                "targetTemp": 60,
                "temperature": 20,
            }
            logger.warning(
                f"Using minimal default data after error: {json.dumps(default_data)}"
            )
            return default_data

    async def device_mutation(self, device_id: str, payload: dict) -> dict:
        """Send a mutation to control a device."""
        request_id = (
            f"{datetime.now().strftime('%Y%m%d%H%M%S')}-device-{device_id}"
        )

        payload_string = json.dumps(payload, indent=4)

        mutation = {
            "operationName": "Mutation",
            "variables": {
                "deviceId": device_id,
                "state": payload_string,
                "getFullState": False,
            },
            "query": "mutation Mutation($deviceId: ID!, $state: AWSJSON!, $getFullState: Boolean) {\n  requestStateChange(deviceId: $deviceId, state: $state, getFullState: $getFullState)\n}\n",
        }

        api_logger.debug(f"=== DEVICE MUTATION REQUEST {request_id} ===")
        api_logger.debug(f"Device ID: {device_id}")
        api_logger.debug(f"Payload: {payload_string}")
        api_logger.debug(f"Full Mutation: {json.dumps(mutation, indent=4)}")

        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Sending device control mutation (attempt {attempt+1}/{max_retries}): {json.dumps(payload)}"
                )
                api_logger.info(
                    f"Attempt {attempt+1}/{max_retries} for mutation {request_id}"
                )

                try:
                    auth_success = await self.authenticate()
                    if not auth_success:
                        logger.warning(
                            "Authentication unsuccessful, but continuing with request"
                        )
                except Exception as auth_error:
                    logger.error(
                        f"Authentication error before mutation: {auth_error}"
                    )
                    api_logger.error(
                        f"Authentication error before mutation {request_id}: {auth_error}"
                    )

                headers = await self.getHeaders()
                url = self.endpoints["device"]["endpoint"]

                timeout = aiohttp.ClientTimeout(
                    total=30, connect=10, sock_read=20, sock_connect=10
                )

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url, json=mutation, headers=headers
                    ) as response:
                        data = await response.json()

                        api_logger.debug(
                            f"=== DEVICE MUTATION RESPONSE {request_id} ==="
                        )
                        api_logger.debug(f"Status: {response.status}")
                        api_logger.debug(f"Response: {json.dumps(data, indent=4)}")

                if "errors" in data:
                    error_msg = (
                        data["errors"][0]["message"]
                        if data["errors"]
                        else "Unknown error"
                    )
                    logger.error(f"API error in mutation response: {error_msg}")
                    api_logger.error(f"Mutation error {request_id}: {error_msg}")

                    if "Unauthorized" in error_msg or "Authentication" in error_msg:
                        logger.info("Auth error detected, re-authenticating...")
                        api_logger.info(
                            f"Auth error in {request_id}, re-authenticating..."
                        )
                        await self.authenticate()

                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue

                logger.info(f"Mutation response: {json.dumps(data)}")
                api_logger.info(f"Mutation {request_id} successful")

                return {"success": True, "data": data}

            except Exception as e:
                logger.error(
                    f"Error in device mutation (attempt {attempt+1}/{max_retries}): {e}"
                )
                api_logger.error(
                    f"Error in mutation {request_id} (attempt {attempt+1}/{max_retries}): {e}"
                )

                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    api_logger.info(
                        f"Retrying mutation {request_id} in {retry_delay} seconds..."
                    )
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error("All mutation attempts failed")
                    api_logger.error(
                        f"All attempts for mutation {request_id} failed"
                    )
                    return {"success": False, "message": f"Error: {e}"}

        logger.error("Failed to send device command after max retries")
        api_logger.error(
            f"Failed to send mutation {request_id} after max retries"
        )
        return {
            "success": False,
            "message": "Failed to send command after multiple attempts",
        }

    async def get_user_data(self):
        """Get current user data including organization ID."""
        try:
            logger.info("Fetching user data to get organization ID")
            api_logger.info("Fetching user data to get organization ID")

            query = {
                "operationName": "Query",
                "variables": {},
                "query": "query Query {\n  getCurrentUserDetails {\n    email\n    organizationId\n    admin\n    given_name\n    family_name\n    superAdmin\n    rdUser\n    appSettings\n    __typename\n  }\n}\n",
            }

            response = await self.endpoint("users", query)

            if "data" in response and "getCurrentUserDetails" in response["data"]:
                user_data = response["data"]["getCurrentUserDetails"]
                organization_id = user_data.get("organizationId")
                email = user_data.get("email")

                logger.info(
                    f"User data retrieved. Organization ID: {organization_id}, Email: {email}"
                )
                api_logger.info(
                    f"User data retrieved. Organization ID: {organization_id}, Email: {email}"
                )

                return user_data
            else:
                logger.warning("Failed to get user data")
                api_logger.warning("Failed to get user data")
                return None
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
            api_logger.error(f"Error getting user data: {e}")
            return None

    async def get_organization_id(self):
        """Get the organization ID for the current user."""
        user_data = await self.get_user_data()
        if user_data and "organizationId" in user_data:
            return user_data["organizationId"]
        return None
