"""Sensor platform for the PoolSync Custom integration."""
import logging
from typing import Any, Callable, Dict, List, Optional, Union, Tuple

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util # For parsing date/time string

from .const import DOMAIN # Using HA constants for units now
from .coordinator import PoolSyncDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Helper to safely navigate nested dictionary/list structure
def _get_value_from_path(data: Optional[Dict[str, Any]], path: List[Union[str, int]]) -> Any:
    """Safely retrieve a value from a nested dictionary using a path list."""
    if data is None:
        _LOGGER.debug("Attempted to get value from None data for path: %s", path)
        return None
    value = data
    try:
        for key_or_index in path:
            if value is None:
                _LOGGER.debug("Intermediate value is None at %s in path %s", key_or_index, path)
                return None
            if isinstance(key_or_index, str):
                if not isinstance(value, dict):
                    _LOGGER.debug("Expected dict but got %s at %s in path %s", type(value).__name__, key_or_index, path)
                    return None
                value = value.get(key_or_index)
            elif isinstance(key_or_index, int): # For list access, though not used in current paths
                if not isinstance(value, list) or not (0 <= key_or_index < len(value)):
                    _LOGGER.debug("Expected list or index out of bounds at %s in path %s", key_or_index, path)
                    return None
                value = value[key_or_index]
            else:
                _LOGGER.warning("Invalid key/index type %s in path %s", type(key_or_index).__name__, path)
                return None
        return value
    except (KeyError, IndexError, TypeError) as e:
        _LOGGER.debug("Error retrieving value for path %s: %s", path, e)
        return None


