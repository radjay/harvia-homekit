import logging
import json
import asyncio
import websockets
import base64
import uuid
import random
from urllib.parse import quote

logger = logging.getLogger("harvia_sauna")

class HarviaDevice:
    def __init__(self, api, device_id, device_name):
        self.api = api
        self.id = device_id
        self.name = device_name
        self.data = {}
        self.active = False
        self.lights_on = False
        self.steam_on = False
        self.target_temp = None
        self.target_rh = None
        self.current_temp = None
        self.humidity = None
        self.remaining_time = None
        self.heat_up_time = 0
        self.fan_on = False
        self.status_codes = None
        self.latest_update = None
        self.data_websocket = None
        self.device_websocket = None
        self.update_callbacks = []

    async def initialize(self):
        """Initialize the device with current state"""
        await self.update_data()
        await self.start_websockets()
        return True

    async def update_data(self):
        """Update the device data from the API"""
        try:
            data = await self.api.get_device_data(self.id)
            await self.process_data_update(data)
            return True
        except Exception as e:
            logger.error(f"Error updating device data: {str(e)}")
            return False

    async def process_data_update(self, data):
        """Process device data update"""
        if not data:
            return False
            
        self.data = data
        logger.debug(f"Processing device update: {json.dumps(data)}")

        if 'displayName' in data:
            self.name = data['displayName']
        if 'active' in data:
            self.active = bool(data['active'])
        if 'light' in data:
            self.lights_on = bool(data['light'])
        if 'fan' in data:
            self.fan_on = bool(data['fan'])
        if 'steamOn' in data:
            self.steam_on = data['steamOn']
        if 'steamEn' in data:
            self.steam_on = bool(data['steamEn'])
        if 'targetTemp' in data:
            self.target_temp = data['targetTemp']
        if 'targetRh' in data:
            self.target_rh = data['targetRh']
        if 'heatUpTime' in data:
            self.heat_up_time = data['heatUpTime']
        if 'remainingTime' in data:
            self.remaining_time = data['remainingTime']
        if 'temperature' in data:
            self.current_temp = data['temperature']
        if 'humidity' in data:
            self.humidity = data['humidity']
        if 'timestamp' in data:
            self.latest_update = data['timestamp']
        if 'statusCodes' in data:
            if data['statusCodes'] != self.status_codes:
                logger.debug(f"StatusCodes changed: {str(data['statusCodes'])}")
            self.status_codes = data['statusCodes']

        # Call any update callbacks
        for callback in self.update_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in update callback: {str(e)}")

        return True

    async def start_websockets(self):
        """Start the websocket connections for device and data updates"""
        # Start data websocket
        self.data_websocket = HarviaWebsocket(self.api, self, 'data')
        asyncio.create_task(self.data_websocket.start())
        
        # Start device websocket
        self.device_websocket = HarviaWebsocket(self.api, self, 'device')
        asyncio.create_task(self.device_websocket.start())
        
        return True

    def add_update_callback(self, callback):
        """Add a callback to be called when the device is updated"""
        if callback not in self.update_callbacks:
            self.update_callbacks.append(callback)

    def remove_update_callback(self, callback):
        """Remove an update callback"""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    async def set_target_temperature(self, temp: int):
        """Set the target temperature"""
        payload = {'targetTemp': temp}
        await self.api.device_mutation(self.id, payload)

    async def set_target_relative_humidity(self, rh: int):
        """Set the target relative humidity"""
        payload = {'targetRh': rh}
        await self.api.device_mutation(self.id, payload)

    async def set_fan(self, state: bool):
        """Set the fan state"""
        fan_int = int(state)
        payload = {'fan': fan_int}
        await self.api.device_mutation(self.id, payload)

    async def set_lights(self, state: bool):
        """Set the lights state"""
        light_int = int(state)
        payload = {'light': light_int}
        await self.api.device_mutation(self.id, payload)

    async def set_steamer(self, state: bool):
        """Set the steamer state"""
        steamer_int = int(state)
        payload = {'steamEn': steamer_int}
        await self.api.device_mutation(self.id, payload)

    async def set_active(self, state: bool):
        """Set the active state (power on/off)"""
        active_int = int(state)
        payload = {'active': active_int}
        await self.api.device_mutation(self.id, payload)

    def get_door_state(self):
        """Get the door state (open/closed) from status codes"""
        if not self.status_codes:
            return False
            
        try:
            safety_status = int(str(self.status_codes)[1])
            return safety_status == 9  # 9 means door is open
        except (IndexError, ValueError):
            return False


