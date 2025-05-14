"""Number platform for the PoolSync Custom integration."""
import logging
from typing import Any, Callable, Dict, List, Optional, Union

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError # For service call errors

from .const import (
    DOMAIN,
    DEFAULT_CHLOR_OUTPUT_MIN,
    DEFAULT_CHLOR_OUTPUT_MAX,
    DEFAULT_CHLOR_OUTPUT_STEP,
    NUMBER_KEY_CHLOR_OUTPUT,
)
from .coordinator import PoolSyncDataUpdateCoordinator
from .sensor import _get_value_from_path # Reuse helper from sensor.py

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTIONS: tuple[NumberEntityDescription, List[str], Optional[Callable[[Any], Any]]] = (
    (NumberEntityDescription(
        key=NUMBER_KEY_CHLOR_OUTPUT, # "chlor_output_control"
        name="Chlorinator Output", # This will be the entity name
        icon="mdi:knob", # Using a knob icon for control
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=DEFAULT_CHLOR_OUTPUT_MIN, # e.g., 0
        native_max_value=DEFAULT_CHLOR_OUTPUT_MAX, # e.g., 100
        native_step=DEFAULT_CHLOR_OUTPUT_STEP,     # e.g., 1 or 5
        mode=NumberMode.SLIDER, # Or NumberMode.BOX
    ), ["devices", "0", "config", "chlorOutput"], None), # Path to get current value
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PoolSync number entities based on a config entry."""
    coordinator: PoolSyncDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    _LOGGER.debug("NUMBER_PLATFORM: Starting async_setup_entry for %s.", coordinator.name)

    number_entities: list[PoolSyncChlorOutputNumberEntity] = []

    if not coordinator.data:
        _LOGGER.warning("NUMBER_PLATFORM: Coordinator %s has no data. Cannot set up number entities.", coordinator.name)
        return

    if not isinstance(coordinator.data.get("devices"), dict):
        _LOGGER.warning("NUMBER_PLATFORM: Coordinator %s data is missing 'devices' dictionary. Cannot set up Chlorinator Output.", coordinator.name)
        return
        
    if not isinstance(coordinator.data["devices"].get("0"), dict):
        _LOGGER.warning(
            "NUMBER_PLATFORM: Coordinator %s data 'devices' dictionary is missing '0' key or it's not a dict. "
            "Chlorinator Output number entity cannot be set up. devices content: %s",
            coordinator.name, coordinator.data["devices"]
        )
        return

    _LOGGER.debug("NUMBER_PLATFORM: Coordinator data seems valid for device '0'. Proceeding to create number entities.")

    for description, data_path, value_fn in NUMBER_DESCRIPTIONS:
        _LOGGER.debug("NUMBER_PLATFORM: Processing number entity description for key: %s", description.key)
        current_value = _get_value_from_path(coordinator.data, data_path)
        if current_value is None:
            _LOGGER.warning(
                "NUMBER_PLATFORM: Coordinator %s: Value for number entity %s at path %s is None. "
                "Entity may be unavailable or show an unexpected state initially.",
                coordinator.name, description.key, data_path
            )
        else:
            _LOGGER.debug(
                "NUMBER_PLATFORM: Coordinator %s: Initial value for number entity %s at path %s is %s.",
                coordinator.name, description.key, data_path, current_value
            )
        
        try:
            entity_instance = PoolSyncChlorOutputNumberEntity(coordinator, description, data_path, value_fn)
            number_entities.append(entity_instance)
            _LOGGER.debug("NUMBER_PLATFORM: Successfully created instance for %s.", description.key)
        except Exception as e:
            _LOGGER.exception("NUMBER_PLATFORM: Error creating instance for %s: %s", description.key, e)


    if number_entities:
        _LOGGER.debug("NUMBER_PLATFORM: Adding %d number entities.", len(number_entities))
        async_add_entities(number_entities)
        _LOGGER.info("NUMBER_PLATFORM: Added %d PoolSync number entities for %s", len(number_entities), coordinator.name)
    else:
        _LOGGER.warning("NUMBER_PLATFORM: No number entities were created for %s. Check descriptions and data paths.", coordinator.name)


class PoolSyncChlorOutputNumberEntity(CoordinatorEntity[PoolSyncDataUpdateCoordinator], NumberEntity):
    """Representation of a PoolSync Chlorinator Output Number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolSyncDataUpdateCoordinator,
        description: NumberEntityDescription,
        data_path: List[str],
        value_fn: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._data_path = data_path
        self._value_fn = value_fn # Not used for native_value here, but kept for pattern consistency

        self._attr_unique_id = f"{coordinator.mac_address}_{description.key}"
        self._attr_device_info = coordinator.device_info

        _LOGGER.debug(
            "NUMBER_ENTITY %s: Initialized. Unique ID: %s, Data Path: %s",
            self.entity_description.name, self._attr_unique_id, self._data_path
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return the current value of the number entity."""
        value = _get_value_from_path(self.coordinator.data, self._data_path)
        # _LOGGER.debug("NUMBER_ENTITY %s: native_value raw from path %s: %s", self.entity_description.key, self._data_path, value)
        if value is None:
            return None
        try:
            num_value = float(value)
            return num_value
        except (ValueError, TypeError):
            _LOGGER.error(
                "NUMBER_ENTITY %s: could not convert value '%s' (type: %s) to float from path %s",
                self.entity_description.key, value, type(value).__name__, self._data_path
            )
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        new_value = int(value) # API expects an integer for percentage
        _LOGGER.info(
            "NUMBER_ENTITY %s: Attempting to set native_value to %d (from HA UI float value: %f)",
            self.entity_description.key, new_value, value
        )

        if not hasattr(self.coordinator, '_password') or not self.coordinator._password:
             _LOGGER.error("NUMBER_ENTITY %s: Password not available on coordinator. Cannot set value.", self.entity_description.key)
             raise HomeAssistantError("API password not available to set value.")
        
        current_api_password = self.coordinator._password
        _LOGGER.debug("NUMBER_ENTITY %s: Using password from coordinator to set value.", self.entity_description.key)

        try:
            _LOGGER.debug("NUMBER_ENTITY %s: Calling api_client.async_set_chlor_output with value %d", self.entity_description.key, new_value)
            api_response = await self.coordinator.api_client.async_set_chlor_output(
                password=current_api_password,
                output_percentage=new_value
            )
            _LOGGER.info("NUMBER_ENTITY %s: API call to set chlor_output to %d completed. Response: %s", self.entity_description.key, new_value, api_response)

            _LOGGER.debug("NUMBER_ENTITY %s: Requesting coordinator refresh after setting value.", self.entity_description.key)
            await self.coordinator.async_request_refresh()
            _LOGGER.info("NUMBER_ENTITY %s: Successfully set value to %d and requested refresh.", self.entity_description.key, new_value)

        except HomeAssistantError: 
            raise
        except Exception as e:
            _LOGGER.error(
                "NUMBER_ENTITY %s: Failed to set new value %d: %s",
                self.entity_description.key, new_value, e
            )
            raise HomeAssistantError(f"Failed to set chlorine output to {new_value}%: {e}") from e

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        coordinator_available = super().available
        # Check if the specific data path for the current value exists
        value_exists = _get_value_from_path(self.coordinator.data, self._data_path) is not None
        is_available = coordinator_available and value_exists
        # _LOGGER.debug(
        #     "NUMBER_ENTITY %s: Availability check: coordinator_available=%s, value_exists_at_path=%s, final_available=%s",
        #     self.entity_description.key, coordinator_available, value_exists, is_available
        # )
        return is_available

