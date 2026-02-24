"""Harvia device state management and WebSocket communication."""

import asyncio
import base64
import json
import logging
import random
import threading
import uuid
from datetime import datetime
from urllib.parse import quote

import websockets

logger = logging.getLogger("harvia_sauna")
ws_logger = logging.getLogger("harvia_websocket")


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
        """Initialize the device with current state."""
        logger.info(f"Initializing device: {self.id} - {self.name}")
        success = await self.update_data()
        if not success:
            logger.error(f"Failed to initialize device {self.id} with initial data")
            return False

        websocket_success = await self.start_websockets()
        if not websocket_success:
            logger.warning(
                f"Failed to start websockets for device {self.id}, will continue with polling"
            )

        logger.info(f"Device initialized successfully: {self.name}")
        logger.info(f"  - Current temperature: {self.current_temp}\u00b0C")
        logger.info(f"  - Target temperature: {self.target_temp}\u00b0C")
        logger.info(f"  - Power state: {'ON' if self.active else 'OFF'}")
        logger.info(f"  - Status codes: {self.status_codes}")

        return True

    async def update_data(self):
        """Update the device data from the API."""
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
            logger.error(f"Error updating device data: {e}")
            return False

    async def process_data_update(self, data):
        """Process device data update."""
        if not data:
            logger.warning("Received empty data update")
            return False

        self.data = data
        logger.debug(f"Processing device update: {json.dumps(data)}")

        prev_temp = self.current_temp
        prev_target = self.target_temp
        prev_active = self.active

        if "displayName" in data:
            self.name = data["displayName"]
        if "active" in data:
            self.active = bool(int(data["active"]))
            logger.info(
                f"Setting active state from data: {data['active']} -> {self.active}"
            )
        if "light" in data:
            self.lights_on = bool(data["light"])
        if "fan" in data:
            self.fan_on = bool(data["fan"])
        if "steamOn" in data:
            self.steam_on = data["steamOn"]
        if "steamEn" in data:
            self.steam_on = bool(data["steamEn"])
        if "targetTemp" in data:
            self.target_temp = data["targetTemp"]
        if "targetRh" in data:
            self.target_rh = data["targetRh"]
        if "heatUpTime" in data:
            self.heat_up_time = data["heatUpTime"]
        if "remainingTime" in data:
            self.remaining_time = data["remainingTime"]
        if "temperature" in data:
            self.current_temp = data["temperature"]
        if "humidity" in data:
            self.humidity = data["humidity"]
        if "timestamp" in data:
            self.latest_update = data["timestamp"]
        if "statusCodes" in data:
            if data["statusCodes"] != self.status_codes:
                logger.debug(f"StatusCodes changed: {data['statusCodes']}")
            self.status_codes = data["statusCodes"]
        if "heatOn" in data:
            heat_on = bool(data["heatOn"])
            if heat_on != self.active:
                logger.info(
                    f"Heat-on flag ({heat_on}) differs from active state ({self.active})"
                )
                if heat_on:
                    self.active = True

        if self.current_temp != prev_temp:
            logger.info(
                f"Current temperature changed: {prev_temp}\u00b0C \u2192 {self.current_temp}\u00b0C"
            )
        if self.target_temp != prev_target:
            logger.info(
                f"Target temperature changed: {prev_target}\u00b0C \u2192 {self.target_temp}\u00b0C"
            )
        if self.active != prev_active:
            logger.info(
                f"Power state changed: {'ON' if prev_active else 'OFF'} \u2192 {'ON' if self.active else 'OFF'}"
            )

        for callback in self.update_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in update callback: {e}")

        return True

    async def start_websockets(self):
        """Start the websocket connections for device and data updates."""
        self.data_websocket = HarviaWebsocket(self.api, self, "data")
        asyncio.create_task(self.data_websocket.start())

        self.device_websocket = HarviaWebsocket(self.api, self, "device")
        asyncio.create_task(self.device_websocket.start())

        return True

    def add_update_callback(self, callback):
        """Add a callback to be called when the device is updated."""
        if callback not in self.update_callbacks:
            self.update_callbacks.append(callback)

    def remove_update_callback(self, callback):
        """Remove an update callback."""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)

    async def set_state(self, payload):
        """Set device state with a given payload."""
        for key, value in payload.items():
            if key == "targetTemp":
                self.target_temp = value
                logger.info(
                    f"Immediately updating local target temperature to {value}\u00b0C"
                )
            elif key == "targetRh":
                self.target_rh = value
                logger.info(
                    f"Immediately updating local target humidity to {value}%"
                )
            elif key == "active":
                self.active = bool(value)
                logger.info(
                    f"Immediately updating local power state to {'ON' if bool(value) else 'OFF'}"
                )
            elif key == "light":
                self.lights_on = bool(value)
                logger.info(
                    f"Immediately updating local light state to {'ON' if bool(value) else 'OFF'}"
                )
            elif key == "fan":
                self.fan_on = bool(value)
                logger.info(
                    f"Immediately updating local fan state to {'ON' if bool(value) else 'OFF'}"
                )
            elif key == "steamEn":
                self.steam_on = bool(value)
                logger.info(
                    f"Immediately updating local steam state to {'ON' if bool(value) else 'OFF'}"
                )

        for callback in self.update_callbacks:
            try:
                callback(self)
            except Exception as e:
                logger.error(f"Error in callback after local state update: {e}")

        def run_api_call():
            async def do_api_call():
                try:
                    logger.info(
                        f"Sending API request with payload: {json.dumps(payload)}"
                    )
                    result = await self.api.device_mutation(self.id, payload)
                    logger.info(f"API request completed. Result: {result}")
                    return result
                except Exception as e:
                    logger.error(f"API request failed: {e}")
                    return False

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(do_api_call())
            finally:
                loop.close()

        thread = threading.Thread(target=run_api_call)
        thread.daemon = True
        thread.start()

        return True

    async def set_target_temperature(self, temp: int):
        """Set the target temperature."""
        logger.info(f"Setting target temperature to {temp}\u00b0C")
        try:
            return await self.set_state({"targetTemp": temp})
        except Exception as e:
            logger.error(f"Failed to set temperature: {e}")
            self.target_temp = temp
            for callback in self.update_callbacks:
                try:
                    callback(self)
                except Exception as callback_error:
                    logger.error(
                        f"Error in callback after temperature update: {callback_error}"
                    )
            return False

    async def set_target_relative_humidity(self, rh: int):
        """Set the target relative humidity."""
        try:
            return await self.set_state({"targetRh": rh})
        except Exception as e:
            logger.error(f"Failed to set humidity: {e}")
            return None

    async def set_fan(self, state: bool):
        """Set the fan state."""
        try:
            return await self.set_state({"fan": int(state)})
        except Exception as e:
            logger.error(f"Failed to set fan: {e}")
            return None

    async def set_lights(self, state: bool):
        """Set the lights state."""
        try:
            return await self.set_state({"light": int(state)})
        except Exception as e:
            logger.error(f"Failed to set lights: {e}")
            return None

    async def set_steamer(self, state: bool):
        """Set the steamer state."""
        try:
            return await self.set_state({"steamEn": int(state)})
        except Exception as e:
            logger.error(f"Failed to set steamer: {e}")
            return None

    async def set_active(self, state: bool):
        """Set the power state."""
        state_int = int(state)
        logger.info(
            f"Setting power state to {'ON' if state else 'OFF'} (value: {state_int})"
        )
        try:
            return await self.set_state({"active": state_int})
        except Exception as e:
            logger.error(f"Failed to set power state: {e}")
            self.active = state
            for callback in self.update_callbacks:
                try:
                    callback(self)
                except Exception as callback_error:
                    logger.error(
                        f"Error in callback after power state update: {callback_error}"
                    )
            return False

    def get_door_state(self):
        """Get the door state (open/closed) from status codes."""
        if not self.status_codes:
            return False

        try:
            safety_status = int(str(self.status_codes)[1])
            return safety_status == 9
        except (IndexError, ValueError):
            return False

    async def process_state_update(self, data):
        """Process device state update from WebSocket."""
        if not data:
            logger.warning("Received empty state update")
            return False

        logger.debug(f"Processing device state update: {json.dumps(data)}")
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
        self.session_id = (
            f"{self.endpoint_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

    async def start(self):
        """Start the websocket."""
        self.running = True
        ws_logger.info(
            f"Starting WebSocket {self.session_id} for device {self.device.id}"
        )

        while self.running:
            try:
                ws_logger.info(f"Connecting WebSocket {self.session_id}")
                await self.connect()

                ws_logger.info(
                    f"Creating subscription for WebSocket {self.session_id}"
                )
                await self.create_subscription()

                ws_logger.info(
                    f"Starting message reception loop for WebSocket {self.session_id}"
                )
                await self.receive_messages()
            except Exception as e:
                logger.error(f"Websocket error ({self.endpoint_type}): {e}")
                ws_logger.error(f"WebSocket {self.session_id} error: {e}")
                ws_logger.info(
                    f"Will attempt to reconnect WebSocket {self.session_id} in 5 seconds"
                )
                await asyncio.sleep(5)

    async def connect(self):
        """Connect to the websocket."""
        try:
            websock_url = await self.api.getWebsockUrlByEndpoint(self.endpoint_type)
            logger.debug(
                f"Connecting to {self.endpoint_type} websocket: {websock_url}"
            )
            ws_logger.debug(f"WebSocket {self.session_id} URL: {websock_url}")

            truncated_url = (
                websock_url[:100] + "..."
                if len(websock_url) > 100
                else websock_url
            )
            ws_logger.info(
                f"Connecting to WebSocket {self.session_id} URL: {truncated_url}"
            )

            self.websocket = await websockets.connect(
                websock_url,
                subprotocols=["graphql-ws"],
                max_size=None,
            )

            connection_init = {"type": "connection_init"}
            connection_init_str = json.dumps(connection_init)
            ws_logger.debug(
                f"WebSocket {self.session_id} sending init: {connection_init_str}"
            )
            await self.websocket.send(connection_init_str)

            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
                ws_logger.debug(f"WebSocket {self.session_id} received: {response}")
                data = json.loads(response)

                if data.get("type") == "connection_ack":
                    self.connection_id = data.get("payload", {}).get("connectionId")
                    logger.info(
                        f"Connected to {self.endpoint_type} websocket. Connection ID: {self.connection_id}"
                    )
                    ws_logger.info(
                        f"WebSocket {self.session_id} connected. Connection ID: {self.connection_id}"
                    )
                    return True
                elif data.get("type") == "connection_error":
                    error_details = (
                        data.get("payload", {})
                        .get("errors", [{}])[0]
                        .get("message", "Unknown error")
                    )
                    logger.error(f"Connection error: {error_details}")
                    ws_logger.error(
                        f"WebSocket {self.session_id} connection error: {error_details}"
                    )
                    return False
                else:
                    logger.error(f"Failed to receive connection ack: {data}")
                    ws_logger.error(
                        f"WebSocket {self.session_id} failed to receive connection ack: {data}"
                    )
                    return False
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for connection acknowledgment")
                ws_logger.error(
                    f"WebSocket {self.session_id} timeout waiting for connection acknowledgment"
                )
                return False
        except Exception as e:
            logger.error(
                f"Failed to connect to {self.endpoint_type} websocket: {e}"
            )
            ws_logger.error(
                f"WebSocket {self.session_id} connection exception: {e}"
            )
            raise

    async def create_subscription(self):
        """Create a websocket subscription."""
        try:
            if self.endpoint_type == "data":
                message_data = await self.create_data_subscription_message()
            else:
                message_data = await self.create_device_subscription_message()

            self.registration_id = str(uuid.uuid4())

            subscription_message = {
                "id": self.registration_id,
                "payload": {
                    "data": message_data,
                    "extensions": {
                        "authorization": {
                            "Authorization": await self.api.getIdToken(),
                            "host": (
                                await self.api.getWebsocketEndpoint(
                                    self.endpoint_type
                                )
                            )["host"],
                            "x-amz-user-agent": "aws-amplify/2.0.5 react-native",
                        }
                    },
                },
                "type": "start",
            }

            subscription_str = json.dumps(subscription_message)
            ws_logger.debug(
                f"WebSocket {self.session_id} sending subscription: {subscription_str}"
            )
            await self.websocket.send(subscription_str)

            try:
                response = await asyncio.wait_for(self.websocket.recv(), timeout=5.0)
                ws_logger.debug(
                    f"WebSocket {self.session_id} received subscription response: {response}"
                )
                data = json.loads(response)

                if data.get("type") == "start_ack":
                    logger.info(
                        f"Subscription created for {self.endpoint_type} websocket with start_ack"
                    )
                    ws_logger.info(
                        f"WebSocket {self.session_id} subscription created with start_ack"
                    )
                    return True
                elif data.get("type") == "ka":
                    logger.info(
                        f"Subscription likely created for {self.endpoint_type} websocket (received keep-alive)"
                    )
                    ws_logger.info(
                        f"WebSocket {self.session_id} subscription likely created (received keep-alive)"
                    )

                    try:
                        second_response = await asyncio.wait_for(
                            self.websocket.recv(), timeout=2.0
                        )
                        ws_logger.debug(
                            f"WebSocket {self.session_id} received second response: {second_response}"
                        )
                        second_data = json.loads(second_response)

                        if second_data.get("type") == "start_ack":
                            logger.info(
                                f"Subscription confirmed for {self.endpoint_type} websocket with delayed start_ack"
                            )
                            ws_logger.info(
                                f"WebSocket {self.session_id} subscription confirmed with delayed start_ack"
                            )
                    except (asyncio.TimeoutError, json.JSONDecodeError):
                        pass

                    return True
                elif data.get("type") == "error":
                    error_msg = data.get("payload", {}).get(
                        "message", "Unknown error"
                    )
                    logger.error(f"Subscription error: {error_msg}")
                    ws_logger.error(
                        f"WebSocket {self.session_id} subscription error: {error_msg}"
                    )
                    return False
                else:
                    logger.error(f"Unexpected subscription response: {data}")
                    ws_logger.error(
                        f"WebSocket {self.session_id} unexpected subscription response: {data}"
                    )
                    return False
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for subscription acknowledgment")
                ws_logger.error(
                    f"WebSocket {self.session_id} timeout waiting for subscription ack"
                )
                return False

        except Exception as e:
            logger.error(f"Failed to create subscription: {e}")
            ws_logger.error(
                f"WebSocket {self.session_id} failed to create subscription: {e}"
            )
            return False

    async def create_data_subscription_message(self):
        """Create a data subscription message."""
        ws_logger.debug(
            f"Creating data subscription message for device {self.device.id}"
        )

        organization_id = await self.api.get_organization_id()

        if not organization_id:
            organization_id = "5d34705e-278d-4de7-84b2-4b515db39c55"
            ws_logger.warning(
                f"Using fallback organization ID {organization_id} for subscription"
            )
        else:
            ws_logger.info(
                f"Using organization ID {organization_id} from API for subscription"
            )

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
            "variables": {"receiver": organization_id},
        }

        return json.dumps(subscription_data)

    async def create_device_subscription_message(self):
        """Create a device subscription message."""
        ws_logger.debug(
            f"Creating device subscription message for device {self.device.id}"
        )

        organization_id = await self.api.get_organization_id()

        if not organization_id:
            organization_id = "5d34705e-278d-4de7-84b2-4b515db39c55"
            ws_logger.warning(
                f"Using fallback organization ID {organization_id} for subscription"
            )
        else:
            ws_logger.info(
                f"Using organization ID {organization_id} from API for subscription"
            )

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
            "variables": {"receiver": organization_id},
        }

        return json.dumps(subscription_data)

    async def receive_messages(self):
        """Receive and process messages from the websocket."""
        ws_logger.info(f"WebSocket {self.session_id} entering receive loop")
        while self.running and self.websocket:
            try:
                message = await self.websocket.recv()
                ws_logger.debug(
                    f"WebSocket {self.session_id} received message: {message}"
                )
                await self.handle_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                logger.info(
                    f"{self.endpoint_type} websocket connection closed. Reconnecting..."
                )
                ws_logger.info(
                    f"WebSocket {self.session_id} connection closed ({e.code}: {e.reason}). Reconnecting..."
                )
                break
            except Exception as e:
                logger.error(
                    f"Error receiving {self.endpoint_type} websocket message: {e}"
                )
                ws_logger.error(f"WebSocket {self.session_id} receive error: {e}")
                break

        ws_logger.info(f"WebSocket {self.session_id} exited receive loop")

    async def handle_message(self, message):
        """Handle a message from the websocket."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "ka":
                ws_logger.debug(
                    f"WebSocket {self.session_id} received keep-alive"
                )
                return

            elif msg_type == "start_ack":
                ws_logger.debug(
                    f"WebSocket {self.session_id} received subscription acknowledgment"
                )
                return

            elif msg_type == "error":
                ws_logger.error(
                    f"WebSocket {self.session_id} received error: {data}"
                )

                if "payload" in data and "errors" in data["payload"]:
                    for error in data["payload"]["errors"]:
                        error_type = error.get("errorType", "Unknown")
                        error_message = error.get("message", "No message")
                        ws_logger.error(
                            f"WebSocket {self.session_id} error: {error_type} - {error_message}"
                        )

                        if error_type == "Unauthorized":
                            ws_logger.warning(
                                f"WebSocket {self.session_id} received unauthorized error, re-authenticating"
                            )
                            await self.api.authenticate()
                            self.websocket.close()
                            return
                else:
                    ws_logger.error(
                        f"WebSocket {self.session_id} received error without details: {data}"
                    )

                return

            elif msg_type == "data":
                ws_logger.debug(
                    f"WebSocket {self.session_id} received data update"
                )

                if not data.get("payload") or not data["payload"].get("data"):
                    ws_logger.warning(
                        f"WebSocket {self.session_id} received malformed data message: {data}"
                    )
                    return

                if (
                    self.endpoint_type == "device"
                    and "onStateUpdated" in data["payload"]["data"]
                ):
                    state_data = data["payload"]["data"]["onStateUpdated"]

                    if "reported" in state_data and state_data["reported"]:
                        try:
                            reported_data = json.loads(state_data["reported"])
                            ws_logger.info(
                                f"WebSocket {self.session_id} processing device state update"
                            )

                            if "active" in reported_data:
                                ws_logger.info(
                                    f"Received active state: {reported_data['active']} (type: {type(reported_data['active']).__name__})"
                                )

                            if (
                                "deviceId" in reported_data
                                and reported_data["deviceId"] == self.device.id
                            ):
                                await self.device.process_state_update(
                                    reported_data
                                )
                            else:
                                ws_logger.debug(
                                    f"WebSocket {self.session_id} ignoring update for different device: {reported_data.get('deviceId', 'unknown')}"
                                )
                        except json.JSONDecodeError:
                            ws_logger.error(
                                f"WebSocket {self.session_id} failed to parse reported state: {state_data['reported']}"
                            )

                elif (
                    self.endpoint_type == "data"
                    and "onDataUpdates" in data["payload"]["data"]
                ):
                    update_data = data["payload"]["data"]["onDataUpdates"]

                    if "item" in update_data and update_data["item"]:
                        item = update_data["item"]

                        if (
                            "deviceId" in item
                            and item["deviceId"] == self.device.id
                        ):
                            if "data" in item and item["data"]:
                                try:
                                    device_data = json.loads(item["data"])
                                    device_data["timestamp"] = item.get(
                                        "timestamp"
                                    )
                                    device_data["deviceId"] = item.get(
                                        "deviceId"
                                    )

                                    ws_logger.info(
                                        f"WebSocket {self.session_id} processing data update"
                                    )
                                    await self.device.process_data_update(
                                        device_data
                                    )
                                except json.JSONDecodeError:
                                    ws_logger.error(
                                        f"WebSocket {self.session_id} failed to parse data: {item['data']}"
                                    )
                        else:
                            ws_logger.debug(
                                f"WebSocket {self.session_id} ignoring update for different device: {item.get('deviceId', 'unknown')}"
                            )
            else:
                ws_logger.debug(
                    f"WebSocket {self.session_id} unhandled message type: {msg_type}"
                )

        except json.JSONDecodeError:
            ws_logger.error(
                f"WebSocket {self.session_id} failed to parse message: {message}"
            )
        except Exception as e:
            ws_logger.error(
                f"WebSocket {self.session_id} error handling message: {e}"
            )

    async def stop(self):
        """Stop the websocket connection."""
        logger.info(f"Stopping {self.endpoint_type} websocket connection")
        ws_logger.info(f"Stopping WebSocket {self.session_id}")

        self.running = False

        if self.websocket:
            try:
                if self.registration_id:
                    stop_message = {
                        "id": self.registration_id,
                        "type": "stop",
                    }
                    stop_str = json.dumps(stop_message)
                    ws_logger.debug(
                        f"WebSocket {self.session_id} sending stop: {stop_str}"
                    )
                    await self.websocket.send(stop_str)

                await self.websocket.close()
                ws_logger.info(f"WebSocket {self.session_id} closed")
            except Exception as e:
                logger.error(
                    f"Error closing {self.endpoint_type} websocket: {e}"
                )
                ws_logger.error(
                    f"WebSocket {self.session_id} close error: {e}"
                )

            self.websocket = None
