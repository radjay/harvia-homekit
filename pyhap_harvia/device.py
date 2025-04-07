import logging
import json
import asyncio
import websockets
import base64
import uuid
import random
import os
from datetime import datetime
from urllib.parse import quote

logger = logging.getLogger("harvia_sauna")

# Set up dedicated WebSocket logger for detailed communications logging
ws_logger = logging.getLogger("harvia_websocket")
ws_logger.setLevel(logging.DEBUG)

# Create logs directory if it doesn't exist
os.makedirs('/tmp/harvia-homekit', exist_ok=True)

# Add file handler for WebSocket logs
ws_log_file = '/tmp/harvia-homekit/websocket.log'
ws_file_handler = logging.FileHandler(ws_log_file)
ws_file_handler.setLevel(logging.DEBUG)
ws_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ws_file_handler.setFormatter(ws_formatter)
ws_logger.addHandler(ws_file_handler)

# Add stdout handler for WebSocket logs during development
ws_stdout_handler = logging.StreamHandler()
ws_stdout_handler.setLevel(logging.INFO)
ws_stdout_handler.setFormatter(ws_formatter)
ws_logger.addHandler(ws_stdout_handler)

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
        logger.info(f"Initializing device: {self.id} - {self.name}")
        success = await self.update_data()
        if not success:
            logger.error(f"Failed to initialize device {self.id} with initial data")
            return False

        # Start the websockets for real-time updates
        websocket_success = await self.start_websockets()
        if not websocket_success:
            logger.warning(f"Failed to start websockets for device {self.id}, will continue with polling")
            
        # Log the initial state
        logger.info(f"Device initialized successfully: {self.name}")
        logger.info(f"  - Current temperature: {self.current_temp}°C")
        logger.info(f"  - Target temperature: {self.target_temp}°C")
        logger.info(f"  - Power state: {'ON' if self.active else 'OFF'}")
        logger.info(f"  - Status codes: {self.status_codes}")
        
        return True

    async def update_data(self):
        """Update the device data from the API"""
        try:
            logger.info(f"Updating data for device: {self.id}")
            data = await self.api.get_device_data(self.id)
            if not data:
                logger.error(f"No data received for device {self.id}")
                return False
                
            success = await self.process_data_update(data)
            if success:
                logger.info(f"Data update successful for device {self.id}")
                return True
            else:
                logger.error(f"Failed to process data update for device {self.id}")
                return False
        except Exception as e:
            logger.error(f"Error updating device data: {str(e)}")
            return False

    async def process_data_update(self, data):
        """Process device data update"""
        if not data:
            logger.warning("Received empty data update")
            return False
            
        self.data = data
        logger.debug(f"Processing device update: {json.dumps(data)}")

        # Save previous values for change detection
        prev_temp = self.current_temp
        prev_target = self.target_temp
        prev_active = self.active

        if 'displayName' in data:
            self.name = data['displayName']
        if 'active' in data:
            # Make sure to convert to boolean correctly (0 = False, anything else = True)
            self.active = bool(int(data['active']))
            logger.info(f"Setting active state from data: {data['active']} -> {self.active}")
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
        # Additional handling for heatOn flag which may be more reliable than 'active'
        if 'heatOn' in data:
            heat_on = bool(data['heatOn'])
            if heat_on != self.active:
                logger.info(f"Heat-on flag ({heat_on}) differs from active state ({self.active})")
                # Only override if heat_on is True - if heat_on is false but active is true, the heater may be pausing
                if heat_on:
                    self.active = True

        # Log significant changes
        if self.current_temp != prev_temp:
            logger.info(f"Current temperature changed: {prev_temp}°C → {self.current_temp}°C")
        if self.target_temp != prev_target:
            logger.info(f"Target temperature changed: {prev_target}°C → {self.target_temp}°C")
        if self.active != prev_active:
            logger.info(f"Power state changed: {'ON' if prev_active else 'OFF'} → {'ON' if self.active else 'OFF'}")

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

    async def set_state(self, payload):
        """Set device state with a given payload"""
        # Update local state immediately for UI responsiveness
        for key, value in payload.items():
            if key == 'targetTemp':
                self.target_temp = value
                logger.info(f"Immediately updating local target temperature to {value}°C")
            elif key == 'targetRh':
                self.target_rh = value
                logger.info(f"Immediately updating local target humidity to {value}%")
            elif key == 'active':
                self.active = bool(value)
                logger.info(f"Immediately updating local power state to {'ON' if bool(value) else 'OFF'}")
            elif key == 'light':
                self.lights_on = bool(value)
                logger.info(f"Immediately updating local light state to {'ON' if bool(value) else 'OFF'}")
            elif key == 'fan':
                self.fan_on = bool(value)
                logger.info(f"Immediately updating local fan state to {'ON' if bool(value) else 'OFF'}")
            elif key == 'steamEn':
                self.steam_on = bool(value)
                logger.info(f"Immediately updating local steam state to {'ON' if bool(value) else 'OFF'}")

        # Notify callbacks immediately to update HomeKit UI
        for callback in self.update_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in callback after local state update: {str(e)}")

        # Run API call in a separate thread to avoid blocking HomeKit
        def run_api_call():
            async def do_api_call():
                try:
                    logger.info(f"Sending API request with payload: {json.dumps(payload)}")
                    result = await self.api.device_mutation(self.id, payload)
                    logger.info(f"API request completed. Result: {result}")
                    return result
                except Exception as e:
                    logger.error(f"API request failed: {str(e)}")
                    return False

            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(do_api_call())
            finally:
                loop.close()

        # Start API call in a thread
        import threading
        thread = threading.Thread(target=run_api_call)
        thread.daemon = True
        thread.start()
        
        # Return success because we've already updated the local state
        # The API call continues in the background
        return True

    async def set_target_temperature(self, temp: int):
        """Set the target temperature"""
        logger.info(f"Setting target temperature to {temp}°C")
        try:
            return await self.set_state({'targetTemp': temp})
        except Exception as e:
            logger.error(f"Failed to set temperature: {str(e)}")
            # Update local state anyway for UI consistency
            self.target_temp = temp
            for callback in self.update_callbacks:
                try:
                    callback(self)
                except Exception as callback_error:
                    logger.error(f"Error in callback after temperature update: {str(callback_error)}")
            return False

    async def set_target_relative_humidity(self, rh: int):
        """Set the target relative humidity"""
        try:
            return await self.set_state({'targetRh': rh})
        except Exception as e:
            logger.error(f"Failed to set humidity: {str(e)}")
            return None

    async def set_fan(self, state: bool):
        """Set the fan state"""
        try:
            fan_int = int(state)
            return await self.set_state({'fan': fan_int})
        except Exception as e:
            logger.error(f"Failed to set fan: {str(e)}")
            return None

    async def set_lights(self, state: bool):
        """Set the lights state"""
        try:
            light_int = int(state)
            return await self.set_state({'light': light_int})
        except Exception as e:
            logger.error(f"Failed to set lights: {str(e)}")
            return None

    async def set_steamer(self, state: bool):
        """Set the steamer state"""
        try:
            steamer_int = int(state)
            return await self.set_state({'steamEn': steamer_int})
        except Exception as e:
            logger.error(f"Failed to set steamer: {str(e)}")
            return None

    async def set_active(self, state: bool):
        """Set the power state"""
        state_int = int(state)
        logger.info(f"Setting power state to {'ON' if state else 'OFF'} (value: {state_int})")
        try:
            return await self.set_state({'active': state_int})
        except Exception as e:
            logger.error(f"Failed to set power state: {str(e)}")
            # Update local state anyway for UI consistency
            self.active = state
            for callback in self.update_callbacks:
                try:
                    callback(self)
                except Exception as callback_error:
                    logger.error(f"Error in callback after power state update: {str(callback_error)}")
            return False

    def get_door_state(self):
        """Get the door state (open/closed) from status codes"""
        if not self.status_codes:
            return False
            
        try:
            safety_status = int(str(self.status_codes)[1])
            return safety_status == 9  # 9 means door is open
        except (IndexError, ValueError):
            return False

    async def process_state_update(self, data):
        """Process device state update from WebSocket"""
        if not data:
            logger.warning("Received empty state update")
            return False
            
        logger.debug(f"Processing device state update: {json.dumps(data)}")
        
        # State updates from WebSocket have the same format as regular updates
        return await self.process_data_update(data)

