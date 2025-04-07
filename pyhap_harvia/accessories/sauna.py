import logging
import asyncio
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_THERMOSTAT
from pyhap.accessory_driver import AccessoryDriver

logger = logging.getLogger("harvia_sauna")

class HarviaSaunaAccessory(Accessory):
    """Harvia Sauna HomeKit accessory implementation"""
    category = CATEGORY_THERMOSTAT

    def __init__(self, driver: AccessoryDriver, device, *args, **kwargs):
        """Initialize the sauna accessory"""
        super().__init__(driver, device.name, *args, **kwargs)
        self.device = device

        # Add services to the accessory
        self._setup_thermostat_service()
        self._setup_fan_service()
        self._setup_light_service()
        self._setup_door_sensor_service()
        self._setup_steamer_service()

        # Register update callback
        self.device.add_update_callback(self.update_state)

    def _setup_thermostat_service(self):
        """Set up the thermostat service for temperature control"""
        thermostat_service = self.add_preload_service('Thermostat')
        
        # Current temperature characteristic
        self.current_temp_char = thermostat_service.configure_char(
            'CurrentTemperature',
            value=self.device.current_temp or 25.0,
            properties={'minValue': 0, 'maxValue': 120}
        )
        
        # Target temperature characteristic
        self.target_temp_char = thermostat_service.configure_char(
            'TargetTemperature',
            value=self.device.target_temp or 60.0,
            properties={'minValue': 40, 'maxValue': 110}
        )
        self.target_temp_char.setter_callback = self.set_target_temperature
        
        # Temperature display units
        thermostat_service.configure_char(
            'TemperatureDisplayUnits',
            value=0  # Celsius
        )
        
        # Heating/cooling mode
        self.current_mode_char = thermostat_service.configure_char(
            'CurrentHeatingCoolingState',
            value=1 if self.device.active else 0  # 0=off, 1=heat
        )
        
        # Target mode
        self.target_mode_char = thermostat_service.configure_char(
            'TargetHeatingCoolingState',
            value=1 if self.device.active else 0  # 0=off, 1=heat
        )
        self.target_mode_char.setter_callback = self.set_heating_cooling_mode

    def _setup_fan_service(self):
        """Set up the fan service"""
        fan_service = self.add_preload_service('Fanv2')
        
        # Active characteristic
        self.fan_active_char = fan_service.configure_char(
            'Active',
            value=1 if self.device.fan_on else 0  # 0=inactive, 1=active
        )
        self.fan_active_char.setter_callback = self.set_fan_active

    def _setup_light_service(self):
        """Set up the light service"""
        light_service = self.add_preload_service('Lightbulb')
        
        # On characteristic
        self.light_on_char = light_service.configure_char(
            'On',
            value=self.device.lights_on
        )
        self.light_on_char.setter_callback = self.set_light_on

    def _setup_door_sensor_service(self):
        """Set up the door sensor service"""
        door_service = self.add_preload_service('ContactSensor')
        
        # Contact state characteristic (1=open, 0=closed)
        self.door_state_char = door_service.configure_char(
            'ContactSensorState',
            value=1 if self.device.get_door_state() else 0
        )

    def _setup_steamer_service(self):
        """Set up the steamer service"""
        # Using a switch service for the steamer
        steamer_service = self.add_preload_service('Switch', 'Steamer')
        
        # On characteristic
        self.steamer_on_char = steamer_service.configure_char(
            'On',
            value=self.device.steam_on
        )
        self.steamer_on_char.setter_callback = self.set_steamer_on

    async def set_target_temperature_async(self, value):
        """Set the target temperature asynchronously"""
        logger.info(f"Setting target temperature to {value}")
        await self.device.set_target_temperature(value)

    def set_target_temperature(self, value):
        """Set the target temperature"""
        logger.info(f"Setting target temperature to {value}")
        asyncio.create_task(self.set_target_temperature_async(value))

    async def set_heating_cooling_mode_async(self, value):
        """Set the heating/cooling mode asynchronously"""
        # 0=off, 1=heat
        state = value > 0
        logger.info(f"Setting heating mode to {state}")
        await self.device.set_active(state)

    def set_heating_cooling_mode(self, value):
        """Set the heating/cooling mode"""
        asyncio.create_task(self.set_heating_cooling_mode_async(value))

    async def set_fan_active_async(self, value):
        """Set the fan active state asynchronously"""
        # 0=inactive, 1=active
        state = value > 0
        logger.info(f"Setting fan to {state}")
        await self.device.set_fan(state)

    def set_fan_active(self, value):
        """Set the fan active state"""
        asyncio.create_task(self.set_fan_active_async(value))

    async def set_light_on_async(self, value):
        """Set the light on state asynchronously"""
        logger.info(f"Setting light to {value}")
        await self.device.set_lights(value)

    def set_light_on(self, value):
        """Set the light on state"""
        asyncio.create_task(self.set_light_on_async(value))

    async def set_steamer_on_async(self, value):
        """Set the steamer on state asynchronously"""
        logger.info(f"Setting steamer to {value}")
        await self.device.set_steamer(value)

    def set_steamer_on(self, value):
        """Set the steamer on state"""
        asyncio.create_task(self.set_steamer_on_async(value))

    def update_state(self, device):
        """Update the accessory state from the device state"""
        try:
            # Update thermostat
            if device.current_temp is not None:
                self.current_temp_char.set_value(device.current_temp)
            
            if device.target_temp is not None:
                self.target_temp_char.set_value(device.target_temp)
            
            is_active = device.active
            
            # Current mode (0=off, 1=heat)
            self.current_mode_char.set_value(1 if is_active else 0)
            
            # Target mode (0=off, 1=heat)
            self.target_mode_char.set_value(1 if is_active else 0)
            
            # Fan state
            self.fan_active_char.set_value(1 if device.fan_on else 0)
            
            # Light state
            self.light_on_char.set_value(device.lights_on)
            
            # Door state
            door_state = device.get_door_state()
            self.door_state_char.set_value(1 if door_state else 0)
            
            # Steamer state
            self.steamer_on_char.set_value(device.steam_on)
            
            logger.debug(f"Updated HomeKit accessory state for {device.name}")
        except Exception as e:
            logger.error(f"Error updating HomeKit accessory state: {str(e)}")

    def stop(self):
        """Stop the accessory and clean up"""
        logger.info("Stopping Harvia Sauna accessory")
        self.device.remove_update_callback(self.update_state)
        super().stop() 