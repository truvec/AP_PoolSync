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
from .sensor import _get_value_from_path # Reuse helper

_LOGGER = logging.getLogger(__name__)

BINARY_SENSOR_DESCRIPTIONS: Tuple[Tuple[BinarySensorEntityDescription, List[Union[str, int]], Optional[Callable[[Any], Optional[bool]]]], ...] = (
    (BinarySensorEntityDescription(
        key="poolsync_online", name="PoolSync Online", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True,
    ), ["poolSync", "status", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),
    (BinarySensorEntityDescription(
        key="service_mode_active", name="Service Mode", icon="mdi:account-wrench", entity_registry_enabled_default=True,
    ), ["poolSync", "config", "serviceMode"], lambda v: bool(v) if isinstance(v, int) else None),
    (BinarySensorEntityDescription(
        key="system_fault", name="System Fault", device_class=BinarySensorDeviceClass.PROBLEM, entity_registry_enabled_default=True,
    ), ["poolSync", "faults"], lambda v: bool(v) if isinstance(v, int) else None),
    (BinarySensorEntityDescription(
        key="chlorsync_online", name="ChlorSync Module Online", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True,
    ), ["poolSync", "devices", "0", "nodeAttr", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),
    (BinarySensorEntityDescription(
        key="chlorsync_fault", name="ChlorSync Module Fault", device_class=BinarySensorDeviceClass.PROBLEM, entity_registry_enabled_default=True,
    ), ["poolSync", "devices", "0", "faults"], lambda v: isinstance(v, list) and any(fault_code != 0 for fault_code in v)),
)

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    binary_sensors_to_add: list[PoolSyncBinarySensor] = []
    if not coordinator.data or not isinstance(coordinator.data.get("poolSync"), dict):
        _LOGGER.warning("Coordinator %s: 'poolSync' key missing or not a dict in initial data. Binary sensor setup aborted.", coordinator.name)
        return
    for description, data_path, value_fn in BINARY_SENSOR_DESCRIPTIONS:
        binary_sensors_to_add.append(PoolSyncBinarySensor(coordinator, description, data_path, value_fn))
    if binary_sensors_to_add:
        async_add_entities(binary_sensors_to_add)

class PoolSyncBinarySensor(CoordinatorEntity[PoolSyncDataUpdateCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    def __init__(
        self, coordinator: PoolSyncDataUpdateCoordinator, description: BinarySensorEntityDescription,
        data_path: List[Union[str, int]], value_fn: Optional[Callable[[Any], Optional[bool]]] = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._data_path = data_path
        self._value_fn = value_fn
        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> Optional[bool]:
        _LOGGER.debug("BinarySensor %s: Checking is_on. Coordinator data available: %s", self.entity_description.key, bool(self.coordinator.data))
        raw_value = _get_value_from_path(self.coordinator.data, self._data_path)
        _LOGGER.debug("BinarySensor %s: Raw value from path %s: %s (type: %s)", self.entity_description.key, self._data_path, raw_value, type(raw_value).__name__)

        if raw_value is None:
            _LOGGER.debug("BinarySensor %s: Raw value is None, returning None for is_on.", self.entity_description.key)
            return None

        if self._value_fn:
            try:
                state = self._value_fn(raw_value)
                _LOGGER.debug("BinarySensor %s: Processed state by value_fn: %s (type: %s)", self.entity_description.key, state, type(state).__name__)
                return state
            except Exception as e:
                _LOGGER.error("BinarySensor %s: Error processing value '%s' with value_fn: %s", self.entity_description.key, raw_value, e)
                return None
        
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, int): # Default interpretation for int if no value_fn
            return bool(raw_value)
            
        _LOGGER.warning("BinarySensor %s: Value '%s' (type: %s) could not be interpreted as boolean. No value_fn or default handling.", self.entity_description.key, raw_value, type(raw_value).__name__)
        return None

    @property
    def available(self) -> bool:
        coordinator_available = super().available
        # For binary sensors, availability also depends on whether `is_on` can determine a clear True/False state
        is_on_state = self.is_on # Call property to get its logging
        final_available = coordinator_available and (is_on_state is not None)
        
        _LOGGER.debug(
            "BinarySensor %s: Availability check: coordinator_available=%s, is_on_state=%s, final_available=%s",
            self.entity_description.key, coordinator_available, is_on_state, final_available
        )
        return final_available