class HarviaWebsocket:
    def __init__(self, api, device, endpoint_type):
        self.api = api
        self.device = device
        self.endpoint_type = endpoint_type
        self.websocket = None
        self.running = False
        self.connection_id = None
        self.registration_id = None
    
    async def start(self):
        """Start the websocket"""
        self.running = True
        
        while self.running:
            try:
                await self.connect()
                
                # Create subscription
                await self.create_subscription()
                
                # Keep receiving messages
                await self.receive_messages()
            except Exception as e:
                logger.error(f"Websocket error ({self.endpoint_type}): {str(e)}")
                await asyncio.sleep(5)  # Wait before reconnecting
    
    async def connect(self):
        """Connect to the websocket"""
        try:
            websock_url = await self.api.getWebsockUrlByEndpoint(self.endpoint_type)
            logger.debug(f"Connecting to {self.endpoint_type} websocket: {websock_url}")
            self.websocket = await websockets.connect(websock_url)
            
            # Send connection init message
            connection_init = {"type": "connection_init"}
            await self.websocket.send(json.dumps(connection_init))
            
            # Receive connection ack
            response = await self.websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "connection_ack":
                self.connection_id = data.get("payload", {}).get("connectionId")
                logger.info(f"Connected to {self.endpoint_type} websocket. Connection ID: {self.connection_id}")
                return True
            else:
                logger.error(f"Failed to receive connection ack: {data}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to {self.endpoint_type} websocket: {str(e)}")
            raise
    
    async def create_subscription(self):
        """Create a GraphQL subscription"""
        try:
            if self.endpoint_type == "data":
                message = await self.create_data_subscription_message()
            else:  # device
                message = await self.create_device_subscription_message()
                
            await self.websocket.send(message)
            
            # Receive subscription response
            response = await self.websocket.recv()
            data = json.loads(response)
            
            if data.get("type") == "start_ack":
                self.registration_id = data.get("id")
                logger.info(f"Subscription to {self.endpoint_type} created successfully. ID: {self.registration_id}")
                return True
            else:
                logger.error(f"Failed to create subscription: {data}")
                return False
        except Exception as e:
            logger.error(f"Failed to create subscription: {str(e)}")
            raise
    
    async def create_data_subscription_message(self):
        """Create a data subscription message"""
        subscription_id = str(uuid.uuid4())
        return json.dumps({
            "id": subscription_id,
            "type": "start",
            "payload": {
                "data": {
                    "query": "subscription OnDeviceDataChanged($deviceId: ID!) { onDeviceDataChanged(deviceId: $deviceId) { active deviceId fan humidity light moisture remoteStartEn remainingTime steamEn steamOn statusCodes targetRh targetTemp temperature timestamp }}",
                    "variables": {"deviceId": self.device.id}
                }
            }
        })
    
    async def create_device_subscription_message(self):
        """Create a device subscription message"""
        subscription_id = str(uuid.uuid4())
        return json.dumps({
            "id": subscription_id,
            "type": "start",
            "payload": {
                "data": {
                    "query": "subscription OnDeviceChanged($deviceId: ID!) { onDeviceChanged(deviceId: $deviceId) { active connectionState displayName fan hwVersion id light metadata moisture remoteStartEn swVersion targetRh targetTemp type }}",
                    "variables": {"deviceId": self.device.id}
                }
            }
        })
    
    async def receive_messages(self):
        """Receive and process messages from the websocket"""
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"{self.endpoint_type} websocket connection closed. Reconnecting...")
                break
            except Exception as e:
                logger.error(f"Error receiving {self.endpoint_type} websocket message: {str(e)}")
                break
    
    async def handle_message(self, message):
        """Handle a message from the websocket"""
        try:
            data = json.loads(message)
            
            if data.get("type") == "data":
                payload = data.get("payload", {}).get("data", {})
                
                if self.endpoint_type == "data" and "onDeviceDataChanged" in payload:
                    device_data = payload["onDeviceDataChanged"]
                    logger.debug(f"Data update received: {json.dumps(device_data)}")
                    await self.device.process_data_update(device_data)
                
                elif self.endpoint_type == "device" and "onDeviceChanged" in payload:
                    device_data = payload["onDeviceChanged"]
                    logger.debug(f"Device update received: {json.dumps(device_data)}")
                    # Process any relevant device updates
                    if "displayName" in device_data:
                        self.device.name = device_data["displayName"]
                    
                    # Trigger a full data update to ensure we have the latest state
                    await self.device.update_data()
            
            elif data.get("type") == "ka":
                # Keep-alive message
                pass
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
    
    async def stop(self):
        """Stop the websocket"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None 