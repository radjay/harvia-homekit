import logging
import asyncio
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_THERMOSTAT
from pyhap.accessory_driver import AccessoryDriver
import threading
from pyhap import loader

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
        
        # Light service - commented out for future use
        # self._setup_light_service()
        
        # Removed: Fan, Door sensor, and Steamer services
        
        # Register update callback
        self.device.add_update_callback(self.update_state)

    def _setup_thermostat_service(self):
        """Set up the thermostat service for temperature control"""
        thermostat_service = self.add_preload_service('Thermostat')
        
        # Use actual temperatures if available, otherwise reasonable defaults
        default_current_temp = 20.0  # More realistic room temperature default
        current_temp = self.device.current_temp if self.device.current_temp is not None else default_current_temp
        logger.info(f"Setting up thermostat service with current temperature: {current_temp}°C (device reports: {self.device.current_temp}°C)")
        
        # Current temperature characteristic
        self.current_temp_char = thermostat_service.configure_char(
            'CurrentTemperature',
            value=current_temp,
            properties={'minValue': 0, 'maxValue': 120}
        )
        
        # Use actual target temperature if available
        default_target_temp = 60.0  # Default sauna temperature
        target_temp = self.device.target_temp if self.device.target_temp is not None else default_target_temp
        logger.info(f"Setting up thermostat service with target temperature: {target_temp}°C (device reports: {self.device.target_temp}°C)")
        
        # Target temperature characteristic
        self.target_temp_char = thermostat_service.configure_char(
            'TargetTemperature',
            value=target_temp,
            properties={'minValue': 40, 'maxValue': 110}
        )
        
        # Explicitly set the callback
        self.target_temp_char.setter_callback = self.set_target_temperature
        
        # Temperature display units
        thermostat_service.configure_char(
            'TemperatureDisplayUnits',
            value=0  # Celsius
        )
        
        # Current Heating/Cooling state - only allow Off and Heat
        self.current_mode_char = thermostat_service.configure_char(
            'CurrentHeatingCoolingState',
            value=1 if self.device.active else 0,  # 0=off, 1=heat
            properties={'validValues': [0, 1], 'minValue': 0, 'maxValue': 1}  # Only allow Off and Heat states
        )
        
        # Target Heating/Cooling state - only allow Off and Heat
        self.target_mode_char = thermostat_service.configure_char(
            'TargetHeatingCoolingState',
            value=1 if self.device.active else 0,  # 0=off, 1=heat
            properties={'validValues': [0, 1], 'minValue': 0, 'maxValue': 1}  # Only allow Off and Heat states
        )
        
        # Explicitly set the callback
        self.target_mode_char.setter_callback = self.set_heating_cooling_mode

    def _setup_light_service(self):
        """Set up the light service (for future use)"""
        light_service = self.add_preload_service('Lightbulb')
        
        # On characteristic
        self.light_on_char = light_service.configure_char(
            'On',
            value=self.device.lights_on
        )
        self.light_on_char.setter_callback = self.set_light_on

    async def set_target_temperature_async(self, value):
        """Set the target temperature asynchronously"""
        logger.info(f"Setting target temperature to {value}")
        await self.device.set_target_temperature(value)

    def set_target_temperature(self, value):
        """Set target temperature"""
        logger.info(f"HomeKit requesting to set target temperature to: {value}°C")
        
        # Update the internal characteristic immediately for HomeKit responsiveness
        self.target_temp_char.set_value(value)
        
        # Set up a background task to handle the API call
        def handle_temp_change():
            async def async_set_temp():
                try:
                    logger.info(f"Setting sauna temperature to: {value}°C")
                    result = await self.device.set_target_temperature(value)
                    if result:
                        logger.info(f"Successfully set temperature to {value}°C")
                    else:
                        logger.error(f"Failed to set temperature to {value}°C")
                except Exception as e:
                    logger.error(f"Error setting temperature: {str(e)}")
                    
                # Update HomeKit state based on device state after the operation
                self.target_temp_char.set_value(self.device.target_temp)
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(async_set_temp())
            except Exception as e:
                logger.error(f"Thread error setting temperature: {str(e)}")
            finally:
                loop.close()
        
        # Start a daemon thread to handle the async operation
        thread = threading.Thread(target=handle_temp_change)
        thread.daemon = True
        thread.start()

    async def set_heating_cooling_mode_async(self, value):
        """Set the heating/cooling mode asynchronously"""
        # 0=off, 1=heat
        state = value > 0
        logger.info(f"Setting heating mode to {state}")
        await self.device.set_active(state)

    def set_heating_cooling_mode(self, value):
        """Set heating cooling mode"""
        logger.info(f"HomeKit requesting to set heating mode to: {value}")
        
        # Update the internal characteristic immediately for HomeKit responsiveness
        self.target_mode_char.set_value(value)
        
        # If value is 0 (off), turn off the sauna. If value is 1 (heat), turn on sauna.
        active = (value == 1)
        
        # Set up a background task to handle the API call
        def handle_mode_change():
            async def async_set_mode():
                try:
                    logger.info(f"Setting sauna power to: {'ON' if active else 'OFF'}")
                    result = await self.device.set_active(active)
                    if result:
                        logger.info(f"Successfully set power state to {'ON' if active else 'OFF'}")
                    else:
                        logger.error(f"Failed to set power state to {'ON' if active else 'OFF'}")
                except Exception as e:
                    logger.error(f"Error setting power state: {str(e)}")
                    
                # Update HomeKit state based on device state after the operation
                # This ensures consistency between HomeKit and the actual device
                self.target_mode_char.set_value(1 if self.device.active else 0)
                self.current_mode_char.set_value(1 if self.device.active else 0)
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(async_set_mode())
            except Exception as e:
                logger.error(f"Thread error setting mode: {str(e)}")
            finally:
                loop.close()
        
        # Start a daemon thread to handle the async operation
        thread = threading.Thread(target=handle_mode_change)
        thread.daemon = True
        thread.start()

    async def set_light_on_async(self, value):
        """Set the light on state asynchronously (for future use)"""
        logger.info(f"Setting light to {value}")
        await self.device.set_lights(value)

    def set_light_on(self, value):
        """Set the light on state (for future use)"""
        logger.info(f"Setting light to {value}")
        
        # Define a synchronous function that we can call
        def make_request():
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Define a simple coroutine that we'll run
                async def do_request():
                    try:
                        await self.device.set_lights(value)
                        return True
                    except Exception as e:
                        logger.error(f"Error setting light: {str(e)}")
                        # Still update local state for HomeKit display
                        self.device.lights_on = value
                        return False
                
                # Run the coroutine until complete
                return loop.run_until_complete(do_request())
            finally:
                loop.close()
        
        # Run the request in a thread so it doesn't block HomeKit
        threading.Thread(target=make_request).start()

    def update_state(self, device):
        """Update the accessory state from the device state"""
        try:
            # Update thermostat
            if device.current_temp is not None:
                logger.info(f"Updating current temperature to {device.current_temp}°C")
                self.current_temp_char.set_value(device.current_temp)
            else:
                logger.warning("Current temperature is None, not updating HomeKit")
            
            if device.target_temp is not None:
                logger.info(f"Updating target temperature to {device.target_temp}°C")
                self.target_temp_char.set_value(device.target_temp)
            else:
                logger.warning("Target temperature is None, not updating HomeKit")
            
            is_active = device.active
            logger.info(f"Updating power state to: {'ON' if is_active else 'OFF'}")
            
            # Always update the power state first to ensure correct HomeKit display
            # Current mode (0=off, 1=heat)
            self.current_mode_char.set_value(1 if is_active else 0)
            
            # Target mode (0=off, 1=heat)
            self.target_mode_char.set_value(1 if is_active else 0)
            
            # Light state - commented out for future use
            # if hasattr(self, 'light_on_char'):
            #     self.light_on_char.set_value(device.lights_on)
            
            logger.info(f"Updated HomeKit accessory state for {device.name}")
        except Exception as e:
            logger.error(f"Error updating HomeKit accessory state: {str(e)}")

    def stop(self):
        """Stop the accessory and clean up"""
        logger.info("Stopping Harvia Sauna accessory")
        self.device.remove_update_callback(self.update_state)
        
        # The parent stop may be a coroutine in newer HAP-python versions
        # We'll handle it properly based on its type
        parent_stop = super().stop
        if asyncio.iscoroutinefunction(parent_stop):
            # Handle it as an async function
            def run_async_stop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(parent_stop())
                finally:
                    loop.close()
            # Run in a thread to avoid blocking
            thread = threading.Thread(target=run_async_stop)
            thread.daemon = True
            thread.start()
        else:
            # Call it directly if it's synchronous
            parent_stop() 