#!/usr/bin/env python3
import asyncio
import websockets
import json
import base64
import logging
from pyhap_harvia.api import HarviaSaunaAPI
from urllib.parse import quote
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("test_websocket")

class TestWebSocket:
    def __init__(self, api, endpoint_type="device"):
        self.api = api
        self.endpoint_type = endpoint_type
        self.websocket = None
        self.running = False
        self.connection_id = None
        self.subscription_id = str(uuid.uuid4())
        self.organization_id = None
        
    async def get_organization_id(self):
        """Get the organization ID from the API"""
        try:
            user_data = await self.api.get_user_data()
            if user_data and 'organizationId' in user_data:
                return user_data['organizationId']
        except Exception as e:
            logger.error(f"Error getting organization ID: {str(e)}")
        
        # Fallback from logs
        logger.warning("Using fallback organization ID for testing")
        return "5d34705e-278d-4de7-84b2-4b515db39c55"  # ID seen in logs
    
    async def connect(self):
        """Connect to the websocket"""
        try:
            websock_endpoint = await self.api.getWebsocketEndpoint(self.endpoint_type)
            wss_url = websock_endpoint['wssUrl']
            host = websock_endpoint['host']
            
            # Get auth token
            id_token = await self.api.getIdToken()
            header_payload = {"Authorization": id_token, "host": host, "x-amz-user-agent": "aws-amplify/2.0.5 react-native"}
            data_string = json.dumps(header_payload)
            encoded_header = base64.b64encode(data_string.encode())
            
            # Full URL
            full_url = f"{wss_url}?header={quote(encoded_header.decode())}&payload=e30="
            logger.info(f"Connecting to {self.endpoint_type} websocket...")
            
            # Connect with proper protocol and options
            self.websocket = await websockets.connect(
                full_url,
                subprotocols=["graphql-ws"],  # Required
                max_size=None  # Allow any size messages
            )
            
            # Send connection init
            connection_init = {"type": "connection_init"}
            await self.websocket.send(json.dumps(connection_init))
            logger.info("Sent connection_init message")
            
            # Wait for connection ack
            ack_response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            logger.info(f"Received: {ack_response}")
            
            ack_data = json.loads(ack_response)
            if ack_data.get("type") == "connection_ack":
                self.connection_id = ack_data.get("payload", {}).get("connectionId")
                logger.info(f"Successfully connected to {self.endpoint_type} websocket")
                self.running = True
                return True
            else:
                logger.error(f"Failed to receive connection ack: {ack_data}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to websocket: {str(e)}")
            return False
    
    async def create_subscription(self):
        """Create a subscription based on endpoint type"""
        try:
            # Get organization ID
            self.organization_id = await self.get_organization_id()
            logger.info(f"Using organization ID: {self.organization_id}")
            
            # Create subscription message
            if self.endpoint_type == "device":
                subscription = await self.create_device_subscription()
            else:
                subscription = await self.create_data_subscription()
                
            # Send subscription
            logger.info(f"Sending {self.endpoint_type} subscription: {subscription}")
            await self.websocket.send(json.dumps(subscription))
            
            # Wait for subscription ack
            start_ack = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
            logger.info(f"Subscription response: {start_ack}")
            
            ack_data = json.loads(start_ack)
            if ack_data.get("type") == "start_ack":
                logger.info(f"Subscription created successfully")
                return True
            else:
                logger.error(f"Failed to create subscription: {ack_data}")
                return False
                
        except Exception as e:
            logger.error(f"Error creating subscription: {str(e)}")
            return False
    
    async def create_device_subscription(self):
        """Create device state subscription"""
        subscription_data = {
            "query": f"""subscription Subscription($receiver: String!) {{
  onStateUpdated(receiver: $receiver) {{
    desired
    reported
    timestamp
    receiver
    __typename
  }}
}}""",
            "variables": {
                "receiver": self.organization_id
            }
        }
        
        # Format according to Harvia API expectations
        return {
            "id": self.subscription_id,
            "type": "start",
            "payload": {
                "data": json.dumps(subscription_data),
                "extensions": {
                    "authorization": {
                        "Authorization": await self.api.getIdToken(),
                        "host": (await self.api.getWebsocketEndpoint(self.endpoint_type))['host'],
                        "x-amz-user-agent": "aws-amplify/2.0.5 react-native"
                    }
                }
            }
        }
    
    async def create_data_subscription(self):
        """Create data updates subscription"""
        subscription_data = {
            "query": f"""subscription Subscription($receiver: String!) {{
  onDataUpdates(receiver: $receiver) {{
    item {{
      deviceId
      timestamp
      sessionId
      type
      data
      __typename
    }}
    __typename
  }}
}}""",
            "variables": {
                "receiver": self.organization_id
            }
        }
        
        # Format according to Harvia API expectations
        return {
            "id": self.subscription_id,
            "type": "start",
            "payload": {
                "data": json.dumps(subscription_data),
                "extensions": {
                    "authorization": {
                        "Authorization": await self.api.getIdToken(),
                        "host": (await self.api.getWebsocketEndpoint(self.endpoint_type))['host'],
                        "x-amz-user-agent": "aws-amplify/2.0.5 react-native"
                    }
                }
            }
        }
    
    async def receive_messages(self, timeout=30):
        """Receive messages for a specific time period"""
        try:
            logger.info(f"Receiving messages for {timeout} seconds...")
            end_time = asyncio.get_event_loop().time() + timeout
            
            while asyncio.get_event_loop().time() < end_time:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.recv(),
                        timeout=min(5, end_time - asyncio.get_event_loop().time())
                    )
                    
                    logger.info(f"Received message: {message}")
                    
                    # Parse message
                    data = json.loads(message)
                    msg_type = data.get("type", "unknown")
                    
                    if msg_type == "ka":
                        logger.info("Received keep-alive message")
                    elif msg_type == "data":
                        logger.info("Received data update")
                        # Process data update
                        if "payload" in data and "data" in data["payload"]:
                            if "onStateUpdated" in data["payload"]["data"]:
                                reported = data["payload"]["data"]["onStateUpdated"]["reported"]
                                logger.info(f"Device state update: {reported}")
                            elif "onDataUpdates" in data["payload"]["data"]:
                                item = data["payload"]["data"]["onDataUpdates"]["item"]
                                device_data = item["data"]
                                logger.info(f"Data update for device {item['deviceId']}: {device_data}")
                    elif msg_type == "error":
                        logger.error(f"Received error message: {data}")
                        if "payload" in data and "errors" in data["payload"]:
                            for error in data["payload"]["errors"]:
                                if "errorType" in error and error["errorType"] == "Unauthorized":
                                    logger.warning("Unauthorized error detected, re-authenticating")
                                    await self.api.authenticate()
                    else:
                        logger.info(f"Unhandled message type: {msg_type}")
                
                except asyncio.TimeoutError:
                    # This is expected when waiting for messages
                    pass
                    
        except Exception as e:
            logger.error(f"Error receiving messages: {str(e)}")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the websocket connection"""
        if self.websocket:
            try:
                stop_msg = {
                    "id": self.subscription_id,
                    "type": "stop"
                }
                await self.websocket.send(json.dumps(stop_msg))
                logger.info("Sent stop message")
                
                await self.websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing websocket: {str(e)}")
            
            self.websocket = None
            self.running = False


async def main():
    # Load credentials
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    # Create API client
    api = HarviaSaunaAPI(config['username'], config['password'])
    await api.initialize()
    
    # Test device websocket
    device_ws = TestWebSocket(api, "device")
    if await device_ws.connect():
        if await device_ws.create_subscription():
            # Receive messages for 30 seconds
            await device_ws.receive_messages(30)
        else:
            logger.error("Failed to create subscription")
    
    # Test data websocket
    data_ws = TestWebSocket(api, "data")
    if await data_ws.connect():
        if await data_ws.create_subscription():
            # Receive messages for 30 seconds
            await data_ws.receive_messages(30)
        else:
            logger.error("Failed to create subscription")
    
    # Clean up
    await api.close()


if __name__ == "__main__":
    asyncio.run(main()) 