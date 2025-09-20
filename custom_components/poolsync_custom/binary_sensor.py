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

from .const import (
    DOMAIN,
    CHLORINATOR_ID,
    HEATPUMP_ID,
)

from .coordinator import PoolSyncDataUpdateCoordinator
from .sensor import _get_value_from_path # Reuse helper

_LOGGER = logging.getLogger(__name__)

# System-wide binary sensors
BINARY_SENSOR_DESCRIPTIONS_POOLSYNC: Tuple[Tuple[BinarySensorEntityDescription, List[Union[str, int]], Optional[Callable[[Any], Optional[bool]]]], ...] = (
    (BinarySensorEntityDescription(
        key="poolsync_online", name="PoolSync Online", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True,
    ), ["poolSync", "status", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),
    (BinarySensorEntityDescription(
        key="service_mode_active", name="Service Mode", icon="mdi:account-wrench", entity_registry_enabled_default=True,
    ), ["poolSync", "config", "serviceMode"], lambda v: bool(v) if isinstance(v, int) else None),
    (BinarySensorEntityDescription(
        key="system_fault", name="System Fault", device_class=BinarySensorDeviceClass.PROBLEM, entity_registry_enabled_default=True,
    ), ["poolSync", "faults"], lambda v: bool(v) if isinstance(v, int) else None),
)

# Chlorinator binary sensors
BINARY_SENSOR_DESCRIPTIONS_CHLORSYNC: Tuple[Tuple[BinarySensorEntityDescription, List[Union[str, int]], Optional[Callable[[Any], Optional[bool]]]], ...] = (    
    (BinarySensorEntityDescription(
        key="chlorsync_online", name="ChlorSync Module Online", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True,
    ), ["devices", CHLORINATOR_ID, "nodeAttr", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),
    (BinarySensorEntityDescription(
        key="chlorsync_fault", name="ChlorSync Module Fault", device_class=BinarySensorDeviceClass.PROBLEM, entity_registry_enabled_default=True,
    ), ["devices", CHLORINATOR_ID, "faults"], lambda v: isinstance(v, list) and any(fault_code != 0 for fault_code in v)),
)

# Heat pump binary sensors - using correct thresholds based on log analysis
BINARY_SENSOR_DESCRIPTIONS_HEATPUMP: Tuple[Tuple[BinarySensorEntityDescription, List[Union[str, int]], Optional[Callable[[Any], Optional[bool]]]], ...] = (    
    (BinarySensorEntityDescription(
        key="heatpump_online", name="HeatPump Module Online", device_class=BinarySensorDeviceClass.CONNECTIVITY, entity_registry_enabled_default=True,
    ), ["devices", HEATPUMP_ID, "nodeAttr", "online"], lambda v: bool(v) if isinstance(v, (bool, int)) else None),
    (BinarySensorEntityDescription(
        key="heatpump_fault", name="HeatPump Module Fault", device_class=BinarySensorDeviceClass.PROBLEM, entity_registry_enabled_default=True,
    ), ["devices", HEATPUMP_ID, "faults"], lambda v: isinstance(v, list) and any(fault_code != 0 for fault_code in v)),
    (BinarySensorEntityDescription(
        key="heatpump_flow", name="HeatPump Flow", entity_registry_enabled_default=True,
    ), ["devices", HEATPUMP_ID, "status", "ctrlFlags"], lambda v: bool(int(v) & 1) if isinstance(v, (bool, int)) else None),
)


class PoolSyncHeatPumpBinarySensor(CoordinatorEntity[PoolSyncDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor for heat pump status that needs access to multiple data points."""
    
    _attr_has_entity_name = True
    
    def __init__(
        self, 
        coordinator: PoolSyncDataUpdateCoordinator, 
        description: BinarySensorEntityDescription,
        heatpump_id: str,
        sensor_type: str  # "active", "fan", or "compressor"
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._heatpump_id = heatpump_id
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> Optional[bool]:
        """Return true if the binary sensor is on."""
        if not self.coordinator.data:
            return None
            
        # Get all needed values
        mode = _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "config", "mode"])
        state_flags = _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "status", "stateFlags"])
        ctrl_flags = _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "status", "ctrlFlags"])
        
        if mode is None or state_flags is None or ctrl_flags is None:
            return None
            
        try:
            mode_val = int(mode)
            state_val = int(state_flags)
            ctrl_val = int(ctrl_flags)
            
            # Only active when in heating mode (mode = 1)
            if mode_val != 1:
                return False
                
            if self._sensor_type == "active":
                # Heat pump is active if stateFlags > baseline (257)
                return state_val > 257
                
            elif self._sensor_type == "fan":
                # Fan runs when stateFlags >= 264 (based on log analysis)
                return state_val >= 264
                
            elif self._sensor_type == "compressor":
                # Compressor active when ctrlFlags >= 397 (based on log analysis)
                return ctrl_val >= 397
                
        except (ValueError, TypeError):
            _LOGGER.error("Heat pump binary sensor %s: Could not convert values to int", self._sensor_type)
            return None
            
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        coordinator_available = super().available
        # Check if required data paths exist
        mode_exists = _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "config", "mode"]) is not None
        flags_exist = (
            _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "status", "stateFlags"]) is not None and
            _get_value_from_path(self.coordinator.data, ["devices", self._heatpump_id, "status", "ctrlFlags"]) is not None
        )
        return coordinator_available and mode_exists and flags_exist


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    binary_sensors_to_add: list[BinarySensorEntity] = []

    if not coordinator.data or not (isinstance(coordinator.data.get("poolSync"), dict) and isinstance(coordinator.data.get("devices"), dict)):
        _LOGGER.warning("Coordinator %s: Initial data is missing 'poolSync' or 'devices' top-level keys. Binary sensor setup may be incomplete.", coordinator.name)
    
    # Get actual device IDs
    heatpump_id = HEATPUMP_ID
    chlor_id = CHLORINATOR_ID
    if coordinator.data and isinstance(coordinator.data.get("deviceType"), dict):
        deviceTypes = coordinator.data.get("deviceType")
        temp = [key for key, value in deviceTypes.items() if value == "heatPump"]
        heatpump_id = temp[0] if temp else "-1"
        temp = [key for key, value in deviceTypes.items() if value == "chlorSync"]
        chlor_id = temp[0] if temp else "-1"
        
    # Add system-wide sensors
    for description, data_path, value_fn in BINARY_SENSOR_DESCRIPTIONS_POOLSYNC:
        binary_sensors_to_add.append(PoolSyncBinarySensor(coordinator, description, data_path, value_fn))
    
    # Add chlorinator sensors if present
    if chlor_id != "-1":
        for description, data_path, value_fn in BINARY_SENSOR_DESCRIPTIONS_CHLORSYNC:
            data_path[1] = chlor_id
            binary_sensors_to_add.append(PoolSyncBinarySensor(coordinator, description, data_path, value_fn))
           
    # Add heat pump sensors if present
    if heatpump_id != "-1":
        # Add simple binary sensors first
        for description, data_path, value_fn in BINARY_SENSOR_DESCRIPTIONS_HEATPUMP:
            data_path[1] = heatpump_id
            binary_sensors_to_add.append(PoolSyncBinarySensor(coordinator, description, data_path, value_fn))
        
        # Add complex multi-parameter sensors
        active_desc = BinarySensorEntityDescription(
            key="heatpump_active", name="HeatPump Active", entity_registry_enabled_default=True
        )
        binary_sensors_to_add.append(
            PoolSyncHeatPumpBinarySensor(coordinator, active_desc, heatpump_id, "active")
        )
        
        fan_desc = BinarySensorEntityDescription(
            key="heatpump_fan", name="HeatPump Fan", entity_registry_enabled_default=True
        )
        binary_sensors_to_add.append(
            PoolSyncHeatPumpBinarySensor(coordinator, fan_desc, heatpump_id, "fan")
        )
        
        compressor_desc = BinarySensorEntityDescription(
            key="heatpump_compressor", name="HeatPump Compressor", entity_registry_enabled_default=True
        )
        binary_sensors_to_add.append(
            PoolSyncHeatPumpBinarySensor(coordinator, compressor_desc, heatpump_id, "compressor")
        )

    if binary_sensors_to_add:
        async_add_entities(binary_sensors_to_add)
        _LOGGER.info("Added %d PoolSync binary sensors for %s", len(binary_sensors_to_add), coordinator.name)


class PoolSyncBinarySensor(CoordinatorEntity[PoolSyncDataUpdateCoordinator], BinarySensorEntity):
    """Standard binary sensor for simple data path values."""
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
        raw_value = _get_value_from_path(self.coordinator.data, self._data_path)
        if raw_value is None: 
            return None
        if self._value_fn:
            try: 
                return self._value_fn(raw_value)
            except Exception as e:
                _LOGGER.error("BinarySensor %s: Error processing value '%s' with value_fn: %s", self.entity_description.key, raw_value, e)
                return None
        if isinstance(raw_value, bool): 
            return raw_value
        if isinstance(raw_value, int): 
            return bool(raw_value)
        return None

    @property
    def available(self) -> bool:
        coordinator_available = super().available
        is_on_state = self.is_on
        return coordinator_available and (is_on_state is not None)
