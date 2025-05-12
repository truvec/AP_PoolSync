"""Binary sensor platform for the PoolSync Custom integration."""
import logging
from typing import Any, Callable, Dict, List, Optional, Union, Tuple

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolSyncDataUpdateCoordinator
# Re-using the helper function from sensor.py
from .sensor import _get_value_from_path

_LOGGER = logging.getLogger(__name__)

# Define Binary Sensor Descriptions:
# (BinarySensorEntityDescription, data_path_list, value_function_lambda_optional)
# value_fn: Converts the raw API value to a boolean (True/False) or None if undetermined.
BINARY_SENSOR_DESCRIPTIONS: Tuple[Tuple[BinarySensorEntityDescription, List[Union[str, int]], Optional[Callable[[Any], Optional[bool]]]], ...] = (
    # --- System Wide Binary Sensors (data['poolSync']['status'] or ['poolSync']['config']) ---
    (BinarySensorEntityDescription(
        key="poolsync_online", # Main device online status
        name="PoolSync Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=True,
    ), ["poolSync", "status", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),

    (BinarySensorEntityDescription(
        key="service_mode_active",
        name="Service Mode",
        icon="mdi:account-wrench", # Using a more descriptive icon
        # Assuming 0 = False (not in service mode), non-zero = True (in service mode)
        entity_registry_enabled_default=True,
    ), ["poolSync", "config", "serviceMode"], lambda v: bool(v) if isinstance(v, int) else None),

    (BinarySensorEntityDescription(
        key="system_fault",
        name="System Fault", # Overall system fault status
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=True,
        # Assuming 0 = No fault, non-zero = Fault present
    ), ["poolSync", "faults"], lambda v: bool(v) if isinstance(v, int) else None),

    # --- ChlorSync Device Specific Binary Sensors (data['poolSync']['devices']['0']) ---
    (BinarySensorEntityDescription(
        key="chlorsync_online", # ChlorSync module online status
        name="ChlorSync Module Online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_registry_enabled_default=True,
    ), ["poolSync", "devices", "0", "nodeAttr", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),

    (BinarySensorEntityDescription(
        key="chlorsync_fault",
        name="ChlorSync Module Fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_registry_enabled_default=True,
        # Value is a list e.g. [0]. True if list exists and contains any non-zero fault code.
        # Example: "faults":[0] means no fault. "faults":[1] or "faults":[0, 5] would mean a fault.
    ), ["poolSync", "devices", "0", "faults"],
     lambda v: isinstance(v, list) and any(fault_code != 0 for fault_code in v)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolSync binary sensors based on a config entry."""
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("Setting up binary sensors for %s (Coordinator data available: %s)",
                  coordinator.name, bool(coordinator.data))

    binary_sensors_to_add: list[PoolSyncBinarySensor] = []

    if not coordinator.data or not isinstance(coordinator.data.get("poolSync"), dict):
        _LOGGER.warning("Coordinator %s: 'poolSync' key missing or not a dict in initial data. Binary sensor setup aborted/deferred.", coordinator.name)
        return

    for description, data_path, value_fn in BINARY_SENSOR_DESCRIPTIONS:
        # Check if the base path for the sensor exists (e.g. 'devices'/'0'/'nodeAttr')
        # This is a basic check; individual values might still be missing.
        # The sensor's 'available' property will ultimately determine its state.
        parent_path = data_path[:-1]
        parent_data = _get_value_from_path(coordinator.data, parent_path)

        if parent_data is None:
            _LOGGER.debug("Binary Sensor %s for %s: parent data path %s not found or is None. Sensor might be unavailable.",
                          description.key, coordinator.name, parent_path)
            # Still add the sensor; its availability will be determined by its own logic.
        else:
            _LOGGER.debug("Binary Sensor %s for %s: parent data path %s found.",
                          description.key, coordinator.name, parent_path)

        binary_sensors_to_add.append(PoolSyncBinarySensor(coordinator, description, data_path, value_fn))

    if binary_sensors_to_add:
        async_add_entities(binary_sensors_to_add)
        _LOGGER.info("Added %d PoolSync binary sensors for %s", len(binary_sensors_to_add), coordinator.name)
    else:
        _LOGGER.info("No binary sensors were identified to be added for %s. This might be normal if data is not yet populated or definitions are too restrictive.", coordinator.name)


class PoolSyncBinarySensor(CoordinatorEntity[PoolSyncDataUpdateCoordinator], BinarySensorEntity):
    """Representation of a PoolSync Binary Sensor entity."""

    _attr_has_entity_name = True # Use the entity_description.name as the entity's name directly

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
        data_path: List[Union[str, int]],
        value_fn: Optional[Callable[[Any], Optional[bool]]] = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator) # Pass coordinator to CoordinatorEntity
        self.entity_description = description # Sets name, icon, device_class etc.
        self._data_path = data_path
        self._value_fn = value_fn

        # Unique ID: domain_mac_address_sensorkey
        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        # Device info is taken from the coordinator's device_info property
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "Initializing binary_sensor: Name: %s, Unique ID: %s, Data Path: %s",
            self.entity_description.name, self._attr_unique_id, self._data_path
        )

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the binary sensor is on."""
        raw_value = _get_value_from_path(self.coordinator.data, self._data_path)

        if raw_value is None: # Data point not found in the current payload
            _LOGGER.debug("Binary sensor %s: data point at %s is None.", self.entity_description.key, self._data_path)
            return None # State is unknown

        if self._value_fn:
            try:
                state = self._value_fn(raw_value)
                _LOGGER.debug("Binary sensor %s: Raw value '%s', processed state '%s' by value_fn.",
                              self.entity_description.key, raw_value, state)
                return state
            except Exception as e:
                _LOGGER.error("Error processing value for binary_sensor %s with value_fn: %s. Raw value: '%s'",
                              self.entity_description.key, e, raw_value)
                return None # Error during processing means state is unknown
        else:
            # Default handling if no value_fn: try to interpret as boolean directly
            if isinstance(raw_value, bool):
                _LOGGER.debug("Binary sensor %s: Raw value '%s' (boolean, no value_fn).", self.entity_description.key, raw_value)
                return raw_value
            if isinstance(raw_value, int): # Common case: 0 for False, non-zero for True
                _LOGGER.debug("Binary sensor %s: Raw value '%s' (int, no value_fn, interpreting as bool).", self.entity_description.key, raw_value)
                return bool(raw_value)

        _LOGGER.warning(
            "Binary sensor %s received value '%s' of type %s that could not be interpreted as boolean without a value_fn.",
            self.entity_description.key, raw_value, type(raw_value).__name__
        )
        return None # Cannot determine state

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if coordinator is available AND the `is_on` property can return a boolean
        # (meaning data point exists and is interpretable).
        if not super().available: # Checks coordinator.last_update_success
            return False
        # The `is_on` property returns None if data is missing or uninterpretable.
        # So, if `is_on` is not None, the sensor is considered available with a valid state.
        return self.is_on is not None

