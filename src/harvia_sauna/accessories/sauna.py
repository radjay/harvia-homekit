"""Harvia Sauna HomeKit accessory implementation."""

import asyncio
import logging
import threading

from pyhap.accessory import Accessory
from pyhap.accessory_driver import AccessoryDriver
from pyhap.const import CATEGORY_THERMOSTAT

logger = logging.getLogger("harvia_sauna")


class HarviaSaunaAccessory(Accessory):
    """Harvia Sauna HomeKit accessory implementation."""

    category = CATEGORY_THERMOSTAT

    def __init__(self, driver: AccessoryDriver, device, *args, **kwargs):
        """Initialize the sauna accessory."""
        super().__init__(driver, device.name, *args, **kwargs)
        self.device = device

        self._setup_thermostat_service()

        self.device.add_update_callback(self.update_state)

    def _setup_thermostat_service(self):
        """Set up the thermostat service for temperature control."""
        thermostat_service = self.add_preload_service("Thermostat")

        default_current_temp = 20.0
        current_temp = (
            self.device.current_temp
            if self.device.current_temp is not None
            else default_current_temp
        )
        logger.info(
            f"Setting up thermostat service with current temperature: {current_temp}\u00b0C "
            f"(device reports: {self.device.current_temp}\u00b0C)"
        )

        self.current_temp_char = thermostat_service.configure_char(
            "CurrentTemperature",
            value=current_temp,
            properties={"minValue": 0, "maxValue": 120},
        )

        default_target_temp = 60.0
        target_temp = (
            self.device.target_temp
            if self.device.target_temp is not None
            else default_target_temp
        )
        logger.info(
            f"Setting up thermostat service with target temperature: {target_temp}\u00b0C "
            f"(device reports: {self.device.target_temp}\u00b0C)"
        )

        self.target_temp_char = thermostat_service.configure_char(
            "TargetTemperature",
            value=target_temp,
            properties={"minValue": 40, "maxValue": 110},
        )

        self.target_temp_char.setter_callback = self.set_target_temperature

        thermostat_service.configure_char("TemperatureDisplayUnits", value=0)

        self.current_mode_char = thermostat_service.configure_char(
            "CurrentHeatingCoolingState",
            value=1 if self.device.active else 0,
            properties={"validValues": [0, 1], "minValue": 0, "maxValue": 1},
        )

        self.target_mode_char = thermostat_service.configure_char(
            "TargetHeatingCoolingState",
            value=1 if self.device.active else 0,
            properties={"validValues": [0, 1], "minValue": 0, "maxValue": 1},
        )

        self.target_mode_char.setter_callback = self.set_heating_cooling_mode

    def _setup_light_service(self):
        """Set up the light service (for future use)."""
        light_service = self.add_preload_service("Lightbulb")

        self.light_on_char = light_service.configure_char(
            "On", value=self.device.lights_on
        )
        self.light_on_char.setter_callback = self.set_light_on

    def set_target_temperature(self, value):
        """Set target temperature."""
        logger.info(f"HomeKit requesting to set target temperature to: {value}\u00b0C")

        self.target_temp_char.set_value(value)

        def handle_temp_change():
            async def async_set_temp():
                try:
                    logger.info(f"Setting sauna temperature to: {value}\u00b0C")
                    result = await self.device.set_target_temperature(value)
                    if result:
                        logger.info(f"Successfully set temperature to {value}\u00b0C")
                    else:
                        logger.error(f"Failed to set temperature to {value}\u00b0C")
                except Exception as e:
                    logger.error(f"Error setting temperature: {e}")

                self.target_temp_char.set_value(self.device.target_temp)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(async_set_temp())
            except Exception as e:
                logger.error(f"Thread error setting temperature: {e}")
            finally:
                loop.close()

        thread = threading.Thread(target=handle_temp_change)
        thread.daemon = True
        thread.start()

    def set_heating_cooling_mode(self, value):
        """Set heating cooling mode."""
        logger.info(f"HomeKit requesting to set heating mode to: {value}")

        self.target_mode_char.set_value(value)

        active = value == 1

        def handle_mode_change():
            async def async_set_mode():
                try:
                    logger.info(
                        f"Setting sauna power to: {'ON' if active else 'OFF'}"
                    )
                    result = await self.device.set_active(active)
                    if result:
                        logger.info(
                            f"Successfully set power state to {'ON' if active else 'OFF'}"
                        )
                    else:
                        logger.error(
                            f"Failed to set power state to {'ON' if active else 'OFF'}"
                        )
                except Exception as e:
                    logger.error(f"Error setting power state: {e}")

                self.target_mode_char.set_value(
                    1 if self.device.active else 0
                )
                self.current_mode_char.set_value(
                    1 if self.device.active else 0
                )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(async_set_mode())
            except Exception as e:
                logger.error(f"Thread error setting mode: {e}")
            finally:
                loop.close()

        thread = threading.Thread(target=handle_mode_change)
        thread.daemon = True
        thread.start()

    def set_light_on(self, value):
        """Set the light on state (for future use)."""
        logger.info(f"Setting light to {value}")

        def make_request():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:

                async def do_request():
                    try:
                        await self.device.set_lights(value)
                        return True
                    except Exception as e:
                        logger.error(f"Error setting light: {e}")
                        self.device.lights_on = value
                        return False

                return loop.run_until_complete(do_request())
            finally:
                loop.close()

        threading.Thread(target=make_request).start()

    def update_state(self, device):
        """Update the accessory state from the device state."""
        try:
            if device.current_temp is not None:
                logger.info(
                    f"Updating current temperature to {device.current_temp}\u00b0C"
                )
                self.current_temp_char.set_value(device.current_temp)
            else:
                logger.warning("Current temperature is None, not updating HomeKit")

            if device.target_temp is not None:
                logger.info(
                    f"Updating target temperature to {device.target_temp}\u00b0C"
                )
                self.target_temp_char.set_value(device.target_temp)
            else:
                logger.warning("Target temperature is None, not updating HomeKit")

            is_active = device.active
            logger.info(
                f"Updating power state to: {'ON' if is_active else 'OFF'}"
            )

            self.current_mode_char.set_value(1 if is_active else 0)
            self.target_mode_char.set_value(1 if is_active else 0)

            logger.info(f"Updated HomeKit accessory state for {device.name}")
        except Exception as e:
            logger.error(f"Error updating HomeKit accessory state: {e}")

    def stop(self):
        """Stop the accessory and clean up."""
        logger.info("Stopping Harvia Sauna accessory")
        self.device.remove_update_callback(self.update_state)

        parent_stop = super().stop
        if asyncio.iscoroutinefunction(parent_stop):

            def run_async_stop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(parent_stop())
                finally:
                    loop.close()

            thread = threading.Thread(target=run_async_stop)
            thread.daemon = True
            thread.start()
        else:
            parent_stop()