# Define Sensor Descriptions: (SensorEntityDescription, data_path_list, value_function_lambda_optional)
# data_path: a list of keys to navigate the coordinator.data dictionary (e.g. coordinator.data['poolSync']['devices']['0']...)
# value_fn: an optional lambda to process the extracted value before it's set as the sensor state.
SENSOR_DESCRIPTIONS: Tuple[Tuple[SensorEntityDescription, List[str], Optional[Callable[[Any], Any]]], ...] = (
    # --- ChlorSync Device Sensors (data['poolSync']['devices']['0']) ---
    (SensorEntityDescription(
        key="water_temp",
        name="Water Temperature",
        icon="mdi:coolant-temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ), ["poolSync", "devices", "0", "status", "waterTemp"], None),
    (SensorEntityDescription(
        key="salt_ppm",
        name="Salt Level",
        icon="mdi:shaker-outline",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ), ["poolSync", "devices", "0", "status", "saltPPM"], None),
    (SensorEntityDescription(
        key="flow_rate", # Unit is generic, "flowRate":25
        name="Flow Rate",
        icon="mdi:pump",
        native_unit_of_measurement=None, # No standard unit, could be GPM or just an indicator
        state_class=SensorStateClass.MEASUREMENT,
    ), ["poolSync", "devices", "0", "status", "flowRate"], None),
    (SensorEntityDescription(
        key="chlor_output_setting", # This is the 'config' setting
        name="Chlorinator Output Setting",
        icon="mdi:percent-circle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, # It's a setting, but HA treats many settings as measurement sensors
    ), ["poolSync", "devices", "0", "config", "chlorOutput"], None),
    (SensorEntityDescription(
        key="boost_remaining", # Unit unknown (seconds, minutes, hours?) "boostRemaining":0
        name="Boost Time Remaining",
        icon="mdi:timer-sand",
        native_unit_of_measurement=None, # Could be 'min' or 'hr' if known
        state_class=SensorStateClass.MEASUREMENT, # Could be SensorDeviceClass.DURATION if unit was 's'
    ), ["poolSync", "devices", "0", "status", "boostRemaining"], None),
    (SensorEntityDescription(
        key="cell_fwd_current",
        name="Cell Forward Current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE, # Assuming mA from example: "fwdCurrent":0
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, # Diagnostic
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "status", "fwdCurrent"], None),
    (SensorEntityDescription(
        key="cell_rev_current",
        name="Cell Reverse Current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE, # Assuming mA from example: "revCurrent":5591
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, # Diagnostic
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "status", "revCurrent"], None),
    (SensorEntityDescription(
        key="cell_output_voltage",
        name="Cell Output Voltage",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT, # Assuming mV from example: "outVoltage":15407
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, # Diagnostic
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "status", "outVoltage"], None),
    (SensorEntityDescription(
        key="cell_serial_number",
        name="Cell Serial Number",
        icon="mdi:barcode-scan",
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "system", "cellSerialNum"], None),
    (SensorEntityDescription(
        key="cell_firmware_version",
        name="Cell Firmware Version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "system", "cellFwVersion"], None),
    (SensorEntityDescription(
        key="cell_hardware_version",
        name="Cell Hardware Version",
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "devices", "0", "system", "cellHwVersion"], None),

    # --- System Wide Sensors (data['poolSync']) ---
    (SensorEntityDescription(
        key="board_temp",
        name="Board Temperature",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, # Diagnostic
        entity_category="diagnostic",
        suggested_display_precision=0,
    ), ["poolSync", "status", "boardTemp"], None),
    (SensorEntityDescription(
        key="wifi_rssi",
        name="Wi-Fi Signal Strength",
        icon="mdi:wifi-strength-2", # Example icon, adjust based on typical values
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False, # Diagnostic
        entity_category="diagnostic",
    ), ["poolSync", "status", "rssi"], None),
    (SensorEntityDescription(
        key="system_datetime",
        name="System Date/Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP, # HA will display this as a datetime
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "status", "dateTime"], lambda v: dt_util.parse_datetime(v) if isinstance(v, str) else None),
    (SensorEntityDescription(
        key="firmware_version",
        name="System Firmware Version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "system", "fwVersion"], None),
    (SensorEntityDescription(
        key="hardware_version",
        name="System Hardware Version",
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "system", "hwVersion"], None),
    (SensorEntityDescription(
        key="uptime_seconds",
        name="System Uptime",
        icon="mdi:timer-outline",
        native_unit_of_measurement="s", # seconds
        device_class=SensorDeviceClass.DURATION, # HA will display this nicely
        state_class=SensorStateClass.TOTAL_INCREASING, # Assuming it's an increasing counter
        entity_registry_enabled_default=False,
        entity_category="diagnostic",
    ), ["poolSync", "stats", "upTimeSecs"], None),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolSync sensors based on a config entry."""
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up sensors for %s (Coordinator data available: %s)",
                  coordinator.name, bool(coordinator.data))

    sensors_to_add: list[PoolSyncSensor] = []

    # Check if essential top-level keys exist in coordinator data
    if not coordinator.data or not isinstance(coordinator.data.get("poolSync"), dict):
        _LOGGER.warning("Coordinator %s: 'poolSync' key missing or not a dict in initial data. Sensor setup aborted/deferred.", coordinator.name)
        # Depending on how critical this is, you might raise ConfigEntryNotReady
        # or simply add no sensors and let the coordinator retry.
        return

    for description, data_path, value_fn in SENSOR_DESCRIPTIONS:
        # Check if the specific data path is accessible in the initial data
        # This is more to log which sensors might be initially unavailable
        # The sensor's 'available' property will ultimately determine its state.
        initial_value = _get_value_from_path(coordinator.data, data_path)
        if initial_value is None:
            _LOGGER.debug("Sensor %s for %s: initial value at path %s is None. Sensor will be unavailable until data appears.",
                          description.key, coordinator.name, data_path)
        else:
            _LOGGER.debug("Sensor %s for %s: initial value at path %s is %s.",
                          description.key, coordinator.name, data_path, initial_value)

        sensors_to_add.append(PoolSyncSensor(coordinator, description, data_path, value_fn))

    if sensors_to_add:
        async_add_entities(sensors_to_add)
        _LOGGER.info("Added %d PoolSync sensors for %s", len(sensors_to_add), coordinator.name)
    else:
        _LOGGER.warning("No sensors were identified to be added for %s. This might be normal if data is not yet populated.", coordinator.name)


class PoolSyncSensor(CoordinatorEntity[PoolSyncDataUpdateCoordinator], SensorEntity):
    """Representation of a PoolSync Sensor entity."""

    _attr_has_entity_name = True # Use the entity_description.name as the entity's name directly

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        description: SensorEntityDescription,
        data_path: List[str], # Changed from List[Union[str, int]] as only str keys are used
        value_fn: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator) # Pass coordinator to CoordinatorEntity
        self.entity_description = description # This sets name, icon, uom, etc.
        self._data_path = data_path
        self._value_fn = value_fn

        # Unique ID: domain_mac_address_sensorkey
        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        # Device info is taken from the coordinator's device_info property
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "Initializing sensor: Name: %s, Unique ID: %s, Data Path: %s",
            self.entity_description.name, self._attr_unique_id, self._data_path
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        value = _get_value_from_path(self.coordinator.data, self._data_path)

        if value is None:
            return None

        if self._value_fn:
            try:
                processed_value = self._value_fn(value)
                _LOGGER.debug("Sensor %s: Raw value '%s', processed value '%s' by value_fn.",
                              self.entity_description.key, value, processed_value)
                return processed_value
            except Exception as e:
                _LOGGER.error("Error processing value for sensor %s with value_fn: %s. Raw value: '%s'",
                              self.entity_description.key, e, value)
                return None # Error during processing means value is not available in correct format

        # Basic type check for direct return
        if isinstance(value, (str, int, float)) or value is None:
            return value
        # For SensorDeviceClass.TIMESTAMP, HA expects a datetime object.
        # If not processed by value_fn, and it's a string, it might cause issues.
        # The dt_util.parse_datetime in value_fn for system_datetime handles this.

        _LOGGER.warning("Sensor %s received value '%s' of unexpected type %s. Returning as is or None if conversion fails.",
                        self.entity_description.key, value, type(value).__name__)
        # As a last resort, try to convert to string if it's not a basic type already.
        try:
            return str(value)
        except Exception:
            _LOGGER.error("Could not convert value of sensor %s to string.", self.entity_description.key)
            return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # An entity is available if the coordinator is available and the specific data point
        # for this sensor exists and is not None (or can be processed by value_fn to not None).
        if not super().available: # Checks coordinator.last_update_success
            return False
        
        value = _get_value_from_path(self.coordinator.data, self._data_path)
        
        if value is None:
            return False
            
        if self._value_fn:
            try:
                return self._value_fn(value) is not None
            except Exception:
                return False # Error in value_fn means value is not available
        
        return True # Value is not None and no processing error

