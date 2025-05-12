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
from homeassistant.helpers.entity import EntityCategory # <<< IMPORT THIS
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
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
            elif isinstance(key_or_index, int):
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


SENSOR_DESCRIPTIONS: Tuple[Tuple[SensorEntityDescription, List[str], Optional[Callable[[Any], Any]]], ...] = (
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
        key="flow_rate",
        name="Flow Rate",
        icon="mdi:pump",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
    ), ["poolSync", "devices", "0", "status", "flowRate"], None),
    (SensorEntityDescription(
        key="chlor_output_setting",
        name="Chlorinator Output Setting",
        icon="mdi:percent-circle",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ), ["poolSync", "devices", "0", "config", "chlorOutput"], None),
    (SensorEntityDescription(
        key="boost_remaining",
        name="Boost Time Remaining",
        icon="mdi:timer-sand",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
    ), ["poolSync", "devices", "0", "status", "boostRemaining"], None),
    (SensorEntityDescription(
        key="cell_fwd_current",
        name="Cell Forward Current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "status", "fwdCurrent"], None),
    (SensorEntityDescription(
        key="cell_rev_current",
        name="Cell Reverse Current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "status", "revCurrent"], None),
    (SensorEntityDescription(
        key="cell_output_voltage",
        name="Cell Output Voltage",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "status", "outVoltage"], None),
    (SensorEntityDescription(
        key="cell_serial_number",
        name="Cell Serial Number",
        icon="mdi:barcode-scan",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "system", "cellSerialNum"], None),
    (SensorEntityDescription(
        key="cell_firmware_version",
        name="Cell Firmware Version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "system", "cellFwVersion"], None),
    (SensorEntityDescription(
        key="cell_hardware_version",
        name="Cell Hardware Version",
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "devices", "0", "system", "cellHwVersion"], None),
    (SensorEntityDescription(
        key="board_temp",
        name="Board Temperature",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
        suggested_display_precision=0,
    ), ["poolSync", "status", "boardTemp"], None),
    (SensorEntityDescription(
        key="wifi_rssi",
        name="Wi-Fi Signal Strength",
        icon="mdi:wifi-strength-2",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "status", "rssi"], None),
    (SensorEntityDescription(
        key="system_datetime",
        name="System Date/Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "status", "dateTime"], lambda v: dt_util.parse_datetime(v) if isinstance(v, str) else None),
    (SensorEntityDescription(
        key="firmware_version",
        name="System Firmware Version",
        icon="mdi:chip",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "system", "fwVersion"], None),
    (SensorEntityDescription(
        key="hardware_version",
        name="System Hardware Version",
        icon="mdi:memory",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
    ), ["poolSync", "system", "hwVersion"], None),
    (SensorEntityDescription(
        key="uptime_seconds",
        name="System Uptime",
        icon="mdi:timer-outline",
        native_unit_of_measurement="s",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC, # <<< CORRECTED
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

    if not coordinator.data or not isinstance(coordinator.data.get("poolSync"), dict):
        _LOGGER.warning("Coordinator %s: 'poolSync' key missing or not a dict in initial data. Sensor setup aborted/deferred.", coordinator.name)
        return

    for description, data_path, value_fn in SENSOR_DESCRIPTIONS:
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

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        description: SensorEntityDescription,
        data_path: List[str],
        value_fn: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._data_path = data_path
        self._value_fn = value_fn

        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
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
                return None

        if isinstance(value, (str, int, float)) or value is None:
             return value
        else:
            _LOGGER.warning("Sensor %s received value '%s' of unexpected type %s. Returning as is or None if conversion fails.",
                            self.entity_description.key, value, type(value).__name__)
            try:
                return str(value)
            except Exception:
                _LOGGER.error("Could not convert value of sensor %s to string.", self.entity_description.key)
                return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
        
        value = _get_value_from_path(self.coordinator.data, self._data_path)
        
        if value is None:
            return False
            
        if self._value_fn:
            try:
                return self._value_fn(value) is not None
            except Exception:
                return False
        
        return True