class HarviaWebsocket:
    def __init__(self, api, device, endpoint_type):
        self.api = api
        self.device = device
        self.endpoint_type = endpoint_type
        self.websocket = None
        self.running = False
        self.connection_id = None
        self.registration_id = None
        # Generate a unique session ID for this websocket instance
        self.session_id = f"{self.endpoint_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    async def start(self):
        """Start the websocket"""
        self.running = True
        ws_logger.info(f"Starting WebSocket {self.session_id} for device {self.device.id}")
        
        while self.running:
            try:
                ws_logger.info(f"Connecting WebSocket {self.session_id}")
                await self.connect()
                
                # Create subscription
                ws_logger.info(f"Creating subscription for WebSocket {self.session_id}")
                await self.create_subscription()
                
                # Keep receiving messages
                ws_logger.info(f"Starting message reception loop for WebSocket {self.session_id}")
                await self.receive_messages()
            except Exception as e:
                logger.error(f"Websocket error ({self.endpoint_type}): {str(e)}")
                ws_logger.error(f"WebSocket {self.session_id} error: {str(e)}")
                ws_logger.info(f"Will attempt to reconnect WebSocket {self.session_id} in 5 seconds")
                await asyncio.sleep(5)  # Wait before reconnecting
    
    async def connect(self):
        """Connect to the websocket"""
        try:
            websock_url = await self.api.getWebsockUrlByEndpoint(self.endpoint_type)
            logger.debug(f"Connecting to {self.endpoint_type} websocket: {websock_url}")
            ws_logger.debug(f"WebSocket {self.session_id} URL: {websock_url}")
            
            # Truncate URL for logging (it can be very long with the auth token)
            truncated_url = websock_url[:100] + "..." if len(websock_url) > 100 else websock_url
            ws_logger.info(f"Connecting to WebSocket {self.session_id} URL: {truncated_url}")
            
            # Connect with proper subprotocols to avoid NoProtocolError
            self.websocket = await websockets.connect(
                websock_url,
                subprotocols=["graphql-ws"],  # Required for GraphQL WebSocket protocol
                max_size=None  # Allow any size messages
            )
            
            # Send connection init message
            connection_init = {"type": "connection_init"}
            connection_init_str = json.dumps(connection_init)
            ws_logger.debug(f"WebSocket {self.session_id} sending init: {connection_init_str}")
            await self.websocket.send(connection_init_str)
            
            # Receive connection ack with timeout
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                ws_logger.debug(f"WebSocket {self.session_id} received: {response}")
                data = json.loads(response)
                
                if data.get("type") == "connection_ack":
                    self.connection_id = data.get("payload", {}).get("connectionId")
                    logger.info(f"Connected to {self.endpoint_type} websocket. Connection ID: {self.connection_id}")
                    ws_logger.info(f"WebSocket {self.session_id} connected. Connection ID: {self.connection_id}")
                    return True
                elif data.get("type") == "connection_error":
                    error_details = data.get("payload", {}).get("errors", [{}])[0].get("message", "Unknown error")
                    logger.error(f"Connection error: {error_details}")
                    ws_logger.error(f"WebSocket {self.session_id} connection error: {error_details}")
                    return False
                else:
                    logger.error(f"Failed to receive connection ack: {data}")
                    ws_logger.error(f"WebSocket {self.session_id} failed to receive connection ack: {data}")
                    return False
            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for connection acknowledgment")
                ws_logger.error(f"WebSocket {self.session_id} timeout waiting for connection acknowledgment")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to {self.endpoint_type} websocket: {str(e)}")
            ws_logger.error(f"WebSocket {self.session_id} connection exception: {str(e)}")
            raise
    
    async def create_subscription(self):
        """Create a websocket subscription"""
        try:
            # Create subscription message based on endpoint type
            if self.endpoint_type == "data":
                message_data = await self.create_data_subscription_message()
            else:
                message_data = await self.create_device_subscription_message()
            
            # Generate UUID for this subscription
            self.registration_id = str(uuid.uuid4())
            
            # Create subscription message in the format expected by the API
            subscription_message = {
                "id": self.registration_id,
                "payload": {
                    "data": message_data,
                    "extensions": {
                        "authorization": {
                            "Authorization": await self.api.getIdToken(),
                            "host": (await self.api.getWebsocketEndpoint(self.endpoint_type))['host'],
                            "x-amz-user-agent": "aws-amplify/2.0.5 react-native"
                        }
                    }
                },
                "type": "start"
            }
            
            # Send subscription message
            subscription_str = json.dumps(subscription_message)
            ws_logger.debug(f"WebSocket {self.session_id} sending subscription: {subscription_str}")
            await self.websocket.send(subscription_str)
            
            # Wait for a response - could be start_ack or keep-alive (ka)
            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                ws_logger.debug(f"WebSocket {self.session_id} received subscription response: {response}")
                data = json.loads(response)
                
                # Check for known response types
                if data.get("type") == "start_ack":
                    # This is a standard acknowledgment
                    logger.info(f"Subscription created for {self.endpoint_type} websocket with start_ack")
                    ws_logger.info(f"WebSocket {self.session_id} subscription created with start_ack")
                    return True
                elif data.get("type") == "ka":
                    # Keep-alive response - this is also valid in the Harvia API
                    logger.info(f"Subscription likely created for {self.endpoint_type} websocket (received keep-alive)")
                    ws_logger.info(f"WebSocket {self.session_id} subscription likely created (received keep-alive)")
                    
                    # Wait for another message - might be start_ack after ka
                    try:
                        second_response = await asyncio.wait_for(self.websocket.recv(), timeout=2.0)
                        ws_logger.debug(f"WebSocket {self.session_id} received second response: {second_response}")
                        second_data = json.loads(second_response)
                        
                        if second_data.get("type") == "start_ack":
                            logger.info(f"Subscription confirmed for {self.endpoint_type} websocket with delayed start_ack")
                            ws_logger.info(f"WebSocket {self.session_id} subscription confirmed with delayed start_ack")
                        # Either way, consider it a success if we get this far
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        # It's okay if we don't get a second message
                        pass
                    
                    return True
                elif data.get("type") == "error":
                    error_msg = data.get("payload", {}).get("message", "Unknown error")
                    logger.error(f"Subscription error: {error_msg}")
                    ws_logger.error(f"WebSocket {self.session_id} subscription error: {error_msg}")
                    return False
                else:
                    logger.error(f"Unexpected subscription response: {data}")
                    ws_logger.error(f"WebSocket {self.session_id} unexpected subscription response: {data}")
                    return False
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for subscription acknowledgment")
                ws_logger.error(f"WebSocket {self.session_id} timeout waiting for subscription ack")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create subscription: {str(e)}")
            ws_logger.error(f"WebSocket {self.session_id} failed to create subscription: {str(e)}")
            return False
    
    async def create_data_subscription_message(self):
        """Create a data subscription message"""
        # This is a JSON string following the format used by the Home Assistant plugin
        ws_logger.debug(f"Creating data subscription message for device {self.device.id}")
        
        # Try to get the organization ID from the API
        organization_id = await self.api.get_organization_id()
        
        # If we couldn't get the organization ID, use a fallback
        if not organization_id:
            organization_id = "5d34705e-278d-4de7-84b2-4b515db39c55"  # Fallback from logs
            ws_logger.warning(f"Using fallback organization ID {organization_id} for subscription")
        else:
            ws_logger.info(f"Using organization ID {organization_id} from API for subscription")
        
        subscription_data = {
            "query": """subscription Subscription($receiver: String!) {
  onDataUpdates(receiver: $receiver) {
    item {
      deviceId
      timestamp
      sessionId
      type
      data
      __typename
    }
    __typename
  }
}
""",
            "variables": {
                "receiver": organization_id
            }
        }
        
        return json.dumps(subscription_data)
    
    async def create_device_subscription_message(self):
        """Create a device subscription message"""
        # This is a JSON string following the format used by the Home Assistant plugin
        ws_logger.debug(f"Creating device subscription message for device {self.device.id}")
        
        # Try to get the organization ID from the API
        organization_id = await self.api.get_organization_id()
        
        # If we couldn't get the organization ID, use a fallback
        if not organization_id:
            organization_id = "5d34705e-278d-4de7-84b2-4b515db39c55"  # Fallback from logs
            ws_logger.warning(f"Using fallback organization ID {organization_id} for subscription")
        else:
            ws_logger.info(f"Using organization ID {organization_id} from API for subscription")
        
        subscription_data = {
            "query": """subscription Subscription($receiver: String!) {
  onStateUpdated(receiver: $receiver) {
    desired
    reported
    timestamp
    receiver
    __typename
  }
}
""",
            "variables": {
                "receiver": organization_id
            }
        }
        
        return json.dumps(subscription_data)
    
    async def receive_messages(self):
        """Receive and process messages from the websocket"""
        ws_logger.info(f"WebSocket {self.session_id} entering receive loop")
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                ws_logger.debug(f"WebSocket {self.session_id} received message: {message}")
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.info(f"{self.endpoint_type} websocket connection closed. Reconnecting...")
                ws_logger.info(f"WebSocket {self.session_id} connection closed ({e.code}: {e.reason}). Reconnecting...")
                break
            except Exception as e:
                logger.error(f"Error receiving {self.endpoint_type} websocket message: {str(e)}")
                ws_logger.error(f"WebSocket {self.session_id} receive error: {str(e)}")
                break
        
        ws_logger.info(f"WebSocket {self.session_id} exited receive loop")
    
    async def handle_message(self, message):
        """Handle a message from the websocket"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            # Handle different message types
            if msg_type == "ka":
                # Keep-alive message
                ws_logger.debug(f"WebSocket {self.session_id} received keep-alive")
                return
                
            elif msg_type == "start_ack":
                # Subscription acknowledgment
                ws_logger.debug(f"WebSocket {self.session_id} received subscription acknowledgment")
                return
                
            elif msg_type == "error":
                # Handle error messages
                ws_logger.error(f"WebSocket {self.session_id} received error: {data}")
                
                # Check for error details
                if "payload" in data and "errors" in data["payload"]:
                    for error in data["payload"]["errors"]:
                        error_type = error.get("errorType", "Unknown")
                        error_message = error.get("message", "No message")
                        ws_logger.error(f"WebSocket {self.session_id} error: {error_type} - {error_message}")
                        
                        # If unauthorized, try to re-authenticate
                        if error_type == "Unauthorized":
                            ws_logger.warning(f"WebSocket {self.session_id} received unauthorized error, re-authenticating")
                            await self.api.authenticate()
                            # Force a reconnection
                            self.websocket.close()
                            return
                else:
                    ws_logger.error(f"WebSocket {self.session_id} received error without details: {data}")
                
                return
                
            elif msg_type == "data":
                # Process data messages
                ws_logger.debug(f"WebSocket {self.session_id} received data update")
                
                # Validate the data structure
                if not data.get("payload") or not data["payload"].get("data"):
                    ws_logger.warning(f"WebSocket {self.session_id} received malformed data message: {data}")
                    return
                
                # Process device state updates
                if self.endpoint_type == "device" and "onStateUpdated" in data["payload"]["data"]:
                    # Extract and process state updates
                    state_data = data["payload"]["data"]["onStateUpdated"]
                    
                    if "reported" in state_data and state_data["reported"]:
                        try:
                            # Parse the reported state (it's a JSON string)
                            reported_data = json.loads(state_data["reported"])
                            ws_logger.info(f"WebSocket {self.session_id} processing device state update")
                            
                            # Extra logging to debug state
                            if "active" in reported_data:
                                ws_logger.info(f"Received active state: {reported_data['active']} (type: {type(reported_data['active']).__name__})")
                            
                            # Ensure the update is for our device
                            if "deviceId" in reported_data and reported_data["deviceId"] == self.device.id:
                                # Process the update
                                await self.device.process_state_update(reported_data)
                            else:
                                ws_logger.debug(f"WebSocket {self.session_id} ignoring update for different device: {reported_data.get('deviceId', 'unknown')}")
                        except json.JSONDecodeError:
                            ws_logger.error(f"WebSocket {self.session_id} failed to parse reported state: {state_data['reported']}")
                
                # Process data updates
                elif self.endpoint_type == "data" and "onDataUpdates" in data["payload"]["data"]:
                    # Extract and process data updates
                    update_data = data["payload"]["data"]["onDataUpdates"]
                    
                    if "item" in update_data and update_data["item"]:
                        item = update_data["item"]
                        
                        # Ensure the update is for our device
                        if "deviceId" in item and item["deviceId"] == self.device.id:
                            if "data" in item and item["data"]:
                                try:
                                    # Parse the data (it's a JSON string)
                                    device_data = json.loads(item["data"])
                                    # Add metadata
                                    device_data["timestamp"] = item.get("timestamp")
                                    device_data["deviceId"] = item.get("deviceId")
                                    
                                    # Process the update
                                    ws_logger.info(f"WebSocket {self.session_id} processing data update")
                                    await self.device.process_data_update(device_data)
                                except json.JSONDecodeError:
                                    ws_logger.error(f"WebSocket {self.session_id} failed to parse data: {item['data']}")
                        else:
                            ws_logger.debug(f"WebSocket {self.session_id} ignoring update for different device: {item.get('deviceId', 'unknown')}")
            else:
                # Unknown message type
                ws_logger.debug(f"WebSocket {self.session_id} unhandled message type: {msg_type}")
                
        except json.JSONDecodeError:
            ws_logger.error(f"WebSocket {self.session_id} failed to parse message: {message}")
        except Exception as e:
            ws_logger.error(f"WebSocket {self.session_id} error handling message: {str(e)}")
    
    async def stop(self):
        """Stop the websocket connection"""
        logger.info(f"Stopping {self.endpoint_type} websocket connection")
        ws_logger.info(f"Stopping WebSocket {self.session_id}")
        
        self.running = False
        
        if self.websocket:
            try:
                # Send stop message if we have a registration ID
                if self.registration_id:
                    stop_message = {
                        "id": self.registration_id,
                        "type": "stop"
                    }
                    stop_str = json.dumps(stop_message)
                    ws_logger.debug(f"WebSocket {self.session_id} sending stop: {stop_str}")
                    await self.websocket.send(stop_str)
                
                # Close the connection
                await self.websocket.close()
                ws_logger.info(f"WebSocket {self.session_id} closed")
            except Exception as e:
                logger.error(f"Error closing {self.endpoint_type} websocket: {str(e)}")
                ws_logger.error(f"WebSocket {self.session_id} close error: {str(e)}")
            
            self.websocket = None 